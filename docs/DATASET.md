# VibeMatch 2.0 Catalog: `data/jamendo_5000.csv`

A 5,000-track catalog of real music metadata, selected deterministically from the MTG-Jamendo Dataset. The V1 catalog (`data/songs.csv`) is unchanged.

An earlier 2,500-track build (`data/jamendo_2500.csv`) is no longer used by the application. It was produced by the same script and rules, and every one of its tracks is also in the 5,000-track catalog.

## Provenance

| | |
|---|---|
| Dataset | MTG-Jamendo Dataset |
| Project URL | https://github.com/MTG/mtg-jamendo-dataset |
| Maintainer | Music Technology Group, Universitat Pompeu Fabra; music from Jamendo |
| Source files | `data/raw_30s_cleantags.tsv` and `data/raw.meta.tsv` |
| Downloaded | 2026-11-17 from the `master` branch (upstream HEAD at that time: `cafd8e20c265ed84f1e61f1c875327971f43a62f`) |
| Metadata license | [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) |

SHA-256 of the exact files used:

```
e827347a505d6ed4e2ce213b8f1a83e5ac62e651ab7ddff426c7f04fa007d680  raw_30s_cleantags.tsv
bb1efa2876536cbe1a8b67db5dda15249ca144f0cff69e481b638803cbdc9aca  raw.meta.tsv
```

Only these two metadata files were downloaded. No audio, spectrograms, models or audio-feature archives were downloaded, and none are redistributed.

### Citation

> Bogdanov, D., Won M., Tovstogan P., Porter A., & Serra X. (2019). The MTG-Jamendo Dataset for Automatic Music Tagging. Machine Learning for Music Discovery Workshop, International Conference on Machine Learning (ICML 2019). http://hdl.handle.net/10230/42015

### License and permitted use

The upstream README states that the metadata is licensed under **CC BY-NC-SA 4.0** and that the dataset "is made available solely for non-commercial research and academic use"; any other use requires prior written authorization from Jamendo S.A. This catalog is derived from that metadata and inherits those terms:

- **Attribution:** credit the MTG-Jamendo Dataset (citation above) and Jamendo as the origin of titles, artists, tags and URLs.
- **NonCommercial:** use only for non-commercial research and academic purposes, such as this course project.
- **ShareAlike:** derivatives, including `data/jamendo_5000.csv`, must be shared under the same license.
- Individual audio files on Jamendo carry their own Creative Commons licenses. This project does not use or distribute audio.
- This repository's code is separate from the data and is not covered by the data license.

## Source file formats (verified by inspection)

Both files are UTF-8, tab-separated, with a header row. **Their schemas differ**:

| File | Columns | Notes |
|---|---|---|
| `raw_30s_cleantags.tsv` | `TRACK_ID, ARTIST_ID, ALBUM_ID, PATH, DURATION, TAGS` | 55,701 rows. `TAGS` is not one cell: each tag occupies its own trailing cell, so row width varies (6 to 17+ cells). Each cell is `<category>---<tag>`, where category is `genre`, `instrument` or `mood/theme`. |
| `raw.meta.tsv` | `TRACK_ID, ARTIST_ID, ALBUM_ID, TRACK_NAME, ARTIST_NAME, ALBUM_NAME, RELEASEDATE, URL` | 56,639 rows, exactly 8 columns each. Contains the titles, artist names and URLs the tag file lacks. |

Track IDs have the form `track_0000214` (zero-padded) in both files and are preserved unchanged.

**Parsing caveat:** `raw.meta.tsv` contains stray `"` characters inside titles (for example `track_0082365`). Default CSV quoting would merge roughly 100 rows into one, so the script parses with quoting disabled. Two rows (`track_1081574`, `track_1081578`) have 9 columns because of an empty artist field and are treated as malformed and excluded.

## Output format

`data/jamendo_5000.csv`: UTF-8, `\n` line endings, standard CSV quoting, one row per track.

| Column | Source | Notes |
|---|---|---|
| `track_id` | tags/meta `TRACK_ID` | Original Jamendo ID. |
| `title` | meta `TRACK_NAME` | Whitespace-stripped. |
| `artist` | meta `ARTIST_NAME` | Whitespace-stripped. |
| `genres` | tags, `genre---*` | JSON array of strings. |
| `moods` | tags, `mood/theme---*` | JSON array of strings. |
| `instruments` | tags, `instrument---*` | JSON array; `[]` when none. |
| `track_url` | meta `URL` | Copied verbatim (`http://www.jamendo.com/track/<n>`). |

**Multi-value fields** are JSON arrays encoded inside a CSV cell, for example `"[""rock"", ""indierock""]"` in the raw file. Read them with `json.loads(cell)`.

**Tag normalization:** strip surrounding whitespace, lowercase, remove duplicates, sort alphabetically. No synonyms are added or merged beyond what the upstream `*_cleantags` file already did. The upstream tags are single tokens with no spaces (`punkrock`, `easylistening`, `electroambient`), and they are preserved exactly as given. Tag categories are kept in separate columns.

The catalog contains **no** energy, tempo, valence, danceability or other numeric audio fields, and no audio descriptions. Nothing in it was measured from audio or produced by a model. Do not describe it as having measured energy or tempo.

## Eligibility rules

A source row must pass all of these. Each tag-file row is counted under the first rule it fails.

1. Row is well-formed (at least 5 columns; every tag cell is `category---tag` with a known category and nonempty tag).
2. Valid track ID (`track_<digits>`).
3. Not a duplicate: IDs that appear more than once in the tag file are excluded entirely (no row is arbitrarily preferred).
4. Metadata is not ambiguous (ID is not duplicated in the meta file).
5. A metadata row joins by track ID.
6. Nonempty title.
7. Nonempty artist.
8. Source URL present and shaped like `http(s)://...`. URLs are never constructed or repaired.
9. At least one genre tag.
10. At least one mood/theme tag.

### Results on the downloaded data

| Outcome | Rows |
|---|---:|
| Tag-file rows read | 55,701 |
| Excluded: malformed row | 0 |
| Excluded: invalid track ID | 0 |
| Excluded: duplicate track ID | 0 |
| Excluded: ambiguous duplicate metadata | 0 |
| Excluded: no metadata match | 2 |
| Excluded: empty title | 0 |
| Excluded: empty artist | 0 |
| Excluded: missing or invalid URL | 0 |
| Excluded: no genre tag | 318 |
| Excluded: no mood/theme tag | 33,669 |
| **Eligible** | **21,712** |
| **Selected** | **5,000** |

Mood/theme tags are the binding constraint: most Jamendo tracks have genre tags but no mood/theme tag. Separately, 938 meta rows have no tag-file record (the tag file covers only tracks longer than 30 s) and 2 meta rows were malformed.

## Selection method

Goal: 5,000 tracks spread across genres and artists, reproducible on any machine, independent of source row order. A fixed random seed would not guarantee that, so no random number generator is used.

1. **Group assignment.** Every eligible track is placed in exactly one group, its *rarest* genre (fewest eligible tracks; ties broken alphabetically). A multi-genre track therefore appears once, and rare genres are not absorbed by large ones such as `electronic`.
2. **Within-group order.** Tracks are sorted by `SHA-256(track_id)`, with the track ID as tie-breaker. This is a stable pseudo-random order, so the selection is not biased toward the earliest uploads.
3. **Round-robin.** Groups are visited in alphabetical order, one track per group per round. A track is skipped if its artist already has 5 selected tracks (case-insensitive name match).
4. Stop at 5,000 tracks, or when all groups are exhausted (in which case the shorter count is reported and nothing is fabricated).

**Feasibility at 5,000.** The 21,712 eligible tracks come from 1,707 distinct artists. With at most 5 tracks per artist, at most 5,887 tracks can be selected, so a target of 5,000 is reachable without changing any rule. Roughly 85% of that ceiling is used, so the artist cap now limits the selection more than it did at 2,500. A target above 5,887 would need a higher cap or fewer constraints, and the script would report the shorter count instead.

The output is sorted by track ID, and regenerating from the same input files produces a byte-identical CSV (verified, and covered by a test).

### Resulting catalog

| Statistic | Value |
|---|---:|
| Tracks | 5,000 |
| Unique artists | 1,538 |
| Max tracks per artist | 5 (663 artists are at the cap) |
| Artists with 1 / 2 / 3 / 4 / 5 tracks | 423 / 204 / 138 / 110 / 663 |
| Top-5 artists' share of catalog | 0.5% |
| Distinct genres / moods / instruments | 221 / 216 / 123 |
| Tracks with no instrument tags | 2,367 (47.3%) |
| Missing or invalid URLs | 0 |
| Mean genres / moods / instruments per track | 2.92 / 1.65 / 1.30 |

Top genres: electronic (1264), soundtrack (740), rock (705), ambient (693), pop (654), classical (384), dance (330), chillout (313), easylistening (304), indie (299).
Top moods: energetic (319), melodic (318), dark (296), love (276), happy (261), film (239), relaxing (231), epic (193), dream (185), emotional (181).
Top instruments: synthesizer (715), drums (607), piano (605), bass (582), guitar (489), electricguitar (479), acousticguitar (232), voice (219), computer (196), keyboard (187).

## Limitations

- **Tags are uploader-provided**, not expert-curated or audio-derived. They can be subjective, inconsistent, or missing.
- **Only tracks that carry a mood/theme tag are eligible** (about 39% of tracks with usable metadata), which skews the pool toward tracks whose uploaders chose to add mood tags.
- **Long tail of rare tags:** 19 genres appear on fewer than 5 selected tracks (a search for one of them can return fewer than 10 results), and the genre list includes near-duplicates (`rock`, `poprock`, `rockfrancais`) because upstream cleaning did not collapse them.
- **Instruments are optional** and absent for about half the tracks.
- **No numeric audio features.** There is no energy, tempo or valence, so ranking must rely on tags.
- **Tag format:** tags are lowercase single tokens (`electroambient`), not natural words. Mapping user language onto them is the job of the later intent step, which must validate against this vocabulary.
- **Duplicates by content:** nine artist+title pairs occur twice under different track IDs (re-uploads). Deduplication is by track ID only.
- **Links may be stale.** A `track_url` came from the source metadata and does not guarantee the track is still online or available in your region. URLs use `http://` as published upstream.
- **Genre mix is deliberately flattened** by the selection method. Frequencies in this catalog do not represent Jamendo's overall distribution.
- Titles and artists are mostly independent and international; 227 titles contain non-ASCII characters, and some content may be unsuitable for all audiences.

## Regeneration

Requires only Python 3.9+ and the standard library.

```bash
# 1. Download ONLY the two metadata files into a git-ignored cache
mkdir -p data/raw_cache
BASE=https://raw.githubusercontent.com/MTG/mtg-jamendo-dataset/master/data
curl -fL -o data/raw_cache/raw_30s_cleantags.tsv $BASE/raw_30s_cleantags.tsv
curl -fL -o data/raw_cache/raw.meta.tsv          $BASE/raw.meta.tsv

# 2. Verify checksums match the values above (the upstream master branch may change)
shasum -a 256 data/raw_cache/*.tsv

# 3. Build the catalog (no network needed)
python scripts/prepare_jamendo.py \
    --tags data/raw_cache/raw_30s_cleantags.tsv \
    --meta data/raw_cache/raw.meta.tsv \
    --output data/jamendo_5000.csv

# 4. Check
python -m pytest -q tests/test_jamendo_data.py
```

With the source files above, the generated catalog has SHA-256 `1702ac80da3c6deff50a5e57e8dbbca197842014ffd4d173c83eb80f2b928540` (`shasum -a 256 data/jamendo_5000.csv`).

If the checksums differ, the upstream metadata has changed and the output may differ from the committed catalog. The regeneration test will then fail by design. `data/raw_cache/` is in `.gitignore`; the raw files are not committed.
