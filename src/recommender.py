import csv
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict

@dataclass
class Song:
    """
    Represents a song and its attributes.
    Required by tests/test_recommender.py
    """
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float

@dataclass
class UserProfile:
    """
    Represents a user's taste preferences.
    Required by tests/test_recommender.py
    """
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool

class Recommender:
    """
    OOP implementation of the recommendation logic.
    Required by tests/test_recommender.py
    """
    def __init__(self, songs: List[Song]):
        self.songs = songs

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        """Return the top k Song objects for this user, best first, using recommend_songs()."""
        song_dicts = [asdict(song) for song in self.songs]
        ranked = recommend_songs(self._to_prefs(user), song_dicts, k)
        songs_by_id = {song.id: song for song in self.songs}
        return [songs_by_id[song_dict["id"]] for song_dict, _, _ in ranked]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """Return the score reasons for one song as text, using score_song()."""
        _, reasons = score_song(self._to_prefs(user), asdict(song))
        return ", ".join(reasons)

    @staticmethod
    def _to_prefs(user: UserProfile) -> Dict:
        """Convert a UserProfile to the preference dict that score_song() expects."""
        return {
            "favorite_genre": user.favorite_genre,
            "favorite_mood": user.favorite_mood,
            "target_energy": user.target_energy,
        }

def load_songs(csv_path: str) -> List[Dict]:
    """Read songs from a CSV file and return a list of dicts with numeric fields converted."""
    print(f"Loading songs from {csv_path}...")

    songs = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # DictReader gives every value as a string, so convert numeric columns.
            row["id"] = int(row["id"])
            for field in ("energy", "tempo_bpm", "valence", "danceability", "acousticness"):
                row[field] = float(row[field])
            songs.append(row)
    return songs

def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """Score one song (0.0 to 4.0) against the user's preferences; return (score, list of reasons)."""
    score = 0.0
    reasons = []

    if song["genre"].strip().lower() == user_prefs["favorite_genre"].strip().lower():
        score += 2.0
        reasons.append("genre match (+2.0)")

    if song["mood"].strip().lower() == user_prefs["favorite_mood"].strip().lower():
        score += 1.0
        reasons.append("mood match (+1.0)")

    energy_similarity = 1.0 - abs(song["energy"] - user_prefs["target_energy"])
    score += energy_similarity
    reasons.append(f"energy similarity (+{energy_similarity:.2f})")

    return score, reasons

def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5) -> List[Tuple[Dict, float, str]]:
    """Score every song and return the top k as (song, score, explanation), best first."""
    scored = []
    for song in songs:
        score, reasons = score_song(user_prefs, song)
        scored.append((song, score, ", ".join(reasons)))

    # Highest score first; equal scores fall back to the lower song id.
    ranked = sorted(scored, key=lambda item: (-item[1], item[0]["id"]))
    return ranked[:max(k, 0)]
