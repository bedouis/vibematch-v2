# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name

**VibeMatch 1.0**, a rule-based music recommender simulation.

---

## 2. Intended Use

**Goal.** Given a listener's favorite genre, favorite mood and target energy level, suggest the five songs in a small catalog that fit best, and explain each suggestion.

**Intended use.** Classroom exploration of how a content-based recommender turns data into a ranking, and of where bias can appear. It assumes a listener can state one favorite genre, one favorite mood and an energy level from 0 to 1, and that these describe what they want right now.

**Not intended for.** Real users of a music service, ranking real songs or artists, or any decision where fairness to listeners or artists matters. It was tested only on this 20-song catalog and five profiles, and we have no evidence of how well it predicts what real people enjoy.

---

## 3. How the Model Works

This is a **rule-based, content-based recommender**, not a trained machine-learning model. The scoring rules and weights were set by hand, and nothing is learned from data or from other listeners.

The listener gives three things: a favorite genre, a favorite mood, and how energetic they want the music to feel, on a scale from 0 to 1. Every song in the catalog gets a score out of 4:

- **2 points** if its genre matches the favorite genre
- **1 point** if its mood matches the favorite mood
- **up to 1 point** for energy: the closer the song's energy is to the target, the more points, and a perfect match earns the full point

Genres and moods count as a match only when the whole label is the same (capitalization and extra spaces are ignored), so "pop" does not match "indie pop". Once every song is scored, the songs are ranked from highest to lowest, ties go to the song with the lower ID number, and the top five are shown with a short note on where each song's points came from. Tempo, danceability and the other data columns are not used.

These weights (2, 1, 1) are what the program uses. A second set (genre 1, mood 1, energy 2) was tried only as an evaluation experiment (Section 7), and the program has been returned to the original weights.

**How the code is organized.** The command-line program uses three functions: `load_songs()` reads the catalog, `score_song()` scores one song, and `recommend_songs()` ranks all the songs. The `Recommender` class, which the starter tests use, is implemented as well. It reuses `score_song()` and `recommend_songs()` instead of repeating the scoring rules, so the scoring logic lives in one place, and automated tests check that the class and the functions return consistent rankings.

**Changes from the starter code.** The starter supplied a 10-song data file and empty placeholders for loading songs, scoring a song, ranking, and the `Recommender` class. We implemented all of them, added the written reasons for each score, and expanded the catalog to 20 songs.

---

## 4. Data

The catalog is `data/songs.csv`: **20 songs**, one row each, with title, artist, genre, mood and five numeric features (energy, tempo, valence, danceability, acousticness). Only genre, mood and energy are used for scoring.

- **Genres:** 17 different labels. Lofi has 3 songs and pop has 2; the other 15 genres (for example rock, jazz, metal and classical) have exactly one song each.
- **Moods:** 15 different labels. "Chill" appears 3 times, "happy", "intense" and "relaxed" twice each, and the other 11 moods once.
- **Energy:** ranges from 0.18 to 0.98. Eight songs are at 0.75 or higher, eight are at 0.45 or lower, and only four fall in between.
- **Missing:** lyrics, language, release year, popularity and listening history. Each song has a single genre and mood label, and related genres such as "pop" and "indie pop" are separate labels. Some tastes are covered by one song or none, so a rock listener has only one rock song to match.

---

## 5. Strengths

These are observations from our five test profiles and our automated tests, not measures of recommendation quality.

- **Clear top results when the profile fits the catalog.** For High-Energy Pop, Chill Lofi and Deep Intense Rock, the #1 song matched genre, mood and energy (scores 3.97, 3.98 and 3.99). In our judgment these matched what each profile asked for. Chill Lofi gave the cleanest list, with three lofi songs in the top three.
- **Explainable recommendations.** Every recommendation lists which rules earned points (genre, mood, energy), so it is easy to see why a song ranked where it did.
- **Deterministic ranking.** The same input always gives the same output, regardless of the order of songs in the catalog, and ties are broken by song ID. All scores stayed between 0 and 4 in every run.
- **Tested behavior.** 18 automated tests pass. They cover ranking order, expected score values, result limits (including `k=0` and `k` larger than the catalog), explanation contents, tie-breaking, and consistency between the `Recommender` class and the functional code. These tests check that the code does what we intended, not that the recommendations suit real listeners.

---
## 6. Limitations and Bias

In the baseline evaluation, the high genre weight sometimes produced questionable rankings: Winter Nocturne, with energy 0.18, ranked first for a user targeting energy 0.95, while Focus Flow outranked Spacewalk Thoughts despite the latter matching the user's preferred mood. The system also relies on exact genre and mood matching, and 15 of the 17 genres in our 20-song dataset contain only one song, limiting the variety of relevant recommendations. Across the five baseline profiles, 11 of the 25 top-five recommendations matched neither genre nor mood, demonstrating how the system fills remaining positions using energy similarity alone. The weight-shift experiment changed the rankings for only one of the five profiles, showing that the impact of adjusting weights depends on the particular preferences and available songs. Although these results demonstrate limitations in ranking behavior, we have not measured actual listener satisfaction, and potential filter bubbles remain a theoretical concern rather than an observed outcome.

---

## 7. Evaluation

### How we tested

We ran the recommender on the 20-song catalog (`data/songs.csv`) with five profiles: three standard (High-Energy Pop, Chill Lofi, Deep Intense Rock) and two adversarial (Conflicting Preferences, Absent Genre). Each run returns five ranked songs, and we checked each score out of 4.00 and its explanation (points for genre, mood and energy closeness). We then ran a weight-shift experiment to test how sensitive the rankings are. The full terminal output for every profile is in the README under "Recommendation Evaluation — User Profiles".

### Standard profiles

All three produced strong top recommendations that matched genre, mood and energy.

- **High-Energy Pop (pop / happy / 0.85):** #1 was Sunrise City (3.97). Notably, #3 Rooftop Lights (1.91) is happy and high-energy but labeled "indie pop", so it earned no genre credit.
- **Chill Lofi (lofi / chill / 0.40):** #1 was Midnight Coding (3.98), and the top three were all lofi. Notably, Focus Flow (lofi, "focused", 3.00) outranked Spacewalk Thoughts (ambient, chill, 1.88).
- **Deep Intense Rock (rock / intense / 0.92):** #1 was Storm Runner (3.99). The rest of the list was weaker because the catalog has only one rock song: #2 Gym Hero (1.99) is a pop song matching only the mood, and #3 to #5 (all under 1.0) matched neither genre nor mood.

### Comparing the standard profiles

- **Pop vs. Lofi:** no songs in common. Every Pop result has energy 0.76 or higher, every Lofi result 0.42 or lower. The cause is mainly the energy targets (0.85 vs. 0.40), plus different genres and moods.
- **Pop vs. Rock:** three songs appear on both lists, for different reasons. Gym Hero is #2 on both: 2.92 for the genre "pop" in one, 1.99 for the mood "intense" in the other. Storm Runner is #5 for Pop (0.94, energy only) but #1 for Rock (3.99). Both profiles want high energy, which explains the overlap; genre and mood explain the differences.
- **Lofi vs. Rock:** no songs in common. Lofi's top three all score 3.00 or higher, while Rock has one strong result, then 1.99, then below 1.0. The energy targets are far apart (0.40 vs. 0.92), and the catalog holds three lofi songs but one rock song.

### Adversarial profiles

**Conflicting Preferences (classical / intense / 0.95).** *Observation:* under the original weights, #1 was Winter Nocturne (2.23), a quiet classical piece (energy 0.18), ahead of Gym Hero (1.98) and Storm Runner (1.96), which match the mood and energy target. *Why:* as the only classical song, it earned the full +2.0 genre bonus plus +0.23 for energy, while Gym Hero earned +1.0 for mood and +0.98 for energy. The 1.0-point genre-over-mood advantage exceeded Gym Hero's 0.75-point energy advantage. *Interpretation:* one heavily weighted category can outweigh a poor fit on everything else.

**Absent Genre (k-pop / happy / 0.80).** *Observation:* no song is k-pop, so none could earn genre points. The top two (Sunrise City 1.98, Rooftop Lights 1.96) are the only "happy" songs. Places #3 to #5 (Calle Luna 0.96, Night Drive Loop 0.95, Storm Runner 0.89) matched neither genre nor mood and were chosen only for energy near 0.80. The program gave no notice that the genre was missing. *Interpretation:* a missing genre simply scores zero and the remaining slots are filled by energy, so the system cannot say "I couldn't find what you asked for."

### Weight-shift experiment

We compared the original weights (genre 2.0, mood 1.0, energy 1.0) with experimental weights (genre 1.0, mood 1.0, energy 2.0). Experimental scores ranged from 0.52 to 3.98, within the valid 0 to 4 range.

| Profile | Baseline #1 | Experimental #1 | Ranking changed? |
|---|---|---|---|
| High-Energy Pop | Sunrise City, 3.97 | Sunrise City, 3.94 | No |
| Chill Lofi | Midnight Coding, 3.98 | Midnight Coding, 3.96 | No |
| Deep Intense Rock | Storm Runner, 3.99 | Storm Runner, 3.98 | No |
| Conflicting Preferences | Winter Nocturne, 2.23 | Gym Hero, 2.96 | **Yes** |
| Absent Genre | Sunrise City, 1.98 | Sunrise City, 2.96 | No |

*Observations:* four profiles kept exactly the same full 20-song ranking, with only the scores changing. Conflicting Preferences was the only profile whose ranking changed: Winter Nocturne fell from #1 to #10, Gym Hero rose to #1, and 10 of the 20 songs changed position. For Chill Lofi, Focus Flow still outranked Spacewalk Thoughts (3.00 vs. 2.76).

*Interpretation:* in our tests, changing the weights affected rankings only when the scoring components favored different songs. In the Conflicting profile, genre and energy pointed to different songs, so the weights decided the outcome; in the other four, the same songs scored well on every component. This describes our five profiles and small catalog, not a general rule, and does not show which weights are better.

### Summary

The system worked well when a listener's preferences matched the catalog: the standard profiles all produced strong top recommendations with sensible explanations. We were surprised that the weight change rarely altered a ranking, and that a calm classical piece could win a request for very high energy. Remaining limitations are exact text matching, a small catalog, and lists filled out by energy alone once real matches run out (see Section 6). We cannot claim objective accuracy, because we have no listener feedback or ground-truth data; these tests show how the algorithm behaves, not how well it predicts what people enjoy.

---

## 8. Future Work

In priority order:

1. **Expand the dataset and represent musical diversity better.** Add many more songs, with several songs per genre and mood, so a profile like rock has real alternatives after its first match. Allow a song to carry more than one genre or mood, and cover a wider range of styles.
2. **Introduce listener feedback and evaluate relevance.** Collect real signals such as likes, skips and replays, or ratings. This would let us check whether the rankings match what people enjoy, which our tests cannot show, and tune the weights from evidence instead of by hand.
3. **Improve related-genre matching and diversity.** Give partial credit to related genres (for example pop and indie pop), keep the top five from being all one style, and tell the listener when nothing in the catalog matches their genre instead of silently filling the list by energy alone.

A possible extension is to use the data columns we currently ignore, such as tempo, valence and acousticness.

---

## 9. Personal Reflection

This project helped me understand how a recommendation system can translate user preferences into numerical scores and ranked results without requiring a complex machine-learning model. One of my biggest learning moments was realizing how strongly the choice of scoring weights influences the behavior of an algorithm. A relatively simple formula could produce seemingly personalized recommendations while also generating unexpected results when different preferences conflicted.

AI tools were particularly useful for designing the scoring algorithm, implementing the Python functions, and developing test cases. They also helped me identify edge cases that I might not have considered initially, such as conflicting preferences and genres missing from the dataset. However, I needed to verify the generated code, check the score calculations, and compare the AI's predictions against actual program output rather than relying on its explanations alone.

The most surprising result came from the weight-shift experiment. I expected changing the relative importance of genre and energy to affect several recommendation lists, but four of the five profiles retained exactly the same rankings. Only the conflicting-preferences profile changed significantly, with Winter Nocturne falling from first to tenth place. This demonstrated that changes to an algorithm do not necessarily affect every user or produce universally better recommendations.

If I continued developing this project, I would expand the dataset to include a wider range of musical styles and more nuanced musical features. I would also explore ways to incorporate listener feedback, recognize similarities between related genres, and balance personalized recommendations with musical discovery. As a musician, I am especially interested in how a recommendation system might represent musical characteristics that are not adequately captured by broad categories such as genre, mood, or energy.
