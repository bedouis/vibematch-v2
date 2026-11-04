from dataclasses import asdict

import pytest

from src.recommender import Song, UserProfile, Recommender, score_song, recommend_songs

def make_small_recommender() -> Recommender:
    songs = [
        Song(
            id=1,
            title="Test Pop Track",
            artist="Test Artist",
            genre="pop",
            mood="happy",
            energy=0.8,
            tempo_bpm=120,
            valence=0.9,
            danceability=0.8,
            acousticness=0.2,
        ),
        Song(
            id=2,
            title="Chill Lofi Loop",
            artist="Test Artist",
            genre="lofi",
            mood="chill",
            energy=0.4,
            tempo_bpm=80,
            valence=0.6,
            danceability=0.5,
            acousticness=0.9,
        ),
    ]
    return Recommender(songs)


def test_recommend_returns_songs_sorted_by_score():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    results = rec.recommend(user, k=2)

    assert len(results) == 2
    # Starter expectation: the pop, happy, high energy song should score higher
    assert results[0].genre == "pop"
    assert results[0].mood == "happy"


def test_explain_recommendation_returns_non_empty_string():
    user = UserProfile(
        favorite_genre="pop",
        favorite_mood="happy",
        target_energy=0.8,
        likes_acoustic=False,
    )
    rec = make_small_recommender()
    song = rec.songs[0]

    explanation = rec.explain_recommendation(user, song)
    assert isinstance(explanation, str)
    assert explanation.strip() != ""


# ---------------------------------------------------------------------------
# Helpers for the behavior tests below. Each test builds its own tiny catalog,
# so no test depends on data/songs.csv or on another test.
# ---------------------------------------------------------------------------

def make_song(song_id, genre="pop", mood="happy", energy=0.8, title=None) -> Song:
    """Build a Song with sensible defaults; only the fields the scorer uses matter."""
    return Song(
        id=song_id,
        title=title or f"Song {song_id}",
        artist="Test Artist",
        genre=genre,
        mood=mood,
        energy=energy,
        tempo_bpm=100,
        valence=0.5,
        danceability=0.5,
        acousticness=0.5,
    )


def make_user(genre="pop", mood="happy", energy=0.8) -> UserProfile:
    return UserProfile(
        favorite_genre=genre,
        favorite_mood=mood,
        target_energy=energy,
        likes_acoustic=False,
    )


def make_prefs(genre="pop", mood="happy", energy=0.8) -> dict:
    """The preference dict that score_song() and recommend_songs() expect."""
    return {"favorite_genre": genre, "favorite_mood": mood, "target_energy": energy}


def make_ranking_catalog():
    """Three songs with clearly different scores for a pop / happy / 0.8 listener.

    Listed worst-first on purpose, so catalog order is the opposite of score order.
      id 1: rock / angry,  energy 0.1 -> 0 + 0 + 0.3 = 0.3
      id 2: pop  / calm,   energy 0.8 -> 2 + 0 + 1.0 = 3.0
      id 3: pop  / happy,  energy 0.8 -> 2 + 1 + 1.0 = 4.0
    """
    return [
        make_song(1, genre="rock", mood="angry", energy=0.1),
        make_song(2, genre="pop", mood="calm", energy=0.8),
        make_song(3, genre="pop", mood="happy", energy=0.8),
    ]


# ---------------------------------------------------------------------------
# 1. Ranking correctness
# ---------------------------------------------------------------------------

def test_recommend_orders_by_score_not_catalog_order():
    rec = Recommender(make_ranking_catalog())

    results = rec.recommend(make_user(), k=3)

    # Best score first, even though that song is last in the catalog.
    assert [song.id for song in results] == [3, 2, 1]


# ---------------------------------------------------------------------------
# 2. Scoring correctness
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "genre, mood, energy, expected",
    [
        ("pop", "happy", 0.8, 4.0),     # perfect match: 2 + 1 + 1.0
        ("pop", "happy", 0.6, 3.8),     # genre + mood, energy off by 0.2
        ("pop", "sad", 0.8, 3.0),       # genre only
        ("rock", "happy", 0.8, 2.0),    # mood only
        ("rock", "sad", 0.3, 0.5),      # neither, energy off by 0.5
        (" POP ", "Happy", 0.8, 4.0),   # capitalization and spaces are ignored
    ],
)
def test_score_song_awards_expected_points(genre, mood, energy, expected):
    song = asdict(make_song(1, genre=genre, mood=mood, energy=energy))

    score, _ = score_song(make_prefs("pop", "happy", 0.8), song)

    assert score == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 3. Recommendation limits
# ---------------------------------------------------------------------------

def test_recommend_k_zero_returns_empty_list():
    rec = Recommender(make_ranking_catalog())

    assert rec.recommend(make_user(), k=0) == []


def test_recommend_k_one_returns_only_the_best_song():
    rec = Recommender(make_ranking_catalog())

    results = rec.recommend(make_user(), k=1)

    assert [song.id for song in results] == [3]


def test_recommend_k_larger_than_catalog_returns_every_song_in_order():
    rec = Recommender(make_ranking_catalog())

    results = rec.recommend(make_user(), k=10)

    assert [song.id for song in results] == [3, 2, 1]


# ---------------------------------------------------------------------------
# 4. Explanation correctness
# ---------------------------------------------------------------------------

def test_explanation_lists_all_three_contributions_for_a_perfect_match():
    rec = Recommender([])
    song = make_song(1, genre="pop", mood="happy", energy=0.8)

    explanation = rec.explain_recommendation(make_user(), song)

    assert "genre match (+2.0)" in explanation
    assert "mood match (+1.0)" in explanation
    assert "energy similarity (+1.00)" in explanation


def test_explanation_only_mentions_the_contributions_a_song_earned():
    rec = Recommender([])
    genre_only = make_song(1, genre="pop", mood="sad", energy=0.6)
    neither = make_song(2, genre="rock", mood="sad", energy=0.3)

    genre_only_text = rec.explain_recommendation(make_user(), genre_only)
    neither_text = rec.explain_recommendation(make_user(), neither)

    assert "genre match (+2.0)" in genre_only_text
    assert "mood match" not in genre_only_text
    assert "energy similarity (+0.80)" in genre_only_text

    assert "genre match" not in neither_text
    assert "mood match" not in neither_text
    assert "energy similarity (+0.50)" in neither_text


# ---------------------------------------------------------------------------
# 5. Deterministic behavior
# ---------------------------------------------------------------------------

def test_reversing_the_catalog_does_not_change_ranking_when_scores_differ():
    catalog = make_ranking_catalog()

    forward = Recommender(catalog).recommend(make_user(), k=3)
    backward = Recommender(list(reversed(catalog))).recommend(make_user(), k=3)

    assert [song.id for song in forward] == [song.id for song in backward]


def test_equal_scores_are_ordered_by_lower_song_id():
    # ids 7 and 3 are identical in every scored field, so their scores tie.
    tied_high_id = make_song(7, genre="pop", mood="happy", energy=0.8)
    tied_low_id = make_song(3, genre="pop", mood="happy", energy=0.8)
    lower_score = make_song(5, genre="rock", mood="sad", energy=0.1)

    for catalog in ([tied_high_id, tied_low_id, lower_score],
                    [lower_score, tied_low_id, tied_high_id]):
        results = Recommender(catalog).recommend(make_user(), k=3)

        assert [song.id for song in results] == [3, 7, 5]


# ---------------------------------------------------------------------------
# 6. Consistency between the class and the functional implementation
# ---------------------------------------------------------------------------

def test_recommender_class_matches_recommend_songs_function():
    # Includes a tie (ids 7 and 3) so the tie-breaker is compared too.
    catalog = make_ranking_catalog() + [
        make_song(7, genre="pop", mood="happy", energy=0.8),
        make_song(4, genre="lofi", mood="chill", energy=0.4),
    ]
    user = make_user()
    song_dicts = [asdict(song) for song in catalog]

    for k in (0, 1, 3, 10):
        class_ids = [song.id for song in Recommender(catalog).recommend(user, k=k)]
        function_ids = [d["id"] for d, _, _ in recommend_songs(make_prefs(), song_dicts, k=k)]

        assert class_ids == function_ids


def test_explanation_matches_the_one_returned_by_recommend_songs():
    catalog = make_ranking_catalog()
    song_dicts = [asdict(song) for song in catalog]

    _, _, function_explanation = recommend_songs(make_prefs(), song_dicts, k=1)[0]
    best_song = Recommender(catalog).recommend(make_user(), k=1)[0]

    assert Recommender(catalog).explain_recommendation(make_user(), best_song) == function_explanation
