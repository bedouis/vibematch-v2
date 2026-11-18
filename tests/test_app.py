"""Smoke tests for app.py using Streamlit's AppTest. No network, no credentials."""

import socket
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import pipeline as pipeline_mod
from src.intent import (
    GeminiServiceError,
    InvalidModelResponseError,
    MusicIntent,
    NoConfidentInterpretationError,
)
from src.pipeline import RecommendationResult

APP = str(Path(__file__).resolve().parent.parent / "app.py")
SECRET = "AIza-super-secret-value"


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("test attempted a real network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)


def new_app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def search(at, query):
    at.text_input[0].set_value(query)
    at.button[0].click()
    at.run()
    return at


def patch_interpreter(monkeypatch, genres=(), moods=(), error=None):
    calls = []

    def fake(query, vocabulary, *, client=None, model=None):
        calls.append(query)
        if error:
            raise error
        return MusicIntent(tuple(genres), tuple(moods))

    monkeypatch.setattr(pipeline_mod, "interpret_intent", fake)
    return calls


def all_text(at):
    parts = [e.value for e in at.markdown] + [e.value for e in at.caption] + [e.value for e in at.error]
    parts += [e.value for e in at.warning] + [e.value for e in at.info] + [e.value for e in at.subheader]
    return "\n".join(parts)


def test_initial_page_shows_title_subtitle_and_form():
    at = new_app()
    assert at.title[0].value == "VibeMatch 2.0"
    assert "Discover music that matches your mood." in [s.value for s in at.subheader]
    assert at.text_input[0].placeholder == "Relaxing ambient music for reading"
    assert at.button[0].label == "Find my vibe"
    assert not at.error and not at.warning
    assert "5,000 tracks" in all_text(at)               # catalog loaded; attribution shown


def test_no_search_on_load(monkeypatch):
    calls = patch_interpreter(monkeypatch, ["rock"], [])
    new_app()
    assert calls == []


def test_successful_search_shows_interpretation_and_ten_ranked_cards(monkeypatch):
    calls = patch_interpreter(monkeypatch, ["ambient"], ["relaxing"])
    at = search(new_app(), "Relaxing ambient music for reading")
    assert not at.exception and not at.error
    assert calls == ["Relaxing ambient music for reading"]          # one Gemini call
    text = all_text(at)
    assert "How Gemini interpreted your request" in text
    assert "`ambient`" in text and "`relaxing`" in text
    assert "Top matches" in text
    assert "not an AI confidence" in text and "no audio was analyzed" in text
    for rank in range(1, 11):
        assert f"**{rank}. " in text
    assert text.count("**3/3**") == 10
    assert "Matches your requested ambient genre and relaxing mood." in text
    links = at.get("link_button")
    assert len(links) == 10
    assert all(l.proto.url.startswith("http://www.jamendo.com/track/") for l in links)


def test_genre_only_search(monkeypatch):
    patch_interpreter(monkeypatch, ["jazz"], [])
    at = search(new_app(), "jazz")
    text = all_text(at)
    assert "**Moods:** _none_" in text and "**2/3**" in text
    assert "Matches your requested jazz genre." in text


def test_empty_query_shows_warning_without_calling_gemini(monkeypatch):
    calls = patch_interpreter(monkeypatch, ["rock"], [])
    at = search(new_app(), "   ")
    assert calls == []
    assert at.warning and "Describe what you want to hear" in at.warning[0].value
    assert not at.get("link_button")


def test_missing_api_key_message_without_exception():
    at = search(new_app(), "calm rock")             # real interpreter, no key, no client built
    assert not at.exception
    assert len(at.error) == 1 and "GEMINI_API_KEY" in at.error[0].value
    assert not at.get("link_button")


@pytest.mark.parametrize("error,expected", [
    (GeminiServiceError(f"Gemini request failed: boom {SECRET}"), "Gemini couldn't be reached"),
    (InvalidModelResponseError(f"bad {SECRET}"), "couldn't be verified"),
    (NoConfidentInterpretationError(f"nothing {SECRET}"), "couldn't match that"),
    (RuntimeError(f"unexpected {SECRET}"), "Something unexpected went wrong"),
])
def test_error_states_use_fixed_messages_and_hide_details(monkeypatch, error, expected):
    patch_interpreter(monkeypatch, error=error)
    at = search(new_app(), "something")
    assert not at.exception                          # no traceback rendered
    assert len(at.error) == 1 and expected in at.error[0].value
    assert SECRET not in all_text(at) and "Traceback" not in all_text(at)
    assert not at.get("link_button")


def test_no_match_message(monkeypatch):
    patch_interpreter(monkeypatch, ["rock"], [])
    monkeypatch.setattr("src.pipeline.recommend_v2", lambda *a, **k: [])
    at = search(new_app(), "rock")
    assert at.info and "No tracks in the catalog matched" in at.info[0].value
    assert not at.get("link_button")


def test_titles_with_markdown_characters_render_literally():
    from app import md
    assert md("*Hi* [x](y) _z_ $5") == r"\*Hi\* \[x\]\(y\) \_z\_ \$5"


def test_app_import_has_no_side_effects():
    import importlib
    import app
    importlib.reload(app)
    assert callable(app.main)


# ---- result persistence (st.session_state) --------------------------------

def link_urls(at):
    return [l.proto.url for l in at.get("link_button")]


def test_result_persists_across_reruns_without_new_gemini_call(monkeypatch):
    calls = patch_interpreter(monkeypatch, ["ambient"], ["relaxing"])
    at = search(new_app(), "Relaxing ambient music for reading")
    before = (all_text(at), link_urls(at))
    assert len(before[1]) == 10 and len(calls) == 1
    for _ in range(3):
        at.run()                                    # unrelated rerun, no form submission
        assert not at.exception and not at.error
        assert (all_text(at), link_urls(at)) == before
    assert len(calls) == 1                          # Gemini was not called again


def test_editing_the_text_box_without_submitting_keeps_results_and_makes_no_call(monkeypatch):
    calls = patch_interpreter(monkeypatch, ["ambient"], ["relaxing"])
    at = search(new_app(), "Relaxing ambient music for reading")
    urls = link_urls(at)
    at.text_input[0].set_value("something else entirely")
    at.run()
    assert link_urls(at) == urls and len(calls) == 1


def test_stored_value_is_only_the_immutable_result(monkeypatch):
    patch_interpreter(monkeypatch, ["jazz"], [])
    at = search(new_app(), "jazz please")
    stored = at.session_state["last_result"]
    assert isinstance(stored, RecommendationResult)
    assert stored.query == "jazz please" and stored.intent.genres == ("jazz",)
    assert len(stored.recommendations) == 10


def test_no_result_stored_before_any_search(monkeypatch):
    patch_interpreter(monkeypatch, ["jazz"], [])
    at = new_app()
    assert "last_result" not in at.session_state


def test_new_submission_runs_pipeline_once_and_replaces_old_result(monkeypatch):
    first = patch_interpreter(monkeypatch, ["ambient"], ["relaxing"])
    at = search(new_app(), "ambient")
    old_urls = link_urls(at)
    assert "`ambient`" in all_text(at) and len(first) == 1

    second = patch_interpreter(monkeypatch, ["jazz"], [])
    at = search(at, "jazz")
    text = all_text(at)
    assert len(first) == 1 and len(second) == 1     # exactly one new execution
    assert "`jazz`" in text and "`ambient`" not in text and "relaxing" not in text
    assert link_urls(at) != old_urls and len(link_urls(at)) == 10
    assert at.session_state["last_result"].intent.genres == ("jazz",)

    at.run()                                        # the replacement is what persists
    assert "`jazz`" in all_text(at) and "`ambient`" not in all_text(at)
    assert len(second) == 1


@pytest.mark.parametrize("error,expected", [
    (GeminiServiceError("boom"), "Gemini couldn't be reached"),
    (InvalidModelResponseError("bad"), "couldn't be verified"),
    (NoConfidentInterpretationError("none"), "couldn't match that"),
    (RuntimeError(f"unexpected {SECRET}"), "Something unexpected went wrong"),
])
def test_failed_submission_clears_stale_results_and_shows_only_the_error(monkeypatch, error, expected):
    patch_interpreter(monkeypatch, ["ambient"], ["relaxing"])
    at = search(new_app(), "ambient")
    assert len(link_urls(at)) == 10

    patch_interpreter(monkeypatch, error=error)
    at = search(at, "a new query that fails")
    text = all_text(at)
    assert len(at.error) == 1 and expected in at.error[0].value
    assert not link_urls(at)
    assert "Top matches" not in text and "How Gemini interpreted" not in text and "`ambient`" not in text
    assert SECRET not in text
    assert "last_result" not in at.session_state

    at.run()                                        # stale result must not reappear on the next rerun
    assert not link_urls(at) and "Top matches" not in all_text(at)


def test_empty_submission_clears_stale_results(monkeypatch):
    calls = patch_interpreter(monkeypatch, ["ambient"], ["relaxing"])
    at = search(new_app(), "ambient")
    assert len(link_urls(at)) == 10
    at = search(at, "   ")
    assert at.warning and "Describe what you want to hear" in at.warning[0].value
    assert not link_urls(at) and "Top matches" not in all_text(at)
    assert len(calls) == 1                          # blank submit made no call
    at.run()
    assert not link_urls(at)


def test_no_match_submission_replaces_stale_results(monkeypatch):
    patch_interpreter(monkeypatch, ["ambient"], ["relaxing"])
    at = search(new_app(), "ambient")
    patch_interpreter(monkeypatch, ["rock"], [])
    monkeypatch.setattr("src.pipeline.recommend_v2", lambda *a, **k: [])
    at = search(at, "rock")
    text = all_text(at)
    assert at.info and "No tracks in the catalog matched" in at.info[0].value
    assert not link_urls(at) and "`ambient`" not in text and "`rock`" in text   # new intent, no old cards


def test_missing_key_after_success_clears_results(monkeypatch):
    original = pipeline_mod.interpret_intent
    patch_interpreter(monkeypatch, ["jazz"], [])
    at = search(new_app(), "jazz")
    assert len(link_urls(at)) == 10

    monkeypatch.setattr(pipeline_mod, "interpret_intent", original)   # real interpreter, no key
    at = search(at, "calm rock")
    assert "GEMINI_API_KEY" in at.error[0].value
    assert not link_urls(at) and "last_result" not in at.session_state


# ---- top-10 behavior on the real 5,000-track catalog ----------------------

def test_app_requests_ten_results_within_recommender_limit():
    import app
    from src.v2_recommender import MAX_K
    assert app.TOP_K == 10 <= MAX_K
    assert app.CATALOG_PATH.name == "jamendo_5000.csv"


def test_cards_are_in_exact_rank_order_with_stable_id_tiebreak(monkeypatch):
    import re
    from src.v2_recommender import load_v2_catalog, recommend_v2
    import app
    patch_interpreter(monkeypatch, ["rock", "poprock"], ["calm"])
    at = search(new_app(), "calm rock")
    expected = recommend_v2(load_v2_catalog(app.CATALOG_PATH), genres=["rock", "poprock"], moods=["calm"], k=10)
    text = all_text(at)
    shown = re.findall(r"\*\*(\d+)\. (.+?)\*\*", text)
    assert [int(n) for n, _ in shown] == list(range(1, 11))
    assert [app.md(r.track.title) for r in expected] == [t for _, t in shown]
    assert [r.score for r in expected] == sorted((r.score for r in expected), reverse=True)
    assert len(link_urls(at)) == 10
    assert link_urls(at) == [r.track.track_url for r in expected]


def test_fewer_than_ten_matches_shows_only_real_matches(monkeypatch):
    from src.v2_recommender import catalog_vocabulary, load_v2_catalog
    import app
    catalog = load_v2_catalog(app.CATALOG_PATH)
    counts = {g: sum(1 for t in catalog if g in t.genres) for g in catalog_vocabulary(catalog).genres}
    rare, n = min(((g, c) for g, c in counts.items() if c < 10), key=lambda gc: (gc[1], gc[0]))
    patch_interpreter(monkeypatch, [rare], [])
    at = search(new_app(), rare)
    assert len(link_urls(at)) == n < 10              # no padding with unrelated tracks
    assert all_text(at).count("**2/3**") == n
