import dataclasses
import random
from pathlib import Path

import pytest

from src import v2_recommender as v2
from src.v2_recommender import (
    CatalogError,
    EmptyPreferencesError,
    MusicTrack,
    RankedRecommendation,
    UnsupportedTagError,
    build_explanation,
    catalog_vocabulary,
    load_v2_catalog,
    recommend_v2,
    split_supported_tags,
)

REAL_CATALOG = Path(__file__).resolve().parent.parent / "data" / "jamendo_2500.csv"
HEADER = "track_id,title,artist,genres,moods,instruments,track_url\n"


def track(n, genres=(), moods=(), instruments=(), artist="A", title=None):
    return MusicTrack(
        track_id=f"track_{n:07d}", title=title or f"Song {n}", artist=artist,
        genres=tuple(sorted(genres)), moods=tuple(sorted(moods)),
        instruments=tuple(sorted(instruments)),
        track_url=f"http://www.jamendo.com/track/{n}",
    )


@pytest.fixture
def catalog():
    return [
        track(1, ["rock"], ["calm"]),                       # both
        track(2, ["rock", "poprock"], ["happy"]),           # two requested genres
        track(3, ["jazz"], ["calm"]),                       # mood only
        track(4, ["poprock"], ["sad"]),                     # genre only
        track(5, ["jazz"], ["sad"]),                        # nothing for rock/calm
        track(6, ["rock"], ["calm", "happy"], ["guitar"]),  # both, multiple moods
        track(7, ["pop"], ["happy", "calm"]),               # mood only, two moods
    ]


def ids(results):
    return [r.track.track_id for r in results]


def write_csv(tmp_path, *rows, header=HEADER):
    path = tmp_path / "c.csv"
    path.write_text(header + "".join(r + "\n" for r in rows), encoding="utf-8")
    return path


GOOD = 'track_0000001,Title,Artist,"[""Rock"", "" indie ""]","[""calm""]",[],http://www.jamendo.com/track/1'


# ---- loading ---------------------------------------------------------------

def test_load_valid_row_normalizes_and_keeps_string_id(tmp_path):
    (t,) = load_v2_catalog(write_csv(tmp_path, GOOD))
    assert t.track_id == "track_0000001" and isinstance(t.track_id, str)
    assert t.genres == ("indie", "rock")          # stripped, lowercased, sorted
    assert t.moods == ("calm",)
    assert t.instruments == ()                    # empty list is valid
    assert t.track_url == "http://www.jamendo.com/track/1"


def test_models_are_immutable(tmp_path):
    (t,) = load_v2_catalog(write_csv(tmp_path, GOOD))
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.title = "x"


def test_model_has_no_audio_feature_fields():
    names = {f.name for f in dataclasses.fields(MusicTrack)}
    assert names == {"track_id", "title", "artist", "genres", "moods", "instruments", "track_url"}
    assert not names & {"energy", "tempo", "tempo_bpm", "valence"}


@pytest.mark.parametrize("row,fragment", [
    ('bad_id,T,A,"[""rock""]","[""calm""]",[],http://x/1', "invalid track_id"),
    ('track_0000001,,A,"[""rock""]","[""calm""]",[],http://x/1', "empty title"),
    ('track_0000001,T,,"[""rock""]","[""calm""]",[],http://x/1', "empty artist"),
    ('track_0000001,T,A,"[""rock""]","[""calm""]",[],ftp://x/1', "invalid track_url"),
    ('track_0000001,T,A,[],"[""calm""]",[],http://x/1', "genres must contain"),
    ('track_0000001,T,A,"[""rock""]",[],[],http://x/1', "moods must contain"),
    ('track_0000001,T,A,not-json,"[""calm""]",[],http://x/1', "not valid JSON"),
    ('track_0000001,T,A,"""rock""","[""calm""]",[],http://x/1', "array of strings"),
    ('track_0000001,T,A,"[1, 2]","[""calm""]",[],http://x/1', "array of strings"),
    ('track_0000001,T,A,"[""rock""]","[""calm""]",[]', "wrong number of columns"),
])
def test_load_rejects_invalid_rows(tmp_path, row, fragment):
    with pytest.raises(CatalogError, match=fragment):
        load_v2_catalog(write_csv(tmp_path, row))


def test_load_rejects_duplicate_ids_and_wrong_header(tmp_path):
    with pytest.raises(CatalogError, match="duplicate track_id"):
        load_v2_catalog(write_csv(tmp_path, GOOD, GOOD))
    with pytest.raises(CatalogError, match="expected columns"):
        load_v2_catalog(write_csv(tmp_path, GOOD, header="id,title\n"))


def test_load_error_names_the_line(tmp_path):
    with pytest.raises(CatalogError, match="line 3"):
        load_v2_catalog(write_csv(tmp_path, GOOD, 'bad,T,A,"[""r""]","[""c""]",[],http://x/1'))


# ---- scoring ---------------------------------------------------------------

def test_score_values(catalog):
    by_id = {r.track.track_id: r for r in recommend_v2(catalog, genres=["rock"], moods=["calm"], k=20)}
    assert by_id["track_0000001"].score == 3
    assert by_id["track_0000003"].score == 1   # mood only
    assert by_id["track_0000002"].score == 2   # genre only
    assert "track_0000005" not in by_id        # nothing matched


def test_scores_are_ints_and_max_is_three(catalog):
    results = recommend_v2(catalog, genres=["rock", "poprock", "jazz"], moods=["calm", "happy"], k=20)
    assert all(type(r.score) is int for r in results)
    assert max(r.score for r in results) == v2.MAX_SCORE == 3


def test_multiple_genre_alternatives_are_or_and_capped_at_two_points(catalog):
    (r,) = [r for r in recommend_v2(catalog, genres=["rock", "poprock"], k=20) if r.track.track_id == "track_0000002"]
    assert r.score == 2                                  # not 4
    assert r.matched_genres == ("rock", "poprock")


def test_multiple_mood_alternatives_are_or_and_capped_at_one_point(catalog):
    r = next(r for r in recommend_v2(catalog, moods=["calm", "happy"], k=20) if r.track.track_id == "track_0000006")
    assert r.score == 1                                  # not 2
    assert r.matched_moods == ("calm", "happy")


def test_matching_is_exact_not_substring_or_synonym(catalog):
    results = recommend_v2(catalog, genres=["poprock"], k=20)
    assert ids(results) == ["track_0000002", "track_0000004"]   # rock-only tracks excluded
    results = recommend_v2(catalog, genres=["rock"], k=20)
    assert "track_0000004" not in ids(results)                   # poprock != rock


def test_case_and_whitespace_normalized(catalog):
    assert ids(recommend_v2(catalog, genres=["  ROCK "], moods=[" Calm"], k=20)) == \
        ids(recommend_v2(catalog, genres=["rock"], moods=["calm"], k=20))


def test_instruments_do_not_affect_score(catalog):
    guitar_track = next(t for t in catalog if t.instruments)
    r = next(r for r in recommend_v2(catalog, genres=["rock"], moods=["calm"], k=20)
             if r.track.track_id == guitar_track.track_id)
    assert r.score == 3
    assert not any("guitar" in x.explanation for x in recommend_v2(catalog, genres=["rock"], k=20))


def test_tracks_missing_attribute_get_no_credit_for_it():
    cat = [track(1, ["rock"], []), track(2, [], ["calm"]), track(3, ["rock"], ["calm"])]
    by_id = {r.track.track_id: r for r in recommend_v2(cat, genres=["rock"], moods=["calm"], k=5)}
    assert by_id["track_0000001"].score == 2    # no mood: no mood credit
    assert by_id["track_0000002"].score == 1    # no genre: no genre credit
    assert by_id["track_0000003"].score == 3


# ---- ranking ---------------------------------------------------------------

def test_exact_ordering(catalog):
    results = recommend_v2(catalog, genres=["rock"], moods=["calm"], k=20)
    assert [(r.track.track_id, r.score) for r in results] == [
        ("track_0000001", 3), ("track_0000006", 3),
        ("track_0000002", 2),
        ("track_0000003", 1), ("track_0000007", 1),
    ]


def test_ties_broken_by_numeric_track_id_not_catalog_order():
    cat = [track(300, ["rock"], ["m"]), track(20, ["rock"], ["m"]), track(1000000, ["rock"], ["m"]),
           track(3, ["rock"], ["m"])]
    assert ids(recommend_v2(cat, genres=["rock"], k=10)) == [
        "track_0000003", "track_0000020", "track_0000300", "track_1000000"]


def test_zero_score_tracks_excluded_and_k_not_padded(catalog):
    results = recommend_v2(catalog, genres=["jazz"], k=20)
    assert ids(results) == ["track_0000003", "track_0000005"]   # only 2 matches, k=20, no filler
    assert all(r.score > 0 for r in results)


def test_k_limits_results(catalog):
    assert len(recommend_v2(catalog, genres=["rock"], moods=["calm"], k=2)) == 2
    assert ids(recommend_v2(catalog, genres=["rock"], moods=["calm"], k=2)) == ["track_0000001", "track_0000006"]


def test_no_unrelated_tracks_added_and_empty_catalog_rejected():
    # Every supported tag occurs on some track, so a validated request always has a
    # positive match; an empty catalog has no vocabulary, so any request is unsupported.
    cat = [track(1, ["rock"], ["calm"]), track(2, ["jazz"], ["sad"])]
    assert ids(recommend_v2(cat, genres=["jazz"], k=5)) == ["track_0000002"]
    with pytest.raises(UnsupportedTagError):
        recommend_v2([], genres=["rock"])


def test_deterministic_and_catalog_order_independent(catalog):
    base = recommend_v2(catalog, genres=["rock", "jazz"], moods=["calm", "sad"], k=20)
    assert base == recommend_v2(catalog, genres=["rock", "jazz"], moods=["calm", "sad"], k=20)
    for seed in range(5):
        shuffled = catalog[:]
        random.Random(seed).shuffle(shuffled)
        assert recommend_v2(shuffled, genres=["rock", "jazz"], moods=["calm", "sad"], k=20) == base


def test_does_not_mutate_catalog(catalog):
    before = list(catalog)
    recommend_v2(catalog, genres=["rock"], k=3)
    assert catalog == before


# ---- validation ------------------------------------------------------------

def test_empty_preferences_raise(catalog):
    with pytest.raises(EmptyPreferencesError):
        recommend_v2(catalog)
    with pytest.raises(EmptyPreferencesError):
        recommend_v2(catalog, genres=[], moods=["", "   "])


def test_unsupported_tags_raise_and_are_reported(catalog):
    with pytest.raises(UnsupportedTagError) as err:
        recommend_v2(catalog, genres=["rock", "metalcore"], moods=["calm", "melancholy"])
    assert err.value.unsupported_genres == ("metalcore",)
    assert err.value.unsupported_moods == ("melancholy",)


def test_tag_in_wrong_category_is_unsupported(catalog):
    with pytest.raises(UnsupportedTagError):
        recommend_v2(catalog, genres=["calm"])      # 'calm' is a mood, not a genre
    with pytest.raises(UnsupportedTagError):
        recommend_v2(catalog, moods=["rock"])


def test_unknown_tag_is_not_silently_mapped(catalog):
    with pytest.raises(UnsupportedTagError):
        recommend_v2(catalog, genres=["pop rock"])   # not rewritten to 'poprock'


@pytest.mark.parametrize("k", [0, -1, 21, 1000])
def test_invalid_k_values_rejected(catalog, k):
    with pytest.raises(ValueError, match="k must be between"):
        recommend_v2(catalog, genres=["rock"], k=k)


@pytest.mark.parametrize("k", [True, 2.5, "5", None])
def test_non_integer_k_rejected(catalog, k):
    with pytest.raises(TypeError):
        recommend_v2(catalog, genres=["rock"], k=k)


def test_max_k_allowed(catalog):
    assert len(recommend_v2(catalog, genres=["rock"], k=v2.MAX_K)) == 3


def test_single_string_instead_of_sequence_rejected(catalog):
    with pytest.raises(TypeError):
        recommend_v2(catalog, genres="rock")
    with pytest.raises(TypeError):
        recommend_v2(catalog, genres=[1])


def test_vocabulary_and_split_supported_tags(catalog):
    vocab = catalog_vocabulary(catalog)
    assert vocab.genres == {"rock", "poprock", "jazz", "pop"}
    assert vocab.moods == {"calm", "happy", "sad"}
    assert split_supported_tags([" Rock", "metal", "ROCK", "calm"], vocab.genres) == (("rock",), ("metal", "calm"))


# ---- explanations ----------------------------------------------------------

def test_explanation_templates():
    assert build_explanation(["rock"], []) == "Matches your requested rock genre."
    assert build_explanation([], ["calm"]) == "Matches your requested calm mood."
    assert build_explanation(["rock"], ["calm"]) == "Matches your requested rock genre and calm mood."
    assert build_explanation(["rock", "poprock"], ["calm"]) == \
        "Matches your requested rock and poprock genres and calm mood."
    assert build_explanation(["a", "b", "c"], []) == "Matches your requested a, b and c genres."
    with pytest.raises(ValueError):
        build_explanation([], [])


def test_explanation_cites_only_actual_matches(catalog):
    for r in recommend_v2(catalog, genres=["rock", "jazz"], moods=["calm", "sad"], k=20):
        assert set(r.matched_genres) <= set(r.track.genres) & {"rock", "jazz"}
        assert set(r.matched_moods) <= set(r.track.moods) & {"calm", "sad"}
        assert r.explanation == build_explanation(r.matched_genres, r.matched_moods)
        for tag in r.matched_genres + r.matched_moods:
            assert tag in r.explanation
        unmatched = (set(r.track.genres) | set(r.track.moods)) - set(r.matched_genres) - set(r.matched_moods)
        for tag in unmatched:
            assert f" {tag} " not in r.explanation


def test_explanations_make_no_audio_claims(catalog):
    banned = ["energy", "energetic", "tempo", "beat", "acoustic", "similar", "love", "danceab", "loud", "fast", "bpm"]
    for r in recommend_v2(catalog, genres=["rock", "poprock", "jazz", "pop"], moods=["calm", "happy", "sad"], k=20):
        assert not any(word in r.explanation.lower() for word in banned)


def test_ranked_recommendation_is_immutable_and_structured(catalog):
    r = recommend_v2(catalog, genres=["rock"], k=1)[0]
    assert isinstance(r, RankedRecommendation) and isinstance(r.track, MusicTrack)
    assert isinstance(r.matched_genres, tuple) and isinstance(r.matched_moods, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.score = 9


# ---- real catalog integration ---------------------------------------------

@pytest.fixture(scope="module")
def real_catalog():
    return load_v2_catalog(REAL_CATALOG)


def test_real_catalog_loads_entirely(real_catalog):
    assert len(real_catalog) == 2500
    assert len({t.track_id for t in real_catalog}) == 2500
    assert all(t.genres and t.moods and t.track_url.startswith("http") for t in real_catalog)
    assert any(t.instruments == () for t in real_catalog)       # empty instruments are fine
    assert any(t.instruments for t in real_catalog)


def test_real_catalog_vocabulary_matches_docs(real_catalog):
    vocab = catalog_vocabulary(real_catalog)
    assert len(vocab.genres) == 221 and len(vocab.moods) == 209
    assert {"rock", "electronic"} <= vocab.genres and {"calm", "happy"} <= vocab.moods


def test_real_catalog_recommendations(real_catalog):
    results = recommend_v2(real_catalog, genres=["rock", "poprock"], moods=["calm"], k=5)
    assert len(results) == 5
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)
    assert results[0].score == 3
    by_id = {t.track_id: t for t in real_catalog}
    for r in results:
        assert by_id[r.track.track_id] is r.track               # a real catalog record
        assert set(r.matched_genres) <= set(r.track.genres) and set(r.matched_moods) <= set(r.track.moods)
        assert r.score == (2 if r.matched_genres else 0) + (1 if r.matched_moods else 0)
    # Ordering and tie-break check against a brute-force recount.
    expected = sorted(
        ((-(2 * bool({"rock", "poprock"} & set(t.genres)) + bool({"calm"} & set(t.moods))), int(t.track_id[6:]))
         for t in real_catalog if {"rock", "poprock"} & set(t.genres) or "calm" in t.moods))
    assert [(-r.score, int(r.track.track_id[6:])) for r in results] == expected[:5]


def test_real_catalog_order_independence(real_catalog):
    shuffled = real_catalog[:]
    random.Random(3).shuffle(shuffled)
    kwargs = dict(genres=["electronic", "ambient"], moods=["dark"], k=10)
    assert recommend_v2(shuffled, **kwargs) == recommend_v2(real_catalog, **kwargs)


def test_real_catalog_unsupported_tag(real_catalog):
    with pytest.raises(UnsupportedTagError):
        recommend_v2(real_catalog, genres=["definitely-not-a-genre"])
