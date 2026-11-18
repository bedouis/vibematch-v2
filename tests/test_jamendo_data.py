"""Tests for scripts/prepare_jamendo.py and the generated data/jamendo_2500.csv."""

import csv
import importlib.util
import json
import random
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "jamendo_2500.csv"

_spec = importlib.util.spec_from_file_location("prepare_jamendo", ROOT / "scripts" / "prepare_jamendo.py")
pj = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pj)

TAGS_HEADER = "TRACK_ID\tARTIST_ID\tALBUM_ID\tPATH\tDURATION\tTAGS"
META_HEADER = "TRACK_ID\tARTIST_ID\tALBUM_ID\tTRACK_NAME\tARTIST_NAME\tALBUM_NAME\tRELEASEDATE\tURL"


def write_tsv(path, header, rows):
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def tag_row(tid, *tags, artist="artist_000001"):
    return "\t".join([tid, artist, "album_000001", "1/1.mp3", "100.0", *tags])


def meta_row(tid, title="Title", artist="Artist", url=None):
    url = f"http://www.jamendo.com/track/{int(tid.split('_')[1])}" if url is None else url
    return "\t".join([tid, "artist_000001", "album_000001", title, artist, "Album", "2020-01-01", url])


@pytest.fixture
def sources(tmp_path):
    """Small fixture covering good rows plus each eligibility failure."""
    tags = write_tsv(tmp_path / "tags.tsv", TAGS_HEADER, [
        tag_row("track_0000001", "genre---rock", "genre---indierock", "mood/theme---happy",
                "mood/theme---energetic", "instrument---guitar", "instrument---drums"),
        tag_row("track_0000002", "genre---ambient", "mood/theme---calm"),         # no instruments
        tag_row("track_0000003", "genre---pop", "mood/theme---happy"),            # empty title
        tag_row("track_0000004", "genre---pop", "mood/theme---happy"),            # empty artist
        tag_row("track_0000005", "mood/theme---happy"),                           # no genre
        tag_row("track_0000006", "genre---pop"),                                  # no mood
        tag_row("track_0000007", "genre---pop", "mood/theme---happy"),            # no metadata
        tag_row("track_0000008", "genre---pop", "mood/theme---happy"),            # bad url
        tag_row("track_0000009", "genre---pop", "mood/theme---happy"),            # dup in tags
        tag_row("track_0000009", "genre---pop", "mood/theme---happy"),
        tag_row("track_0000010", "genre---pop", "bogus"),                         # malformed tag
        tag_row("track_0000011", "weird---pop", "mood/theme---happy"),            # unknown category
        "track_0000012\tartist_000001",                                           # too few columns
        tag_row("bad_id", "genre---pop", "mood/theme---happy"),                   # invalid id
        tag_row("track_0000013", " Genre---Rock ", "genre---rock", "mood/theme---Sad"),  # normalization
    ])
    meta = write_tsv(tmp_path / "meta.tsv", META_HEADER, [
        meta_row("track_0000001", "Song One", "Band A"),
        meta_row("track_0000002", "Song Two", "Band B"),
        meta_row("track_0000003", title=" "),
        meta_row("track_0000004", artist=""),
        meta_row("track_0000005"),
        meta_row("track_0000006"),
        meta_row("track_0000008", url="not a url"),
        meta_row("track_0000009"),
        meta_row("track_0000013", "  Padded  ", " Band C "),
        meta_row("track_0000099"),                                                # meta only
        "track_0000100\tonly\tthree",                                             # malformed meta
    ])
    return tags, meta


# ---- parsing ---------------------------------------------------------------

def test_tags_parsing_multiple_genres_moods_instruments(sources):
    rec = pj.parse_tags_file(sources[0])["records"]["track_0000001"]
    assert rec["genres"] == ["indierock", "rock"]
    assert rec["moods"] == ["energetic", "happy"]
    assert rec["instruments"] == ["drums", "guitar"]


def test_absent_instruments_become_empty_list(sources):
    assert pj.parse_tags_file(sources[0])["records"]["track_0000002"]["instruments"] == []


def test_tag_normalization_strip_lowercase_dedupe(sources):
    rec = pj.parse_tags_file(sources[0])["records"]["track_0000013"]
    assert rec["genres"] == ["rock"]
    assert rec["moods"] == ["sad"]


def test_malformed_tag_rows_and_invalid_ids_counted(sources):
    counts = pj.parse_tags_file(sources[0])["counts"]
    assert counts["malformed_row"] == 3      # 'bogus', unknown category, too few columns
    assert counts["invalid_track_id"] == 1
    assert counts["duplicate_track_id"] == 2


def test_meta_parsing_strips_and_flags_malformed(sources):
    meta = pj.parse_meta_file(sources[1])
    assert meta["records"]["track_0000013"] == {
        "title": "Padded", "artist": "Band C", "track_url": "http://www.jamendo.com/track/13"}
    assert meta["counts"]["malformed_row"] == 1
    assert "track_0000100" not in meta["records"]


def test_stray_quotes_do_not_merge_rows(tmp_path):
    meta = write_tsv(tmp_path / "m.tsv", META_HEADER, [
        meta_row("track_0000001", title='Say "hello'),
        meta_row("track_0000002", title="Next"),
    ])
    records = pj.parse_meta_file(meta)["records"]
    assert records["track_0000001"]["title"] == 'Say "hello'
    assert "track_0000002" in records


def test_header_mismatch_raises(tmp_path):
    bad = write_tsv(tmp_path / "bad.tsv", "A\tB", ["x\ty"])
    with pytest.raises(ValueError):
        pj.parse_tags_file(bad)
    with pytest.raises(ValueError):
        pj.parse_meta_file(bad)


def test_schemas_are_not_assumed_identical(sources):
    # Tag file: variable width; meta file: fixed width. Meta columns 3/4/7 hold title/artist/url.
    meta = pj.parse_meta_file(sources[1])["records"]["track_0000001"]
    assert set(meta) == {"title", "artist", "track_url"}


# ---- eligibility -----------------------------------------------------------

def test_eligibility_accounting(sources):
    tags, meta = pj.parse_tags_file(sources[0]), pj.parse_meta_file(sources[1])
    eligible, excl = pj.build_eligible(tags, meta)
    assert [r["track_id"] for r in eligible] == ["track_0000001", "track_0000002", "track_0000013"]
    assert excl["empty_title"] == 1
    assert excl["empty_artist"] == 1
    assert excl["no_genre_tag"] == 1
    assert excl["no_mood_tag"] == 1
    assert excl["no_metadata_match"] == 1
    assert excl["missing_or_invalid_url"] == 1
    assert excl["duplicate_track_id"] == 2
    assert excl["malformed_row"] == 3
    assert excl["invalid_track_id"] == 1
    # Every tag-file row is either eligible or counted exactly once.
    assert len(eligible) + sum(excl.values()) == tags["counts"]["rows_read"]


def test_join_uses_track_id_not_row_position(tmp_path):
    tags = write_tsv(tmp_path / "t.tsv", TAGS_HEADER, [
        tag_row("track_0000002", "genre---jazz", "mood/theme---calm"),
        tag_row("track_0000001", "genre---rock", "mood/theme---happy"),
    ])
    meta = write_tsv(tmp_path / "m.tsv", META_HEADER, [
        meta_row("track_0000001", "One", "A"),
        meta_row("track_0000002", "Two", "B"),
    ])
    eligible, _ = pj.build_eligible(pj.parse_tags_file(tags), pj.parse_meta_file(meta))
    by_id = {r["track_id"]: r for r in eligible}
    assert by_id["track_0000001"]["title"] == "One" and by_id["track_0000001"]["genres"] == ["rock"]
    assert by_id["track_0000002"]["title"] == "Two" and by_id["track_0000002"]["genres"] == ["jazz"]


def test_duplicate_metadata_ids_are_excluded(tmp_path):
    tags = write_tsv(tmp_path / "t.tsv", TAGS_HEADER, [tag_row("track_0000001", "genre---rock", "mood/theme---happy")])
    meta = write_tsv(tmp_path / "m.tsv", META_HEADER, [meta_row("track_0000001", "A"), meta_row("track_0000001", "B")])
    eligible, excl = pj.build_eligible(pj.parse_tags_file(tags), pj.parse_meta_file(meta))
    assert eligible == [] and excl["ambiguous_duplicate_metadata"] == 1


# ---- selection -------------------------------------------------------------

def synthetic_eligible(n=300):
    rng = random.Random(7)
    genres = ["rock", "pop", "jazz", "ambient", "folk", "metal"]
    recs = []
    for i in range(n):
        recs.append({
            "track_id": f"track_{i:07d}", "title": f"T{i}", "artist": f"Artist {i % 40}",
            "track_url": f"http://www.jamendo.com/track/{i}",
            "genres": sorted(rng.sample(genres, rng.randint(1, 3))),
            "moods": ["happy"], "instruments": [],
        })
    return recs


def test_selection_is_deterministic_and_order_independent():
    recs = synthetic_eligible()
    first = pj.select_diverse(recs, 100, 3)
    shuffled = recs[:]
    random.Random(1).shuffle(shuffled)
    second = pj.select_diverse(shuffled, 100, 3)
    assert [r["track_id"] for r in first] == [r["track_id"] for r in second]
    assert [r["track_id"] for r in first] == [r["track_id"] for r in pj.select_diverse(recs, 100, 3)]


def test_selection_has_no_duplicates_and_respects_artist_cap():
    chosen = pj.select_diverse(synthetic_eligible(), 70, 2)  # 40 artists x cap 2 = 80 max
    ids = [r["track_id"] for r in chosen]
    assert len(ids) == len(set(ids)) == 70
    assert max(Counter(r["artist"] for r in chosen).values()) <= 2


def test_selection_spreads_across_genres_and_not_first_rows():
    recs = synthetic_eligible()
    chosen = pj.select_diverse(recs, 60, 5)
    assert {g for r in chosen for g in r["genres"]} == {"rock", "pop", "jazz", "ambient", "folk", "metal"}
    assert [r["track_id"] for r in chosen] != [r["track_id"] for r in recs[:60]]


def test_multi_genre_track_assigned_to_rarest_genre():
    recs = [
        {"track_id": "track_0000001", "title": "x", "artist": "A", "track_url": "http://a/1",
         "genres": ["common", "rare"], "moods": ["m"], "instruments": []},
    ] + [
        {"track_id": f"track_{i:07d}", "title": "x", "artist": f"B{i}", "track_url": f"http://a/{i}",
         "genres": ["common"], "moods": ["m"], "instruments": []} for i in range(2, 30)
    ]
    # One round-robin pass over two groups ('common', 'rare') must include the rare-genre track.
    chosen = pj.select_diverse(recs, 2, 5)
    assert "track_0000001" in {r["track_id"] for r in chosen}


def test_returns_fewer_when_insufficient_without_fabrication():
    recs = synthetic_eligible(10)
    chosen = pj.select_diverse(recs, 50, 5)
    assert len(chosen) == 10
    assert {r["track_id"] for r in chosen} <= {r["track_id"] for r in recs}


# ---- serialization ---------------------------------------------------------

def test_csv_roundtrip_json_arrays(tmp_path):
    rec = {"track_id": "track_0000001", "title": 'He said "hi", ok', "artist": "Ünï, Band",
           "track_url": "http://www.jamendo.com/track/1",
           "genres": ["rock", "indierock"], "moods": ["happy"], "instruments": []}
    out = tmp_path / "o.csv"
    pj.write_catalog([rec], out)
    with open(out, newline="", encoding="utf-8") as fh:
        row = next(csv.DictReader(fh))
    assert list(row) == pj.OUTPUT_FIELDS
    assert row["title"] == rec["title"] and row["artist"] == rec["artist"]
    assert json.loads(row["genres"]) == ["rock", "indierock"]
    assert row["instruments"] == "[]"


def test_script_end_to_end_on_fixture(sources, tmp_path):
    out = tmp_path / "out.csv"
    result = pj.run(sources[0], sources[1], out, size=10, max_per_artist=5)
    assert result["eligible"] == 3 and result["selected"] == 3
    assert out.read_text(encoding="utf-8").splitlines()[0] == ",".join(pj.OUTPUT_FIELDS)


# ---- the real generated catalog -------------------------------------------

@pytest.fixture(scope="module")
def catalog():
    with open(CATALOG, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames, list(reader)


def test_catalog_schema(catalog):
    fields, _ = catalog
    assert fields == ["track_id", "title", "artist", "genres", "moods", "instruments", "track_url"]


def test_catalog_has_no_fabricated_numeric_columns(catalog):
    fields, _ = catalog
    forbidden = {"energy", "tempo", "valence", "danceability", "acousticness", "bpm", "loudness"}
    assert not forbidden & {f.lower() for f in fields}


def test_catalog_size_and_unique_ids(catalog):
    _, rows = catalog
    ids = [r["track_id"] for r in rows]
    assert len(rows) == 2500
    assert len(set(ids)) == 2500
    assert ids == sorted(ids)
    assert all(pj.TRACK_ID_RE.match(i) for i in ids)


def test_catalog_required_fields_and_tags(catalog):
    _, rows = catalog
    for r in rows:
        assert r["title"].strip() and r["title"] == r["title"].strip()
        assert r["artist"].strip() and r["artist"] == r["artist"].strip()
        assert pj.URL_RE.match(r["track_url"])
        genres, moods, instruments = (json.loads(r[k]) for k in ("genres", "moods", "instruments"))
        assert genres and moods
        for tags in (genres, moods, instruments):
            assert isinstance(tags, list) and len(tags) == len(set(tags))
            assert all(isinstance(t, str) and t == t.strip().lower() and t for t in tags)


def test_catalog_url_matches_track_id(catalog):
    _, rows = catalog
    for r in rows:
        assert r["track_url"].rstrip("/").endswith("/" + str(int(r["track_id"].split("_")[1])))


def test_catalog_artist_cap_and_diversity(catalog):
    _, rows = catalog
    artists = Counter(r["artist"].casefold() for r in rows)
    assert max(artists.values()) <= pj.DEFAULT_MAX_PER_ARTIST
    assert len(artists) >= 500
    genres = {g for r in rows for g in json.loads(r["genres"])}
    assert len(genres) >= 100


def test_catalog_regeneration_matches_if_sources_cached(tmp_path):
    tags, meta = ROOT / "data/raw_cache/raw_30s_cleantags.tsv", ROOT / "data/raw_cache/raw.meta.tsv"
    if not (tags.is_file() and meta.is_file()):
        pytest.skip("raw metadata cache not present")
    out = tmp_path / "regen.csv"
    pj.run(tags, meta, out, pj.DEFAULT_SIZE, pj.DEFAULT_MAX_PER_ARTIST)
    assert out.read_bytes() == CATALOG.read_bytes()
