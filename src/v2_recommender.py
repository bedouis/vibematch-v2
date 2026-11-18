"""VibeMatch 2.0 recommendation engine over the MTG-Jamendo catalog.

A small, deterministic, tag-based ranker. It is a simplified descendant of
the V1 scoring rules (see src/recommender.py, which is unchanged):

    genre category matched  -> +2
    mood category matched   -> +1        (maximum score: 3)

Each category is scored once, no matter how many requested tags match inside
it (matching within a category is OR). Matching is exact on normalized tags
(strip + lowercase); no synonyms or fuzzy matching are applied, so ``rock``
and ``poprock`` are different tags. The catalog has no energy, tempo or
valence data and this module never produces any.

No network access, randomness, or third-party dependencies.

Validation contract for requested tags
--------------------------------------
* ``recommend_v2`` raises ``EmptyPreferencesError`` if no genre or mood is
  requested (after normalization), rather than returning arbitrary tracks.
* It raises ``UnsupportedTagError`` if any requested tag is absent from the
  catalog vocabulary. Tags are never silently remapped or dropped.
* A request that is valid but matches nothing returns ``[]``.
* A caller (for example a future LLM layer) can inspect the vocabulary with
  ``catalog_vocabulary`` and pre-filter with ``split_supported_tags``.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

GENRE_POINTS = 2
MOOD_POINTS = 1
MAX_SCORE = GENRE_POINTS + MOOD_POINTS

DEFAULT_K = 5
MAX_K = 20  # upper bound suited to a results page

CATALOG_FIELDS = ["track_id", "title", "artist", "genres", "moods", "instruments", "track_url"]

_TRACK_ID_RE = re.compile(r"^track_(\d+)$")
_URL_RE = re.compile(r"^https?://\S+$")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class CatalogError(ValueError):
    """The catalog file is missing fields or contains invalid records."""


class EmptyPreferencesError(ValueError):
    """No genre or mood was requested."""


class UnsupportedTagError(ValueError):
    """One or more requested tags do not exist in the catalog."""

    def __init__(self, unsupported_genres: Sequence[str], unsupported_moods: Sequence[str]):
        self.unsupported_genres = tuple(unsupported_genres)
        self.unsupported_moods = tuple(unsupported_moods)
        parts = []
        if self.unsupported_genres:
            parts.append(f"genres {list(self.unsupported_genres)}")
        if self.unsupported_moods:
            parts.append(f"moods {list(self.unsupported_moods)}")
        super().__init__("Not in catalog vocabulary: " + "; ".join(parts))


# --------------------------------------------------------------------------
# Data models
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class MusicTrack:
    """One catalog record. Tags are normalized, deduplicated, sorted tuples."""
    track_id: str
    title: str
    artist: str
    genres: tuple[str, ...]
    moods: tuple[str, ...]
    instruments: tuple[str, ...]  # may be empty
    track_url: str


@dataclass(frozen=True)
class RankedRecommendation:
    """A scored track plus the evidence behind the score."""
    track: MusicTrack
    score: int
    matched_genres: tuple[str, ...]  # requested genres this track actually has
    matched_moods: tuple[str, ...]   # requested moods this track actually has
    explanation: str


@dataclass(frozen=True)
class CatalogVocabulary:
    genres: frozenset[str]
    moods: frozenset[str]


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

def normalize_tag(tag: str) -> str:
    """Strip surrounding whitespace and lowercase. Nothing else is changed."""
    return tag.strip().lower()


def _normalize_requested(tags: Iterable[str], label: str) -> tuple[str, ...]:
    if isinstance(tags, (str, bytes)):
        raise TypeError(f"{label} must be a sequence of tags, not a single string")
    result: dict[str, None] = {}  # ordered dedupe
    for tag in tags:
        if not isinstance(tag, str):
            raise TypeError(f"{label} entries must be strings, got {type(tag).__name__}")
        norm = normalize_tag(tag)
        if norm:
            result[norm] = None
    return tuple(result)


# --------------------------------------------------------------------------
# Catalog loading
# --------------------------------------------------------------------------

def _parse_tag_array(cell: str, field: str, where: str, *, required: bool) -> tuple[str, ...]:
    try:
        value = json.loads(cell)
    except json.JSONDecodeError as exc:
        raise CatalogError(f"{where}: {field} is not valid JSON ({exc.msg})") from None
    if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
        raise CatalogError(f"{where}: {field} must be a JSON array of strings")
    tags = tuple(sorted({normalize_tag(t) for t in value if normalize_tag(t)}))
    if required and not tags:
        raise CatalogError(f"{where}: {field} must contain at least one tag")
    return tags


def load_v2_catalog(path: str | Path) -> list[MusicTrack]:
    """Load and validate the Jamendo catalog CSV (see docs/DATASET.md).

    ``genres`` and ``moods`` must be nonempty JSON arrays; ``instruments`` may
    be ``[]``. IDs stay strings. Raises ``CatalogError`` on any invalid record,
    naming the file line.
    """
    tracks: list[MusicTrack] = []
    seen_ids: set[str] = set()
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != CATALOG_FIELDS:
            raise CatalogError(f"{path}: expected columns {CATALOG_FIELDS}, found {reader.fieldnames}")
        for row in reader:
            where = f"{path} line {reader.line_num}"
            if None in row or any(v is None for v in row.values()):
                raise CatalogError(f"{where}: wrong number of columns")
            track_id = row["track_id"].strip()
            if not _TRACK_ID_RE.match(track_id):
                raise CatalogError(f"{where}: invalid track_id {track_id!r}")
            if track_id in seen_ids:
                raise CatalogError(f"{where}: duplicate track_id {track_id}")
            seen_ids.add(track_id)
            title, artist, url = row["title"].strip(), row["artist"].strip(), row["track_url"].strip()
            if not title:
                raise CatalogError(f"{where}: empty title")
            if not artist:
                raise CatalogError(f"{where}: empty artist")
            if not _URL_RE.match(url):
                raise CatalogError(f"{where}: invalid track_url {url!r}")
            tracks.append(MusicTrack(
                track_id=track_id,
                title=title,
                artist=artist,
                genres=_parse_tag_array(row["genres"], "genres", where, required=True),
                moods=_parse_tag_array(row["moods"], "moods", where, required=True),
                instruments=_parse_tag_array(row["instruments"], "instruments", where, required=False),
                track_url=url,
            ))
    return tracks


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

def catalog_vocabulary(catalog: Iterable[MusicTrack]) -> CatalogVocabulary:
    """All genre and mood tags that occur in the catalog."""
    genres: set[str] = set()
    moods: set[str] = set()
    for track in catalog:
        genres.update(track.genres)
        moods.update(track.moods)
    return CatalogVocabulary(frozenset(genres), frozenset(moods))


def split_supported_tags(
    requested: Iterable[str], supported: Iterable[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Normalize ``requested`` and split it into (supported, unsupported).

    Does not map or guess: a tag is supported only if its normalized form is
    exactly in ``supported``.
    """
    supported_set = set(supported)
    norm = _normalize_requested(requested, "requested tags")
    return (tuple(t for t in norm if t in supported_set),
            tuple(t for t in norm if t not in supported_set))


# --------------------------------------------------------------------------
# Scoring, explanation, ranking
# --------------------------------------------------------------------------

def _join(words: Sequence[str]) -> str:
    if len(words) <= 2:
        return " and ".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def build_explanation(matched_genres: Sequence[str], matched_moods: Sequence[str]) -> str:
    """Fixed-template sentence built only from tags that actually matched."""
    parts = []
    if matched_genres:
        parts.append(f"{_join(matched_genres)} {'genre' if len(matched_genres) == 1 else 'genres'}")
    if matched_moods:
        parts.append(f"{_join(matched_moods)} {'mood' if len(matched_moods) == 1 else 'moods'}")
    if not parts:
        raise ValueError("cannot explain a track with no matches")
    return "Matches your requested " + " and ".join(parts) + "."


def score_track(
    track: MusicTrack, genres: Sequence[str], moods: Sequence[str]
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    """Return (score, matched_genres, matched_moods) for already-normalized requests."""
    track_genres, track_moods = set(track.genres), set(track.moods)
    matched_genres = tuple(g for g in genres if g in track_genres)
    matched_moods = tuple(m for m in moods if m in track_moods)
    score = (GENRE_POINTS if matched_genres else 0) + (MOOD_POINTS if matched_moods else 0)
    return score, matched_genres, matched_moods


def _id_sort_key(track_id: str) -> tuple[int, str]:
    match = _TRACK_ID_RE.match(track_id)
    return (int(match.group(1)) if match else 0, track_id)


def _validate_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int):
        raise TypeError(f"k must be an integer, got {type(k).__name__}")
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be between 1 and {MAX_K}, got {k}")


def recommend_v2(
    catalog: Sequence[MusicTrack],
    *,
    genres: Iterable[str] = (),
    moods: Iterable[str] = (),
    k: int = DEFAULT_K,
) -> list[RankedRecommendation]:
    """Rank catalog tracks for requested genres and moods.

    Returns at most ``k`` tracks with a positive score, ordered by score
    descending then track ID ascending. Returns fewer (or ``[]``) when fewer
    tracks match; unrelated tracks are never added to fill ``k``.

    Raises:
        TypeError / ValueError: invalid ``k`` or malformed tag arguments.
        EmptyPreferencesError: no genre and no mood requested.
        UnsupportedTagError: a requested tag is not in the catalog vocabulary.
    """
    _validate_k(k)
    req_genres = _normalize_requested(genres, "genres")
    req_moods = _normalize_requested(moods, "moods")
    if not req_genres and not req_moods:
        raise EmptyPreferencesError("request at least one genre or mood")

    vocab = catalog_vocabulary(catalog)
    bad_genres = tuple(g for g in req_genres if g not in vocab.genres)
    bad_moods = tuple(m for m in req_moods if m not in vocab.moods)
    if bad_genres or bad_moods:
        raise UnsupportedTagError(bad_genres, bad_moods)

    scored = []
    for track in catalog:
        score, matched_genres, matched_moods = score_track(track, req_genres, req_moods)
        if score > 0:
            scored.append((score, track, matched_genres, matched_moods))
    scored.sort(key=lambda item: (-item[0], _id_sort_key(item[1].track_id)))

    return [
        RankedRecommendation(
            track=track,
            score=score,
            matched_genres=matched_genres,
            matched_moods=matched_moods,
            explanation=build_explanation(matched_genres, matched_moods),
        )
        for score, track, matched_genres, matched_moods in scored[:k]
    ]
