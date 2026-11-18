import ast
import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from src import pipeline as pipeline_mod
from src.intent import (
    GeminiServiceError,
    IntentError,
    InvalidModelResponseError,
    InvalidQueryError,
    MissingApiKeyError,
    MusicIntent,
    NoConfidentInterpretationError,
)
from src.pipeline import RecommendationError, RecommendationResult, run_pipeline
from src.v2_recommender import MusicTrack, catalog_vocabulary, load_v2_catalog, recommend_v2

ROOT = Path(__file__).resolve().parent.parent
REAL_CATALOG = ROOT / "data" / "jamendo_5000.csv"


def track(n, genres=(), moods=(), instruments=()):
    return MusicTrack(f"track_{n:07d}", f"Song {n}", f"Artist {n}", tuple(sorted(genres)),
                      tuple(sorted(moods)), tuple(sorted(instruments)), f"http://www.jamendo.com/track/{n}")


CATALOG = [
    track(1, ["rock"], ["calm"]),
    track(2, ["rock", "poprock"], ["happy"]),
    track(3, ["jazz"], ["calm"]),
    track(4, ["poprock"], ["sad"]),
    track(5, ["jazz"], ["sad"]),
    track(6, ["rock"], ["calm", "happy"], ["guitar"]),
    track(7, ["pop"], ["happy"]),
    track(8, ["rock"], ["dark"]),
    track(9, ["rock"], ["dark"]),
    track(10, ["rock"], ["dark"]),
]


class FakeClient:
    """Stands in for genai.Client; counts calls."""

    def __init__(self, genres=(), moods=(), text=None, error=None):
        self.calls = []
        self._text = text if text is not None else json.dumps({"genres": list(genres), "moods": list(moods)})
        self._error = error
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(text=self._text)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("test attempted a real network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)


def ids(result):
    return [r.track.track_id for r in result.recommendations]


# ---- successful requests ---------------------------------------------------

def test_genre_and_mood_request():
    client = FakeClient(["rock"], ["calm"])
    result = run_pipeline("calm rock please", CATALOG, client=client)
    assert isinstance(result, RecommendationResult)
    assert result.intent == MusicIntent(("rock",), ("calm",))
    assert ids(result)[:2] == ["track_0000001", "track_0000006"]    # score 3, ID order
    assert result.recommendations[0].score == 3


def test_genre_only_request():
    result = run_pipeline("some jazz", CATALOG, client=FakeClient(["jazz"], []))
    assert result.intent == MusicIntent(("jazz",), ())
    assert ids(result) == ["track_0000003", "track_0000005"]
    assert all(r.score == 2 for r in result.recommendations)


def test_mood_only_request():
    result = run_pipeline("sad songs", CATALOG, client=FakeClient([], ["sad"]))
    assert result.intent == MusicIntent((), ("sad",))
    assert ids(result) == ["track_0000004", "track_0000005"]
    assert all(r.score == 1 for r in result.recommendations)


def test_returns_at_most_five_by_default():
    result = run_pipeline("rock", CATALOG, client=FakeClient(["rock"], []))
    assert len(result.recommendations) == 5
    assert ids(result) == ["track_0000001", "track_0000002", "track_0000006", "track_0000008", "track_0000009"]


def test_custom_k_and_fewer_matches_not_padded():
    assert len(run_pipeline("rock", CATALOG, client=FakeClient(["rock"], []), k=2).recommendations) == 2
    result = run_pipeline("jazz", CATALOG, client=FakeClient(["jazz"], []), k=10)
    assert len(result.recommendations) == 2


def test_original_query_preserved_exactly():
    query = "  Chill   ROCK, please!  "
    assert run_pipeline(query, CATALOG, client=FakeClient(["rock"], [])).query == query


def test_intent_preserved_as_validated_by_interpreter():
    result = run_pipeline("x", CATALOG, client=FakeClient([" ROCK ", "rock", "Poprock"], [" Calm"]))
    assert result.intent == MusicIntent(("rock", "poprock"), ("calm",))


def test_actual_v2_ranking_reused_unchanged():
    client = FakeClient(["rock", "poprock"], ["calm", "happy"])
    result = run_pipeline("x", CATALOG, client=client, k=10)
    direct = recommend_v2(CATALOG, genres=["rock", "poprock"], moods=["calm", "happy"], k=10)
    assert list(result.recommendations) == direct               # same objects' values: scores, tags, text
    assert [r.explanation for r in result.recommendations] == [r.explanation for r in direct]


def test_no_fabricated_metadata():
    result = run_pipeline("x", CATALOG, client=FakeClient(["rock"], ["calm"]), k=10)
    by_id = {t.track_id: t for t in CATALOG}
    for r in result.recommendations:
        assert r.track is by_id[r.track.track_id]               # the catalog's own record
        assert set(r.matched_genres) <= set(r.track.genres)
        assert set(r.matched_moods) <= set(r.track.moods)
        assert r.explanation.startswith("Matches your requested")


# ---- Gemini usage ----------------------------------------------------------

def test_gemini_called_exactly_once_per_request():
    client = FakeClient(["rock"], ["calm"])
    run_pipeline("calm rock", CATALOG, client=client)
    assert len(client.calls) == 1


def test_gemini_not_retried_after_invalid_response():
    client = FakeClient(text="not json")
    with pytest.raises(InvalidModelResponseError):
        run_pipeline("x", CATALOG, client=client)
    assert len(client.calls) == 1


def test_injected_interpreter_receives_arguments_once():
    calls = []

    def fake(query, vocabulary, *, client=None, model=None):
        calls.append((query, vocabulary, client, model))
        return MusicIntent(("rock",), ())

    sentinel = object()
    run_pipeline("hello", CATALOG, client=sentinel, model="m", interpreter=fake)
    assert len(calls) == 1
    query, vocab, client, model = calls[0]
    assert (query, client, model) == ("hello", sentinel, "m")
    assert vocab == catalog_vocabulary(CATALOG)


def test_default_interpreter_is_patchable_at_call_time(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "interpret_intent", lambda q, v, **kw: MusicIntent((), ("sad",)))
    assert run_pipeline("x", CATALOG).intent == MusicIntent((), ("sad",))


# ---- error contract --------------------------------------------------------

def test_missing_api_key_propagates():
    with pytest.raises(MissingApiKeyError):
        run_pipeline("calm rock", CATALOG)         # no client injected, no key in env


@pytest.mark.parametrize("error", [
    genai_errors.ServerError(504, {"error": {"message": "deadline", "status": "DEADLINE_EXCEEDED"}}),
    ConnectionError("down"),
])
def test_gemini_service_failure_propagates(error):
    with pytest.raises(GeminiServiceError):
        run_pipeline("x", CATALOG, client=FakeClient(error=error))


@pytest.mark.parametrize("text", ["nope", json.dumps({"genres": ["metalcore"], "moods": []}),
                                  json.dumps({"genres": ["calm"], "moods": []}), json.dumps({"genres": ["rock"]})])
def test_invalid_model_response_propagates_and_never_reaches_recommender(monkeypatch, text):
    monkeypatch.setattr(pipeline_mod, "recommend_v2", lambda *a, **k: pytest.fail("recommender was called"))
    with pytest.raises(InvalidModelResponseError):
        run_pipeline("x", CATALOG, client=FakeClient(text=text))


def test_empty_interpretation_propagates_without_substitute_preferences(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "recommend_v2", lambda *a, **k: pytest.fail("recommender was called"))
    with pytest.raises(NoConfidentInterpretationError):
        run_pipeline("asdf", CATALOG, client=FakeClient([], []))


@pytest.mark.parametrize("query", ["", "   ", None, 5, "a" * 501])
def test_invalid_query_propagates_without_calling_gemini(query):
    client = FakeClient(["rock"], [])
    with pytest.raises(InvalidQueryError):
        run_pipeline(query, CATALOG, client=client)
    assert client.calls == []


def test_all_intent_failures_are_intent_errors():
    for text in ("nope",):
        with pytest.raises(IntentError):
            run_pipeline("x", CATALOG, client=FakeClient(text=text))


def test_unsupported_tags_from_faulty_interpreter_become_recommendation_error():
    faulty = lambda q, v, **kw: MusicIntent(("zydeco",), ())
    with pytest.raises(RecommendationError) as err:
        run_pipeline("x", CATALOG, interpreter=faulty)
    assert err.value.__cause__ is not None
    assert not isinstance(err.value, IntentError)


def test_empty_intent_from_faulty_interpreter_becomes_recommendation_error():
    with pytest.raises(RecommendationError):
        run_pipeline("x", CATALOG, interpreter=lambda q, v, **kw: MusicIntent((), ()))


def test_no_match_returns_empty_result_if_recommender_finds_nothing(monkeypatch):
    # Unreachable with real vocabulary validation; verifies the pipeline passes an empty list through.
    monkeypatch.setattr(pipeline_mod, "recommend_v2", lambda *a, **k: [])
    result = run_pipeline("x", CATALOG, interpreter=lambda q, v, **kw: MusicIntent(("rock",), ()))
    assert result.recommendations == () and result.intent.genres == ("rock",)


@pytest.mark.parametrize("k", [0, -1, 21, True, 2.5, "5", None])
def test_invalid_k_rejected_before_calling_gemini(k):
    client = FakeClient(["rock"], [])
    with pytest.raises(ValueError):
        run_pipeline("x", CATALOG, client=client, k=k)
    assert client.calls == []


# ---- real catalog ----------------------------------------------------------

def test_real_catalog_end_to_end_with_fake_gemini():
    catalog = load_v2_catalog(REAL_CATALOG)
    vocab = catalog_vocabulary(catalog)
    client = FakeClient(["ambient"], ["relaxing"])
    result = run_pipeline("Relaxing ambient music for reading", catalog, vocab, client=client, k=10)
    assert len(client.calls) == 1
    assert len(result.recommendations) == 10
    assert [r.score for r in result.recommendations] == [3] * 10
    direct = recommend_v2(catalog, genres=["ambient"], moods=["relaxing"], k=10)
    assert list(result.recommendations) == direct
    assert all(r.track.track_url.startswith("http") for r in result.recommendations)


# ---- scope -----------------------------------------------------------------

def test_result_is_immutable():
    result = run_pipeline("x", CATALOG, client=FakeClient(["rock"], []))
    with pytest.raises(Exception):
        result.query = "other"
    assert isinstance(result.recommendations, tuple)


@pytest.mark.parametrize("path", ["src/pipeline.py", "app.py"])
def test_v1_module_is_not_used(path):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
               {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert "src.recommender" not in imported and "src.main" not in imported
