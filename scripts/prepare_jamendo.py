#!/usr/bin/env python3
"""Build data/jamendo_5000.csv from official MTG-Jamendo metadata.

Inputs (both from https://github.com/MTG/mtg-jamendo-dataset, directory data/):
  raw_30s_cleantags.tsv  TRACK_ID ARTIST_ID ALBUM_ID PATH DURATION TAGS...
                         (variable number of trailing cells, each
                         "<category>---<tag>", category in genre /
                         instrument / mood/theme)
  raw.meta.tsv           TRACK_ID ARTIST_ID ALBUM_ID TRACK_NAME ARTIST_NAME
                         ALBUM_NAME RELEASEDATE URL   (exactly 8 columns)

Both files are tab-separated with a header row and are parsed with
quoting disabled: the files contain stray double quotes inside titles, and
default CSV quoting would merge many rows into one.

Standard library only. No network access is needed once the two files exist.

Usage:
  python scripts/prepare_jamendo.py \
      --tags data/raw_cache/raw_30s_cleantags.tsv \
      --meta data/raw_cache/raw.meta.tsv \
      --output data/jamendo_5000.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TAGS_HEADER = ["TRACK_ID", "ARTIST_ID", "ALBUM_ID", "PATH", "DURATION", "TAGS"]
META_HEADER = [
    "TRACK_ID", "ARTIST_ID", "ALBUM_ID", "TRACK_NAME",
    "ARTIST_NAME", "ALBUM_NAME", "RELEASEDATE", "URL",
]
TAG_SEPARATOR = "---"
CATEGORY_FIELDS = {"genre": "genres", "mood/theme": "moods", "instrument": "instruments"}
TAGS_FIRST_TAG_COLUMN = 5  # zero-based index of the first tag cell
META_COLUMNS = 8

OUTPUT_FIELDS = ["track_id", "title", "artist", "genres", "moods", "instruments", "track_url"]

TRACK_ID_RE = re.compile(r"^track_\d+$")
URL_RE = re.compile(r"^https?://\S+$")

DEFAULT_SIZE = 5000
DEFAULT_MAX_PER_ARTIST = 5

# Exclusion reasons, listed in the order the rules are applied. Each source
# record is counted under the FIRST rule it fails, so counts sum exactly.
EXCLUSION_ORDER = [
    "malformed_row",
    "invalid_track_id",
    "duplicate_track_id",
    "ambiguous_duplicate_metadata",
    "no_metadata_match",
    "empty_title",
    "empty_artist",
    "missing_or_invalid_url",
    "no_genre_tag",
    "no_mood_tag",
]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def normalize_tag(value: str) -> str:
    """Strip whitespace and lowercase. Multiword tags are otherwise untouched."""
    return value.strip().lower()


def _read_rows(path: Path, expected_header: list[str]) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader, None)
        if header is None or [h.strip() for h in header[: len(expected_header)]] != expected_header:
            raise ValueError(
                f"{path}: unexpected header {header!r}; expected it to start with {expected_header!r}"
            )
        return [row for row in reader if any(cell.strip() for cell in row)]


def _parse_tag_cells(cells: list[str]) -> dict[str, list[str]] | None:
    """Return {'genres': [...], 'moods': [...], 'instruments': [...]} or None if malformed."""
    result: dict[str, set[str]] = {field: set() for field in CATEGORY_FIELDS.values()}
    for cell in cells:
        if not cell.strip():
            continue  # tolerate an empty trailing cell
        if cell.count(TAG_SEPARATOR) != 1:
            return None
        category, tag = (normalize_tag(part) for part in cell.split(TAG_SEPARATOR))
        field = CATEGORY_FIELDS.get(category)
        if field is None or not tag:
            return None
        result[field].add(tag)
    return {field: sorted(tags) for field, tags in result.items()}


def parse_tags_file(path: Path) -> dict:
    """Parse raw_30s_cleantags.tsv.

    Returns {'records': {id: {genres, moods, instruments}},
             'duplicate_ids': set, 'counts': Counter,
             'invalid_ids': int, ...}.
    Rows are classified, not dropped silently: see counts.
    """
    rows = _read_rows(path, TAGS_HEADER)
    counts: Counter = Counter()
    seen: Counter = Counter()
    parsed: dict[str, dict] = {}
    # Collect (id, tags) per valid row first so duplicates can be dropped entirely.
    for row in rows:
        counts["rows_read"] += 1
        if len(row) < TAGS_FIRST_TAG_COLUMN:
            counts["malformed_row"] += 1
            continue
        track_id = row[0].strip()
        if not TRACK_ID_RE.match(track_id):
            counts["invalid_track_id"] += 1
            continue
        tags = _parse_tag_cells(row[TAGS_FIRST_TAG_COLUMN:])
        if tags is None:
            counts["malformed_row"] += 1
            continue
        seen[track_id] += 1
        parsed[track_id] = tags
    duplicate_ids = {tid for tid, n in seen.items() if n > 1}
    for tid in duplicate_ids:
        counts["duplicate_track_id"] += seen[tid]  # every occurrence is excluded
        del parsed[tid]
    return {"records": parsed, "duplicate_ids": duplicate_ids, "counts": counts}


def parse_meta_file(path: Path) -> dict:
    """Parse raw.meta.tsv (exactly 8 columns per row)."""
    rows = _read_rows(path, META_HEADER)
    counts: Counter = Counter()
    seen: Counter = Counter()
    parsed: dict[str, dict] = {}
    for row in rows:
        counts["rows_read"] += 1
        if len(row) != META_COLUMNS:
            counts["malformed_row"] += 1
            continue
        track_id = row[0].strip()
        if not TRACK_ID_RE.match(track_id):
            counts["invalid_track_id"] += 1
            continue
        seen[track_id] += 1
        parsed[track_id] = {
            "title": row[3].strip(),
            "artist": row[4].strip(),
            "track_url": row[7].strip(),
        }
    duplicate_ids = {tid for tid, n in seen.items() if n > 1}
    for tid in duplicate_ids:
        del parsed[tid]
    return {"records": parsed, "duplicate_ids": duplicate_ids, "counts": counts}


# --------------------------------------------------------------------------
# Eligibility
# --------------------------------------------------------------------------

def build_eligible(tags: dict, meta: dict) -> tuple[list[dict], Counter]:
    """Join the two sources by track ID and apply the eligibility rules.

    Returns (eligible_records, exclusions) where exclusions maps each reason
    in EXCLUSION_ORDER to the number of tag-file rows it removed.
    """
    exclusions: Counter = Counter()
    for reason in ("malformed_row", "invalid_track_id", "duplicate_track_id"):
        exclusions[reason] += tags["counts"].get(reason, 0)

    eligible: list[dict] = []
    for track_id, tag_rec in tags["records"].items():
        if track_id in meta["duplicate_ids"]:
            exclusions["ambiguous_duplicate_metadata"] += 1
            continue
        meta_rec = meta["records"].get(track_id)
        if meta_rec is None:
            exclusions["no_metadata_match"] += 1
        elif not meta_rec["title"]:
            exclusions["empty_title"] += 1
        elif not meta_rec["artist"]:
            exclusions["empty_artist"] += 1
        elif not URL_RE.match(meta_rec["track_url"]):
            exclusions["missing_or_invalid_url"] += 1
        elif not tag_rec["genres"]:
            exclusions["no_genre_tag"] += 1
        elif not tag_rec["moods"]:
            exclusions["no_mood_tag"] += 1
        else:
            eligible.append({"track_id": track_id, **meta_rec, **tag_rec})
    eligible.sort(key=lambda r: r["track_id"])
    return eligible, exclusions


# --------------------------------------------------------------------------
# Diverse deterministic selection
# --------------------------------------------------------------------------

def _stable_key(track_id: str) -> tuple[str, str]:
    """Order-independent pseudo-random rank; the track ID breaks any tie."""
    return hashlib.sha256(track_id.encode("utf-8")).hexdigest(), track_id


def _artist_key(record: dict) -> str:
    return record["artist"].casefold()


def select_diverse(eligible: list[dict], size: int, max_per_artist: int) -> list[dict]:
    """Pick up to `size` tracks, spread across genres and artists.

    1. Each track is assigned to exactly ONE group: its rarest genre
       (fewest eligible tracks; ties broken alphabetically). A multi-genre
       track therefore appears in one group only, and rare genres are not
       swallowed by large ones.
    2. Within a group, tracks are ordered by SHA-256(track_id), so the
       order is pseudo-random but identical on every run and independent of
       the order of the source rows.
    3. Groups are visited round-robin in alphabetical order, taking one track
       per group per round, skipping any track whose artist already has
       `max_per_artist` selected tracks.
    4. Stop at `size` tracks or when every group is exhausted.

    The result is sorted by track ID. If fewer than `size` tracks can be
    selected, the shorter list is returned; nothing is fabricated.
    """
    genre_freq: Counter = Counter()
    for rec in eligible:
        genre_freq.update(rec["genres"])

    groups: dict[str, list[dict]] = {}
    for rec in eligible:
        primary = min(rec["genres"], key=lambda g: (genre_freq[g], g))
        groups.setdefault(primary, []).append(rec)
    for members in groups.values():
        members.sort(key=lambda r: _stable_key(r["track_id"]))

    group_names = sorted(groups)
    cursor = {name: 0 for name in group_names}
    artist_counts: Counter = Counter()
    selected: list[dict] = []

    while len(selected) < size:
        progressed = False
        for name in group_names:
            if len(selected) >= size:
                break
            members = groups[name]
            i = cursor[name]
            while i < len(members) and artist_counts[_artist_key(members[i])] >= max_per_artist:
                i += 1  # artist already at its cap: skip permanently
            if i < len(members):
                rec = members[i]
                selected.append(rec)
                artist_counts[_artist_key(rec)] += 1
                i += 1
                progressed = True
            cursor[name] = i
        if not progressed:
            break

    selected.sort(key=lambda r: r["track_id"])
    return selected


# --------------------------------------------------------------------------
# Output and reporting
# --------------------------------------------------------------------------

def write_catalog(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for rec in records:
            writer.writerow({
                "track_id": rec["track_id"],
                "title": rec["title"],
                "artist": rec["artist"],
                "genres": json.dumps(rec["genres"], ensure_ascii=False),
                "moods": json.dumps(rec["moods"], ensure_ascii=False),
                "instruments": json.dumps(rec["instruments"], ensure_ascii=False),
                "track_url": rec["track_url"],
            })


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize(records: list[dict], top: int = 10) -> dict:
    artists = Counter(r["artist"].casefold() for r in records)
    genres = Counter(g for r in records for g in r["genres"])
    moods = Counter(m for r in records for m in r["moods"])
    instruments = Counter(i for r in records for i in r["instruments"])
    n = len(records)
    top_artist, top_artist_n = artists.most_common(1)[0] if artists else ("", 0)
    return {
        "tracks": n,
        "unique_artists": len(artists),
        "distinct_genres": len(genres),
        "distinct_moods": len(moods),
        "distinct_instruments": len(instruments),
        "top_genres": genres.most_common(top),
        "top_moods": moods.most_common(top),
        "top_instruments": instruments.most_common(top),
        "max_tracks_per_artist": top_artist_n,
        "most_common_artist": top_artist,
        "top5_artist_share": (sum(c for _, c in artists.most_common(5)) / n) if n else 0.0,
        "tracks_without_instruments": sum(1 for r in records if not r["instruments"]),
        "missing_urls": sum(1 for r in records if not URL_RE.match(r["track_url"])),
    }


def run(tags_path: Path, meta_path: Path, output_path: Path, size: int, max_per_artist: int) -> dict:
    tags = parse_tags_file(tags_path)
    meta = parse_meta_file(meta_path)
    eligible, exclusions = build_eligible(tags, meta)
    selected = select_diverse(eligible, size, max_per_artist)
    write_catalog(selected, output_path)
    return {
        "tags_rows": tags["counts"]["rows_read"],
        "meta_rows": meta["counts"]["rows_read"],
        "meta_malformed_rows": meta["counts"].get("malformed_row", 0),
        "meta_duplicate_ids": len(meta["duplicate_ids"]),
        "meta_without_tags": len(set(meta["records"]) - set(tags["records"]) - tags["duplicate_ids"]),
        "exclusions": {reason: exclusions.get(reason, 0) for reason in EXCLUSION_ORDER},
        "eligible": len(eligible),
        "selected": len(selected),
        "summary": summarize(selected),
    }


def print_report(result: dict, tags_path: Path, meta_path: Path, output_path: Path) -> None:
    print(f"tags file : {tags_path}  sha256={sha256_file(tags_path)}")
    print(f"meta file : {meta_path}  sha256={sha256_file(meta_path)}")
    print(f"tag rows read: {result['tags_rows']}   meta rows read: {result['meta_rows']}")
    print(f"meta malformed rows: {result['meta_malformed_rows']}   "
          f"meta duplicate ids: {result['meta_duplicate_ids']}   "
          f"meta ids with no tag record: {result['meta_without_tags']}")
    print("exclusions (tag-file rows, first failing rule):")
    for reason, n in result["exclusions"].items():
        print(f"  {reason:30s} {n}")
    print(f"eligible: {result['eligible']}")
    print(f"selected: {result['selected']}  -> {output_path}")
    s = result["summary"]
    print(f"unique artists: {s['unique_artists']}   distinct genres: {s['distinct_genres']}   "
          f"moods: {s['distinct_moods']}   instruments: {s['distinct_instruments']}")
    print(f"max tracks per artist: {s['max_tracks_per_artist']} ({s['most_common_artist']})   "
          f"top-5 artist share: {s['top5_artist_share']:.1%}")
    print(f"tracks without instruments: {s['tracks_without_instruments']}   missing urls: {s['missing_urls']}")
    for label, key in (("genres", "top_genres"), ("moods", "top_moods"), ("instruments", "top_instruments")):
        print(f"top {label}: " + ", ".join(f"{t} ({c})" for t, c in s[key]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tags", type=Path, default=REPO_ROOT / "data/raw_cache/raw_30s_cleantags.tsv")
    parser.add_argument("--meta", type=Path, default=REPO_ROOT / "data/raw_cache/raw.meta.tsv")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "data/jamendo_5000.csv")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--max-per-artist", type=int, default=DEFAULT_MAX_PER_ARTIST)
    args = parser.parse_args(argv)

    for path in (args.tags, args.meta):
        if not path.is_file():
            print(f"error: source file not found: {path}\n"
                  f"       see docs/DATASET.md for download instructions", file=sys.stderr)
            return 1
    result = run(args.tags, args.meta, args.output, args.size, args.max_per_artist)
    print_report(result, args.tags, args.meta, args.output)
    if result["selected"] < args.size:
        print(f"warning: only {result['selected']} tracks selected (requested {args.size})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
