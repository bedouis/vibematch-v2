#!/usr/bin/env python3
"""Offline reliability evaluation for VibeMatch 2.0.

Runs 12 fixed scenarios and a list of invalid-input cases through the real
pipeline (``src.pipeline.run_pipeline``), real validator
(``src.intent.parse_model_response``) and real recommender
(``src.v2_recommender.recommend_v2``) on the actual catalog.

IMPORTANT: no Gemini is involved. For each scenario the "interpretation" is
either a human-selected REFERENCE interpretation (valid scenarios) or a
HAND-WRITTEN candidate response (invalid scenarios). Neither is a model
output, and none of the numbers here is a measure of Gemini's accuracy. No
network access or API key is used.

Usage:
    python scripts/evaluate_v2.py [--catalog data/jamendo_5000.csv]
                                  [--output docs/evaluation_results.csv]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.intent import (  # noqa: E402
    MAX_QUERY_CHARS,
    IntentError,
    InvalidModelResponseError,
    InvalidQueryError,
    NoConfidentInterpretationError,
    interpret_intent,
    parse_model_response,
)
from src.pipeline import RecommendationError, run_pipeline  # noqa: E402
from src.v2_recommender import (  # noqa: E402
    EmptyPreferencesError,
    UnsupportedTagError,
    catalog_vocabulary,
    load_v2_catalog,
    recommend_v2,
)

DEFAULT_CATALOG = REPO_ROOT / "data" / "jamendo_5000.csv"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "evaluation_results.csv"
K = 10

SOURCE_REFERENCE = "reference interpretation (human-selected; not a Gemini response)"
SOURCE_HAND_WRITTEN = "hand-written candidate response (not a Gemini response)"

RESULT_COLUMNS = [
    "scenario_id", "request", "reference_genres", "reference_moods", "interpretation_source",
    "expected_outcome", "execution_status", "outcome_as_expected", "recommendation_count",
    "recommended_track_ids", "score_distribution", "distinct_artists", "artist_diversity_at_10",
    "distinct_genres", "ranking_check", "evidence_check", "notes",
]

# Words an explanation must never contain (no unsupported audio claims).
BANNED_EXPLANATION_WORDS = ("energy", "tempo", "beat", "acoustic", "similar", "bpm", "loud", "danceab", "fast")


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    id: str
    request: str
    genres: tuple[str, ...]      # human-selected reference interpretation
    moods: tuple[str, ...]
    expected: str                # "recommendations" or the exception class name expected
    candidate_response: str      # JSON text that is validated like a model response
    source: str
    notes: str


def _valid(sid, request, genres, moods, notes):
    text = json.dumps({"genres": list(genres), "moods": list(moods)})
    return Scenario(sid, request, tuple(genres), tuple(moods), "recommendations", text, SOURCE_REFERENCE, notes)


SCENARIOS: tuple[Scenario, ...] = (
    _valid("S01", "Relaxing ambient music", ["ambient"], ["relaxing"],
           "Genre + mood; many tracks match both."),
    _valid("S02", "Energetic rock", ["rock"], ["energetic"],
           "Genre + mood."),
    _valid("S03", "Happy pop", ["pop"], ["happy"],
           "Genre + mood."),
    _valid("S04", "Calm jazz", ["jazz"], ["calm"],
           "Genre + mood; only a few tracks carry both tags, so most of the top 10 are jazz-only."),
    _valid("S05", "Dark atmospheric music", ["atmospheric"], ["dark"],
           "'atmospheric' exists only as a genre tag, not a mood; reference maps it to the genre field."),
    _valid("S06", "Music for reading", [], ["calm", "relaxing"],
           "Mood-only; no genre is implied, so genre stays empty. Two moods are alternatives (OR)."),
    _valid("S07", "Music for exercise", [], ["workout", "sport"],
           "Mood-only; 'workout' and 'sport' are alternatives (OR)."),
    _valid("S08", "Classical music", ["classical"], [],
           "Genre-only."),
    _valid("S09", "Calm death metal", ["deathmetal"], ["calm"],
           "Conflicting/unusual: no catalog track has both tags, so the best possible score is 2."),
    _valid("S10", "Metalcore", ["metalcore"], [],
           "Supported but extremely sparse tag; the result list is short, not padded."),
    Scenario("S11", "Vaporwave", (), (), "InvalidModelResponseError",
             json.dumps({"genres": ["vaporwave"], "moods": []}), SOURCE_HAND_WRITTEN,
             "Unsupported subgenre. Reference interpretation is empty; the candidate names a tag the catalog "
             "lacks and must be rejected, not remapped."),
    Scenario("S12", "Surprise me", (), (), "NoConfidentInterpretationError",
             json.dumps({"genres": [], "moods": []}), SOURCE_HAND_WRITTEN,
             "Ambiguous request. No genre or mood is justified; an empty interpretation must be rejected."),
)

LONG_QUERY = "a" * (MAX_QUERY_CHARS + 1)


@dataclass(frozen=True)
class InvalidCase:
    id: str
    layer: str          # "query" | "response" | "recommender"
    description: str
    payload: Any
    expected: str       # exception class name


INVALID_CASES: tuple[InvalidCase, ...] = (
    InvalidCase("X01", "query", "blank query", "", "InvalidQueryError"),
    InvalidCase("X02", "query", "whitespace-only query", "  \n\t ", "InvalidQueryError"),
    InvalidCase("X03", "query", "non-string query", 42, "InvalidQueryError"),
    InvalidCase("X04", "query", f"query over {MAX_QUERY_CHARS} characters", LONG_QUERY, "InvalidQueryError"),
    InvalidCase("X05", "response", "unsupported genre", '{"genres": ["vaporwave"], "moods": []}',
                "InvalidModelResponseError"),
    InvalidCase("X06", "response", "unsupported mood", '{"genres": [], "moods": ["melancholy-ish"]}',
                "InvalidModelResponseError"),
    InvalidCase("X07", "response", "mood returned in genre field", '{"genres": ["calm"], "moods": []}',
                "InvalidModelResponseError"),
    InvalidCase("X08", "response", "genre returned in mood field", '{"genres": [], "moods": ["rock"]}',
                "InvalidModelResponseError"),
    InvalidCase("X09", "response", "three genres", '{"genres": ["rock", "pop", "jazz"], "moods": []}',
                "InvalidModelResponseError"),
    InvalidCase("X10", "response", "missing moods field", '{"genres": ["rock"]}', "InvalidModelResponseError"),
    InvalidCase("X11", "response", "unexpected extra field", '{"genres": ["rock"], "moods": [], "score": 9}',
                "InvalidModelResponseError"),
    InvalidCase("X12", "response", "not JSON", "rock and calm", "InvalidModelResponseError"),
    InvalidCase("X13", "response", "markdown-fenced JSON", '```json\n{"genres": ["rock"], "moods": []}\n```',
                "InvalidModelResponseError"),
    InvalidCase("X14", "response", "wrong type (genres is a string)", '{"genres": "rock", "moods": []}',
                "InvalidModelResponseError"),
    InvalidCase("X15", "response", "one valid and one unsupported genre (no partial acceptance)",
                '{"genres": ["rock", "vaporwave"], "moods": []}', "InvalidModelResponseError"),
    InvalidCase("X16", "response", "empty interpretation", '{"genres": [], "moods": []}',
                "NoConfidentInterpretationError"),
    InvalidCase("X17", "recommender", "unsupported tag sent straight to the recommender",
                {"genres": ["vaporwave"], "moods": []}, "UnsupportedTagError"),
    InvalidCase("X18", "recommender", "empty preferences sent straight to the recommender",
                {"genres": [], "moods": []}, "EmptyPreferencesError"),
)


# --------------------------------------------------------------------------
# Independent checkers (re-implemented here, not imported from the engine)
# --------------------------------------------------------------------------

def expected_ranking(catalog, genres, moods, k):
    """Documented rule: +2 if any requested genre matches, +1 if any requested mood matches;
    drop zero scores; sort by score desc then numeric track ID asc; keep k."""
    rows = []
    for track in catalog:
        score = (2 if set(genres) & set(track.genres) else 0) + (1 if set(moods) & set(track.moods) else 0)
        if score > 0:
            rows.append((-score, int(track.track_id.split("_")[1]), track.track_id))
    rows.sort()
    return [(track_id, -neg) for neg, _, track_id in rows[:k]]


def ranking_correct(catalog, intent, recommendations, k=K) -> bool:
    actual = [(r.track.track_id, r.score) for r in recommendations]
    return actual == expected_ranking(catalog, intent.genres, intent.moods, k)


def _join(words):
    words = list(words)
    return " and ".join(words) if len(words) <= 2 else ", ".join(words[:-1]) + " and " + words[-1]


def evidence_correct(rec, intent) -> bool:
    """matched tags are exactly the requested tags the track really has, and the
    explanation is the fixed template over those tags with no audio claims."""
    want_genres = tuple(g for g in intent.genres if g in rec.track.genres)
    want_moods = tuple(m for m in intent.moods if m in rec.track.moods)
    if rec.matched_genres != want_genres or rec.matched_moods != want_moods:
        return False
    parts = []
    if want_genres:
        parts.append(f"{_join(want_genres)} {'genre' if len(want_genres) == 1 else 'genres'}")
    if want_moods:
        parts.append(f"{_join(want_moods)} {'mood' if len(want_moods) == 1 else 'moods'}")
    if not parts or rec.explanation != "Matches your requested " + " and ".join(parts) + ".":
        return False
    return not any(word in rec.explanation.lower() for word in BANNED_EXPLANATION_WORDS)


# --------------------------------------------------------------------------
# Running scenarios
# --------------------------------------------------------------------------

def _parse_as_interpreter(candidate_response: str):
    """An interpreter that validates fixed text exactly as a model response would be."""
    def interpreter(query, vocabulary, *, client=None, model=None):
        return parse_model_response(candidate_response, vocabulary)
    return interpreter


def run_scenario(scenario: Scenario, catalog, vocabulary) -> dict[str, Any]:
    row: dict[str, Any] = {
        "scenario_id": scenario.id,
        "request": scenario.request,
        "reference_genres": json.dumps(list(scenario.genres)),
        "reference_moods": json.dumps(list(scenario.moods)),
        "interpretation_source": scenario.source,
        "expected_outcome": scenario.expected,
        "recommendation_count": 0,
        "recommended_track_ids": "",
        "score_distribution": "",
        "distinct_artists": "",
        "artist_diversity_at_10": "",
        "distinct_genres": "",
        "ranking_check": "n/a",
        "evidence_check": "n/a",
    }
    notes = [scenario.notes]
    try:
        result = run_pipeline(scenario.request, catalog, vocabulary, k=K,
                              interpreter=_parse_as_interpreter(scenario.candidate_response))
    except (IntentError, RecommendationError) as exc:
        status = f"rejected:{type(exc).__name__}"
        row["execution_status"] = status
        row["outcome_as_expected"] = status == f"rejected:{scenario.expected}"
        row["_result"] = None
        row["notes"] = " ".join(notes)
        return row

    recs = result.recommendations
    row["execution_status"] = "ok"
    row["outcome_as_expected"] = scenario.expected == "recommendations"
    row["recommendation_count"] = len(recs)
    row["recommended_track_ids"] = ";".join(r.track.track_id for r in recs)
    dist = Counter(r.score for r in recs)
    row["score_distribution"] = ";".join(f"{score}x{dist[score]}" for score in sorted(dist, reverse=True))
    if recs:
        artists = {r.track.artist.casefold() for r in recs}
        row["distinct_artists"] = len(artists)
        row["artist_diversity_at_10"] = f"{len(artists) / len(recs):.3f}"
        row["distinct_genres"] = len({g for r in recs for g in r.track.genres})
    row["ranking_check"] = "pass" if ranking_correct(catalog, result.intent, recs) else "fail"
    row["evidence_check"] = "pass" if all(evidence_correct(r, result.intent) for r in recs) else "fail"
    if len(recs) < K:
        notes.append(f"Short list: {len(recs)} of {K} requested; no filler added.")
    row["_result"] = result
    row["notes"] = " ".join(notes)
    return row


class _NoCallClient:
    """Stand-in Gemini client that records any call. A query-validation case passes only if it
    is never called. (interpret_intent wraps client exceptions, so the call count is what we trust.)"""

    def __init__(self):
        self.calls = 0
        self.models = self  # exposes generate_content like genai.Client.models

    def generate_content(self, **kwargs):
        self.calls += 1
        raise AssertionError("evaluation must never call Gemini")


def run_invalid_case(case: InvalidCase, catalog, vocabulary) -> dict[str, Any]:
    """Returns {'id', 'layer', 'description', 'expected', 'raised', 'recommendations', 'gemini_calls',
    'rejected_as_expected'}."""
    raised, recs, guard = None, 0, _NoCallClient()
    try:
        if case.layer == "query":
            interpret_intent(case.payload, vocabulary, client=guard)
            recs = -1  # reaching here means the query was wrongly accepted
        elif case.layer == "response":
            result = run_pipeline("evaluation request", catalog, vocabulary, k=K,
                                  interpreter=_parse_as_interpreter(case.payload))
            recs = len(result.recommendations)
        else:
            recs = len(recommend_v2(catalog, genres=case.payload["genres"], moods=case.payload["moods"], k=K))
    except (IntentError, RecommendationError, UnsupportedTagError, EmptyPreferencesError) as exc:
        raised = type(exc).__name__
    return {
        "id": case.id, "layer": case.layer, "description": case.description, "expected": case.expected,
        "raised": raised or "none", "recommendations": recs, "gemini_calls": guard.calls,
        "rejected_as_expected": raised == case.expected and recs == 0 and guard.calls == 0,
    }


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def compute_metrics(rows, invalid_results) -> dict[str, Any]:
    """Every metric carries its numerator and denominator."""
    ok_rows = [r for r in rows if r["execution_status"] == "ok"]
    valid_rows = [r for r in rows if r["expected_outcome"] == "recommendations"]
    invalid_rows = [r for r in rows if r["expected_outcome"] != "recommendations"]

    evidence_ok = evidence_total = 0
    for r in ok_rows:
        result = r["_result"]
        for rec in result.recommendations:
            evidence_total += 1
            evidence_ok += evidence_correct(rec, result.intent)

    diversities = [(r["scenario_id"], int(r["distinct_artists"]), int(r["recommendation_count"]))
                   for r in ok_rows if r["recommendation_count"]]
    ratios = [d / n for _, d, n in diversities]
    return {
        "A_execution_success": (sum(r["outcome_as_expected"] for r in rows), len(rows)),
        "B_ranking_correct": (sum(r["ranking_check"] == "pass" for r in ok_rows), len(ok_rows)),
        "C_evidence_consistent_recommendations": (evidence_ok, evidence_total),
        "C_evidence_consistent_scenarios": (sum(r["evidence_check"] == "pass" for r in ok_rows), len(ok_rows)),
        "D_artist_diversity_mean": (sum(ratios) / len(ratios)) if ratios else None,
        "D_artist_diversity_min": min(ratios) if ratios else None,
        "D_artist_diversity_max": max(ratios) if ratios else None,
        "D_scenarios_measured": len(ratios),
        "E_coverage": (sum(1 for r in valid_rows if r["execution_status"] == "ok" and r["recommendation_count"] >= 1),
                       len(valid_rows)),
        "F1_invalid_scenarios_rejected": (sum(1 for r in invalid_rows if r["outcome_as_expected"]
                                               and r["recommendation_count"] == 0), len(invalid_rows)),
        "F2_invalid_cases_rejected": (sum(c["rejected_as_expected"] for c in invalid_results), len(invalid_results)),
        "short_lists": [r["scenario_id"] for r in ok_rows if r["recommendation_count"] < K],
    }


def evaluate(catalog, scenarios=SCENARIOS, invalid_cases=INVALID_CASES):
    vocabulary = catalog_vocabulary(catalog)
    rows = [run_scenario(s, catalog, vocabulary) for s in scenarios]
    invalid_results = [run_invalid_case(c, catalog, vocabulary) for c in invalid_cases]
    return rows, invalid_results, compute_metrics(rows, invalid_results)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def write_results(rows, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _frac(pair) -> str:
    num, den = pair
    return f"{num}/{den} = {num / den:.1%}" if den else f"{num}/{den} (n/a)"


def format_metrics(m) -> str:
    lines = [
        f"A  Offline execution success      {_frac(m['A_execution_success'])}",
        f"B  Ranking correctness (scenarios) {_frac(m['B_ranking_correct'])}",
        f"C  Evidence consistency (recs)    {_frac(m['C_evidence_consistent_recommendations'])}",
        f"C  Evidence consistency (scenarios){_frac(m['C_evidence_consistent_scenarios'])}",
        f"D  Artist diversity@10            mean {m['D_artist_diversity_mean']:.3f}  "
        f"min {m['D_artist_diversity_min']:.3f}  max {m['D_artist_diversity_max']:.3f}  "
        f"({m['D_scenarios_measured']} result sets)",
        f"E  Recommendation coverage        {_frac(m['E_coverage'])}",
        f"F1 Invalid scenarios rejected     {_frac(m['F1_invalid_scenarios_rejected'])}",
        f"F2 Invalid-input cases rejected   {_frac(m['F2_invalid_cases_rejected'])}",
        f"Short result lists (<{K}): {', '.join(m['short_lists']) or 'none'}",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline VibeMatch 2.0 reliability evaluation (no Gemini, no network).")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    catalog = load_v2_catalog(args.catalog)
    rows, invalid_results, metrics = evaluate(catalog)
    write_results(rows, args.output)

    print(f"catalog: {args.catalog.name} ({len(catalog)} tracks); k={K}; offline, no Gemini calls")
    for r in rows:
        print(f"{r['scenario_id']} {r['request']!r:32} {r['execution_status']:42} n={r['recommendation_count']:<3} "
              f"scores[{r['score_distribution']}] artists={r['distinct_artists']} "
              f"rank={r['ranking_check']} evidence={r['evidence_check']}")
    print()
    for c in invalid_results:
        print(f"{c['id']} {c['layer']:11} {c['description']:62} -> {c['raised']}"
              f"{'' if c['rejected_as_expected'] else '   <-- UNEXPECTED'}")
    print()
    print(format_metrics(metrics))
    print(f"\nwrote {args.output}")
    return 0 if metrics["A_execution_success"][0] == metrics["A_execution_success"][1] else 1


if __name__ == "__main__":
    sys.exit(main())
