"""Tests for scripts/evaluate_v2.py and docs/evaluation_results.csv (offline, no Gemini)."""

import ast
import csv
import dataclasses
import importlib.util
import json
import socket
import sys
from pathlib import Path

import pytest

from src import intent as intent_mod
from src import pipeline as pipeline_mod
from src.intent import MusicIntent
from src.v2_recommender import MusicTrack, RankedRecommendation, catalog_vocabulary, load_v2_catalog, recommend_v2

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "evaluate_v2.py"
RESULTS_CSV = ROOT / "docs" / "evaluation_results.csv"

_spec = importlib.util.spec_from_file_location("evaluate_v2", SCRIPT)
ev = importlib.util.module_from_spec(_spec)
sys.modules["evaluate_v2"] = ev   # dataclasses need the module registered
_spec.loader.exec_module(ev)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("test attempted a real network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)


@pytest.fixture(scope="module")
def real_catalog():
    return load_v2_catalog(ev.DEFAULT_CATALOG)


@pytest.fixture(scope="module")
def real_eval(real_catalog):
    return ev.evaluate(real_catalog)


def render(rows, tmp_path):
    out = tmp_path / "r.csv"
    ev.write_results(rows, out)
    return out.read_bytes()


# ---- small hand-computable fixture ----------------------------------------

def track(n, artist, genres, moods):
    return MusicTrack(f"track_{n:07d}", f"Song {n}", artist, tuple(sorted(genres)), tuple(sorted(moods)),
                      (), f"http://www.jamendo.com/track/{n}")


TINY = [
    track(1, "A1", ["rock"], ["calm"]),
    track(2, "A1", ["rock"], ["happy"]),
    track(3, "A2", ["rock"], ["calm"]),
    track(4, "A3", ["jazz"], ["calm"]),
    track(5, "A4", ["rock"], ["happy"]),
    track(6, "A5", ["jazz"], ["sad"]),
]


def tiny_valid(sid="T1", genres=("rock",), moods=("calm",)):
    text = json.dumps({"genres": list(genres), "moods": list(moods)})
    return ev.Scenario(sid, "rock but calm", tuple(genres), tuple(moods), "recommendations", text,
                       ev.SOURCE_REFERENCE, "note")


def tiny_invalid(sid="T2", text='{"genres": ["vaporwave"], "moods": []}', expected="InvalidModelResponseError"):
    return ev.Scenario(sid, "vaporwave", (), (), expected, text, ev.SOURCE_HAND_WRITTEN, "note")


# ---- scenario data validity ------------------------------------------------

def test_twelve_scenarios_with_unique_ids_and_requests():
    ids = [s.id for s in ev.SCENARIOS]
    assert ids == [f"S{i:02d}" for i in range(1, 13)]
    assert len({s.request for s in ev.SCENARIOS}) == 12


def test_scenario_fields_are_complete_and_requests_valid():
    for s in ev.SCENARIOS:
        assert s.request.strip() and len(s.request) <= intent_mod.MAX_QUERY_CHARS
        assert s.notes.strip()
        assert s.source in (ev.SOURCE_REFERENCE, ev.SOURCE_HAND_WRITTEN)
        assert "not a Gemini response" in s.source
        json.loads(s.candidate_response)


def test_scenarios_cover_required_kinds():
    by_id = {s.id: s for s in ev.SCENARIOS}
    assert by_id["S08"].genres and not by_id["S08"].moods                 # genre-only
    assert by_id["S06"].moods and not by_id["S06"].genres                 # mood-only
    assert by_id["S01"].genres and by_id["S01"].moods                     # both
    assert by_id["S11"].expected == "InvalidModelResponseError"           # unsupported subgenre
    assert by_id["S12"].expected == "NoConfidentInterpretationError"      # ambiguous
    assert sum(s.expected == "recommendations" for s in ev.SCENARIOS) == 10
    assert sum(s.expected != "recommendations" for s in ev.SCENARIOS) == 2


def test_valid_scenario_candidate_matches_its_reference_interpretation():
    for s in ev.SCENARIOS:
        if s.expected == "recommendations":
            assert json.loads(s.candidate_response) == {"genres": list(s.genres), "moods": list(s.moods)}


def test_reference_tags_exist_in_real_catalog_vocabulary(real_catalog):
    vocab = catalog_vocabulary(real_catalog)
    for s in ev.SCENARIOS:
        if s.expected != "recommendations":
            continue
        assert len(s.genres) <= 2 and len(s.moods) <= 2
        assert set(s.genres) <= vocab.genres, s.id
        assert set(s.moods) <= vocab.moods, s.id
        assert ev.expected_ranking(real_catalog, s.genres, s.moods, 10), s.id    # something matches


def test_negative_scenario_candidates_really_are_unsupported_or_empty(real_catalog):
    vocab = catalog_vocabulary(real_catalog)
    assert "vaporwave" not in vocab.genres and "vaporwave" not in vocab.moods
    assert json.loads(next(s for s in ev.SCENARIOS if s.id == "S12").candidate_response) == {"genres": [], "moods": []}


def test_invalid_cases_are_well_formed():
    ids = [c.id for c in ev.INVALID_CASES]
    assert len(ids) == len(set(ids)) == 18
    assert {c.layer for c in ev.INVALID_CASES} == {"query", "response", "recommender"}


# ---- real run --------------------------------------------------------------

def test_real_run_metrics_and_denominators(real_eval):
    rows, invalid, m = real_eval
    ok = [r for r in rows if r["execution_status"] == "ok"]
    assert len(rows) == 12 and len(ok) == 10
    assert m["A_execution_success"] == (12, 12)
    assert m["B_ranking_correct"] == (10, 10)                  # denominator = result sets, not all scenarios
    assert m["C_evidence_consistent_scenarios"] == (10, 10)
    total_recs = sum(r["recommendation_count"] for r in ok)
    assert m["C_evidence_consistent_recommendations"] == (total_recs, total_recs)
    assert m["E_coverage"] == (10, 10)                         # denominator = valid scenarios
    assert m["F1_invalid_scenarios_rejected"] == (2, 2)
    assert m["F2_invalid_cases_rejected"] == (18, 18)
    assert m["short_lists"] == ["S10"]


def test_real_run_each_row_agrees_with_direct_engine_call(real_catalog, real_eval):
    rows, _, _ = real_eval
    for row, scenario in zip(rows, ev.SCENARIOS):
        if row["execution_status"] != "ok":
            continue
        direct = recommend_v2(real_catalog, genres=scenario.genres, moods=scenario.moods, k=10)
        assert row["recommended_track_ids"] == ";".join(r.track.track_id for r in direct)
        assert row["recommendation_count"] == len(direct)


def test_real_artist_counts_are_accurate(real_catalog, real_eval):
    rows, _, m = real_eval
    ratios = []
    for row, scenario in zip(rows, ev.SCENARIOS):
        if row["execution_status"] != "ok":
            continue
        direct = recommend_v2(real_catalog, genres=scenario.genres, moods=scenario.moods, k=10)
        distinct = len({r.track.artist.casefold() for r in direct})
        assert row["distinct_artists"] == distinct
        assert row["artist_diversity_at_10"] == f"{distinct / len(direct):.3f}"
        assert row["distinct_genres"] == len({g for r in direct for g in r.track.genres})
        ratios.append(distinct / len(direct))
    assert m["D_artist_diversity_mean"] == pytest.approx(sum(ratios) / len(ratios))
    assert m["D_artist_diversity_min"] == min(ratios) and m["D_scenarios_measured"] == 10


def test_expected_failure_modes_are_visible_in_results(real_eval):
    rows, _, _ = real_eval
    by_id = {r["scenario_id"]: r for r in rows}
    assert by_id["S09"]["score_distribution"] == "2x10"       # 'calm' contributes nothing to the top 10
    assert by_id["S04"]["score_distribution"] == "3x4;2x6"
    assert by_id["S10"]["recommendation_count"] == 1 and by_id["S10"]["artist_diversity_at_10"] == "1.000"
    assert "Short list" in by_id["S10"]["notes"]


# ---- reproducibility and output -------------------------------------------

def test_evaluation_is_reproducible_and_matches_committed_results(real_catalog, real_eval, tmp_path):
    first = render(real_eval[0], tmp_path)
    second_rows, _, _ = ev.evaluate(real_catalog)
    assert render(second_rows, tmp_path) == first
    assert RESULTS_CSV.read_bytes() == first                      # committed file is current


def test_results_csv_schema(tmp_path, real_eval):
    with open(RESULTS_CSV, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert reader.fieldnames == ev.RESULT_COLUMNS
    assert len(rows) == 12
    assert not any(name.startswith("_") for name in reader.fieldnames)
    assert all(r["interpretation_source"] and "Gemini" in r["interpretation_source"] for r in rows)


def test_does_not_mutate_catalog(real_catalog):
    before = list(real_catalog)
    ev.evaluate(real_catalog)
    assert real_catalog == before


# ---- metrics on a hand-computed fixture -----------------------------------

def test_fixture_row_values_by_hand():
    (row,), _, _ = ev.evaluate(TINY, [tiny_valid()], [])
    # scores: t1=3, t3=3, t2=2, t5=2, t4=1; t6 excluded
    assert row["execution_status"] == "ok" and row["outcome_as_expected"] is True
    assert row["recommended_track_ids"] == "track_0000001;track_0000003;track_0000002;track_0000005;track_0000004"
    assert row["score_distribution"] == "3x2;2x2;1x1"
    assert row["distinct_artists"] == 4 and row["artist_diversity_at_10"] == "0.800"   # A1,A2,A1,A4,A3
    assert row["distinct_genres"] == 2                                                  # rock, jazz
    assert row["ranking_check"] == "pass" and row["evidence_check"] == "pass"
    assert "Short list: 5 of 10" in row["notes"]


def test_fixture_denominators_and_short_lists():
    scenarios = [tiny_valid("T1"), tiny_valid("T2", ("jazz",), ("sad",)), tiny_invalid("T3")]
    rows, _, m = ev.evaluate(TINY, scenarios, [])
    assert m["A_execution_success"] == (3, 3)
    assert m["B_ranking_correct"] == (2, 2)                      # only the 2 result sets, not 3 scenarios
    assert m["E_coverage"] == (2, 2)                             # only the 2 valid scenarios
    assert m["F1_invalid_scenarios_rejected"] == (1, 1)
    assert m["C_evidence_consistent_recommendations"] == (5 + 2, 5 + 2)
    assert m["short_lists"] == ["T1", "T2"]
    ratios = [4 / 5, 2 / 2]
    assert m["D_artist_diversity_mean"] == pytest.approx(sum(ratios) / 2)
    assert m["D_artist_diversity_min"] == pytest.approx(0.8)


def test_short_list_is_not_padded():
    (row,), _, _ = ev.evaluate(TINY, [tiny_valid("T1", ("jazz",), ())], [])
    assert row["recommendation_count"] == 2                      # only two jazz tracks exist
    assert row["recommended_track_ids"] == "track_0000004;track_0000006"
    assert row["artist_diversity_at_10"] == "1.000"              # denominator is returned tracks (2), not 10


def test_unexpected_outcome_lowers_success_rate():
    # A scenario that is expected to be rejected but is actually valid must count as a failure.
    wrong = ev.Scenario("T9", "x", (), (), "InvalidModelResponseError",
                        json.dumps({"genres": ["rock"], "moods": []}), ev.SOURCE_HAND_WRITTEN, "n")
    rows, _, m = ev.evaluate(TINY, [tiny_valid("T1"), wrong], [])
    assert rows[1]["outcome_as_expected"] is False
    assert m["A_execution_success"] == (1, 2)
    assert m["F1_invalid_scenarios_rejected"] == (0, 1)
    # The wrong rejection type also fails.
    other = tiny_invalid("T8", expected="NoConfidentInterpretationError")
    assert ev.evaluate(TINY, [other], [])[0][0]["outcome_as_expected"] is False


# ---- the checkers can actually fail ---------------------------------------

@pytest.fixture
def good():
    catalog = TINY
    result = recommend_v2(catalog, genres=["rock"], moods=["calm"], k=10)
    return catalog, MusicIntent(("rock",), ("calm",)), result


def test_ranking_checker_accepts_correct_and_rejects_corruption(good):
    catalog, intent, recs = good
    assert ev.ranking_correct(catalog, intent, recs)
    assert not ev.ranking_correct(catalog, intent, list(reversed(recs)))                     # wrong order
    assert not ev.ranking_correct(catalog, intent, recs[:-1])                                # missing track
    bad_score = [dataclasses.replace(recs[0], score=2)] + recs[1:]
    assert not ev.ranking_correct(catalog, intent, bad_score)                                # wrong score
    filler = dataclasses.replace(recs[0], track=TINY[5], score=0, matched_genres=(), matched_moods=())
    assert not ev.ranking_correct(catalog, intent, recs + [filler])                          # zero-score filler
    swapped_tie = [recs[1], recs[0]] + recs[2:]
    assert not ev.ranking_correct(catalog, intent, swapped_tie)                              # tie-break violated


def test_evidence_checker_accepts_correct_and_rejects_corruption(good):
    _, intent, recs = good
    rec = recs[0]
    assert ev.evidence_correct(rec, intent)
    assert not ev.evidence_correct(dataclasses.replace(rec, matched_genres=("jazz",)), intent)       # tag not on track
    assert not ev.evidence_correct(dataclasses.replace(rec, matched_moods=()), intent)               # missing evidence
    assert not ev.evidence_correct(dataclasses.replace(rec, explanation="Matches your requested rock genre."), intent)
    assert not ev.evidence_correct(dataclasses.replace(rec, explanation=rec.explanation[:-1] + " and is high-energy."), intent)
    assert not ev.evidence_correct(dataclasses.replace(rec, explanation=rec.explanation.replace("rock", "jazz")), intent)


def test_evidence_checker_handles_multiple_matched_tags():
    catalog = [track(1, "A", ["rock", "poprock"], ["calm", "happy"])]
    intent = MusicIntent(("rock", "poprock"), ("calm", "happy"))
    (rec,) = recommend_v2(catalog, genres=intent.genres, moods=intent.moods, k=1)
    assert rec.explanation == "Matches your requested rock and poprock genres and calm and happy moods."
    assert ev.evidence_correct(rec, intent)


# ---- invalid interpretations ----------------------------------------------

def test_all_invalid_cases_rejected_with_no_recommendations(real_catalog, real_eval):
    _, invalid, _ = real_eval
    assert len(invalid) == 18
    for case, result in zip(ev.INVALID_CASES, invalid):
        assert result["raised"] == case.expected, case.id
        assert result["recommendations"] == 0
        assert result["rejected_as_expected"] is True


def test_an_accepted_invalid_case_is_reported_as_not_rejected(real_catalog):
    vocab = catalog_vocabulary(real_catalog)
    sneaky = ev.InvalidCase("Z1", "response", "actually valid", '{"genres": ["rock"], "moods": []}',
                            "InvalidModelResponseError")
    result = ev.run_invalid_case(sneaky, real_catalog, vocab)
    assert result["raised"] == "none" and result["recommendations"] > 0
    assert result["rejected_as_expected"] is False


def test_query_cases_never_reach_gemini(real_catalog):
    vocab = catalog_vocabulary(real_catalog)
    for case in (c for c in ev.INVALID_CASES if c.layer == "query"):
        result = ev.run_invalid_case(case, real_catalog, vocab)
        assert result["raised"] == "InvalidQueryError" and result["gemini_calls"] == 0


def test_a_query_that_would_reach_gemini_is_flagged_as_not_rejected(real_catalog):
    vocab = catalog_vocabulary(real_catalog)
    leaky = ev.InvalidCase("Z2", "query", "valid query wrongly treated as invalid", "calm rock",
                           "InvalidQueryError")
    result = ev.run_invalid_case(leaky, real_catalog, vocab)
    assert result["gemini_calls"] == 1                 # the guard recorded the attempted call
    assert result["raised"] == "GeminiServiceError"    # interpret_intent wraps the guard's failure
    assert result["rejected_as_expected"] is False


# ---- no Gemini, no network -------------------------------------------------

def test_evaluation_never_touches_gemini_or_network(monkeypatch, real_catalog):
    def boom(*args, **kwargs):
        raise AssertionError("Gemini must not be used by the offline evaluation")

    monkeypatch.setattr(intent_mod.genai, "Client", boom)
    monkeypatch.setattr(pipeline_mod, "interpret_intent", boom)
    rows, invalid, m = ev.evaluate(real_catalog)
    assert m["A_execution_success"] == (12, 12) and len(invalid) == 18


def test_results_never_claim_live_model_output(real_eval):
    rows, _, _ = real_eval
    for row in rows:
        source = row["interpretation_source"]
        assert source in (ev.SOURCE_REFERENCE, ev.SOURCE_HAND_WRITTEN)
        assert "not a Gemini response" in source
        assert "live" not in source.lower()


def test_script_has_no_api_key_or_client_construction():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | \
            {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "environ" not in names and "getenv" not in names and "Client" not in names
    assert "GEMINI_API_KEY" not in SCRIPT.read_text(encoding="utf-8")


def test_network_is_blocked_in_this_module():
    with pytest.raises(AssertionError, match="real network"):
        socket.create_connection(("example.com", 80))
