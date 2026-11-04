"""
Command line runner for the Music Recommender Simulation.

This file helps you quickly run and test your recommender.

You will implement the functions in recommender.py:
- load_songs
- score_song
- recommend_songs
"""

from src.recommender import load_songs, recommend_songs


PROFILES = {
    "High-Energy Pop": {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 0.85},
    "Chill Lofi": {"favorite_genre": "lofi", "favorite_mood": "chill", "target_energy": 0.40},
    "Deep Intense Rock": {"favorite_genre": "rock", "favorite_mood": "intense", "target_energy": 0.92},
    "Conflicting Preferences": {"favorite_genre": "classical", "favorite_mood": "intense", "target_energy": 0.95},
    "Absent Genre": {"favorite_genre": "k-pop", "favorite_mood": "happy", "target_energy": 0.80},
}


def main() -> None:
    songs = load_songs("data/songs.csv")

    for name, user_prefs in PROFILES.items():
        recommendations = recommend_songs(user_prefs, songs, k=5)
        print_recommendations(name, user_prefs, recommendations)


def print_recommendations(name: str, user_prefs: dict, recommendations: list) -> None:
    print(
        f"\nProfile: {name} (genre={user_prefs['favorite_genre']}, "
        f"mood={user_prefs['favorite_mood']}, "
        f"target energy={user_prefs['target_energy']})"
    )
    print("=" * 60)
    print("Top recommendations")
    print("=" * 60)

    if not recommendations:
        print("No recommendations found.")
        return

    for rank, (song, score, explanation) in enumerate(recommendations, start=1):
        artist = song.get("artist")
        title = f"{song['title']} by {artist}" if artist else song["title"]
        print(f"\n#{rank}  {title}")
        print(f"    Score: {score:.2f} / 4.00")
        print("    Why:")
        for reason in explanation.split(", "):
            print(f"      - {reason}")


if __name__ == "__main__":
    main()
