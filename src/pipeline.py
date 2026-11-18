"""Query -> Gemini intent -> deterministic V2 ranking.

    result = run_pipeline("calm ambient for reading", catalog)
    result.intent            # MusicIntent chosen by Gemini (validated)
    result.recommendations   # tuple[RankedRecommendation, ...], from recommend_v2

Guarantees:
* Gemini is called exactly once per request, and only to interpret the query.
* Scores, ordering, tags and explanations come unchanged from ``recommend_v2``;
  the pipeline adds nothing and invents no metadata.
* An invalid or empty interpretation is never replaced with other preferences.

Error contract (every failure is an exception; nothing is swallowed):
* ``IntentError`` subclasses from ``src.intent`` propagate unchanged:
  ``InvalidQueryError``, ``MissingApiKeyError``, ``GeminiServiceError``,
  ``InvalidModelResponseError``, ``NoConfidentInterpretationError``.
* ``RecommendationError`` wraps recommender validation failures
  (``UnsupportedTagError`` / ``EmptyPreferencesError``). With the real
  interpreter this is unreachable, because its output is already checked
  against the same vocabulary; it guards against a faulty injected interpreter.
* ``ValueError`` for an invalid ``k`` (a programming error, raised before
  Gemini is called).
* A valid request that scores no tracks returns an empty ``recommendations``
  tuple. This is also unreachable in practice, because every vocabulary tag
  occurs on at least one catalog track.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from src.intent import MusicIntent, interpret_intent
from src.v2_recommender import (
    DEFAULT_K,
    MAX_K,
    CatalogVocabulary,
    EmptyPreferencesError,
    MusicTrack,
    RankedRecommendation,
    UnsupportedTagError,
    catalog_vocabulary,
    recommend_v2,
)


class RecommendationError(Exception):
    """The recommender rejected the interpreted preferences."""


@dataclass(frozen=True)
class RecommendationResult:
    query: str                                        # exactly as received
    intent: MusicIntent                               # validated Gemini interpretation
    recommendations: tuple[RankedRecommendation, ...]  # as returned by recommend_v2


def run_pipeline(
    query: str,
    catalog: Sequence[MusicTrack],
    vocabulary: CatalogVocabulary | None = None,
    *,
    client: Any = None,
    model: str | None = None,
    interpreter: Callable[..., MusicIntent] | None = None,
    k: int = DEFAULT_K,
) -> RecommendationResult:
    """Interpret ``query`` once, then rank ``catalog`` deterministically.

    Args:
        query: the listener's request, as typed.
        catalog: tracks from ``load_v2_catalog``.
        vocabulary: precomputed ``catalog_vocabulary(catalog)``; derived if omitted.
        client / model: forwarded to the interpreter (see ``src.intent``).
        interpreter: replacement for ``interpret_intent`` (tests); called as
            ``interpreter(query, vocabulary, client=client, model=model)``.
        k: number of recommendations, 1..MAX_K.
    """
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= MAX_K:
        raise ValueError(f"k must be an integer between 1 and {MAX_K}, got {k!r}")
    if vocabulary is None:
        vocabulary = catalog_vocabulary(catalog)
    if interpreter is None:
        interpreter = interpret_intent  # looked up at call time, so tests can patch it

    intent = interpreter(query, vocabulary, client=client, model=model)

    try:
        ranked = recommend_v2(catalog, genres=intent.genres, moods=intent.moods, k=k)
    except (UnsupportedTagError, EmptyPreferencesError) as exc:
        raise RecommendationError("interpreted preferences were rejected by the recommender") from exc
    return RecommendationResult(query=query, intent=intent, recommendations=tuple(ranked))
