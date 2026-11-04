"""
Command line runner for the Music Recommender Simulation.

This file helps you quickly run and test your recommender.

You will implement the functions in recommender.py:
- load_songs
- score_song
- recommend_songs
"""

from src.recommender import load_songs, recommend_songs


def main() -> None:
    songs = load_songs("data/songs.csv") 

    # Starter example profile
    user_prefs = {"favorite_genre": "pop", "favorite_mood": "happy", "target_energy": 0.8}

    recommendations = recommend_songs(user_prefs, songs, k=5)

    print(
        f"\nProfile: genre={user_prefs['favorite_genre']}, "
        f"mood={user_prefs['favorite_mood']}, "
        f"target energy={user_prefs['target_energy']}"
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
