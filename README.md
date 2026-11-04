# 🎵 Music Recommender Simulation

## Project Summary

**Music Recommender Simulation** (model name: **VibeMatch 1.0**) is a small, rule-based music recommender written in Python. A listener states a favorite genre, a favorite mood and a target energy level. The program scores each of the 20 songs in `data/songs.csv` against those preferences (up to 4 points: 2 for genre, 1 for mood, and up to 1 for how close the energy is), ranks the songs, and prints the top five with a plain-language reason for each score.

It is a content-based system built on hand-set rules, not a trained machine-learning model. We evaluated it on five user profiles (three standard and two adversarial), ran a weight-shift experiment, and documented what we found. 18 automated tests check ranking, scoring, result limits, explanations, tie-breaking and consistency. We did not measure listener satisfaction or recommendation accuracy, so the results describe how the algorithm behaves, not how well it predicts what people enjoy.

For the full write-up, see the [Model Card](model_card.md).

---

## How The System Works

The design below is implemented in `src/recommender.py` and run by `src/main.py`.

### Overview

This is a **content-based** recommender. It compares each song's own attributes to what a user says they like, and it needs no data from other listeners. Every song gets a score for how well it fits the user, the songs are sorted by score, and the best few are returned.

### Dataset

The catalog is `data/songs.csv`, with **20 songs**. Each row has an id, title, artist, and these attributes:

- `genre` and `mood`: text labels (e.g., pop, lofi, rock; happy, chill, intense)
- `energy`: a number from 0.0 to 1.0
- `tempo_bpm`, `valence`, `danceability`, `acousticness`: also available, but the scoring rule does not use them

### User profile

A user is described by a dictionary with three attributes:

```python
user_prefs = {
    "favorite_genre": "pop",    # the genre the user prefers
    "favorite_mood": "happy",   # the mood the user prefers
    "target_energy": 0.80,      # 0.0 to 1.0, the energy level the user wants
}
```

### Scoring formula

```
score = 2 * genre_match + mood_match + (1 - abs(song_energy - target_energy))
```

- `genre_match` and `mood_match` are 1 if the song's value equals the user's (ignoring capitalization and extra spaces), otherwise 0.
- The energy term is 1.0 for a perfect match and shrinks as the gap grows.
- Scores range from **0.0 to 4.0**. For example, "Sunrise City" (pop, happy, 0.82) scores 2 + 1 + 0.98 = **3.98** for the profile above.

### From scoring to recommendations

1. **Score each song.** The system loads the CSV into a list of dictionaries and loops over every song. For each one it applies the formula and records the score with a short explanation (e.g., "genre match (+2.0), energy similarity (+0.98)"). Each song is scored on its own, without reference to the others.
2. **Rank the catalog.** Once every song has a score, the list is sorted from highest to lowest. If two songs have the same score, the one with the lower song ID comes first, so the same input always gives the same output.
3. **Return the top K.** The first K songs are kept and printed to the terminal with their titles, scores, and reasons.

The same logic is also available as a `Recommender` class (`recommend()` and `explain_recommendation()`), which reuses `score_song()` and `recommend_songs()` instead of repeating the scoring rules.

### Data flow

```mermaid
flowchart TD
    %% ---------- INPUTS ----------
    subgraph INPUTS["📥 INPUTS"]
        U["User Preferences<br/>favorite_genre<br/>favorite_mood<br/>target_energy (0–1)"]
        C["Song Catalog<br/>data/songs.csv"]
    end

    %% ---------- PROCESSING ----------
    subgraph PROCESS["⚙️ PROCESSING"]
        L["Load & parse CSV<br/>into a list of Python dictionaries"]
        I["Iterate through every song"]

        subgraph SCORE["Calculate relevance score for each song"]
            G["Genre match<br/>+2.0 if equal, else 0"]
            M["Mood match<br/>+1.0 if equal, else 0"]
            E["Energy similarity<br/>1.0 − abs(song_energy − target_energy)"]
            T["score = genre + mood + energy<br/>(range 0 to 4)"]
            G --> T
            M --> T
            E --> T
        end

        S["Store score + explanation<br/>e.g. 'genre match (+2.0), energy similarity (+0.98)'"]
        N{"More songs<br/>left?"}
        R["Sort by score, descending<br/>Tie-breaker: song ID, ascending"]
        K["Keep the top K songs"]
    end

    %% ---------- OUTPUT ----------
    subgraph OUTPUT["📤 OUTPUT"]
        D["Print to terminal<br/>title • score • reasons"]
    end

    %% ---------- FLOW ----------
    C --> L
    L --> I
    U --> I
    I --> G
    I --> M
    I --> E
    T --> S
    S --> N
    N -- "yes" --> I
    N -- "no" --> R
    R --> K
    K --> D

    %% ---------- STYLING ----------
    classDef input fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef process fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef output fill:#dcfce7,stroke:#16a34a,color:#14532d
    class U,C input
    class L,I,G,M,E,T,S,N,R,K process
    class D output
```

### Limitations of the design

- **Genre dominance.** A genre match is worth 2.0, twice as much as a mood match and more than the entire energy term can contribute. A song in the right genre will almost always beat a song in the wrong genre, even if the wrong-genre song matches the user's mood and energy better.
- **Exact matching.** Genre and mood are compared as exact text, so related labels get no partial credit. A "pop" listener gets nothing for "indie pop," so in the High-Energy Pop run a happy indie pop song (*Rooftop Lights*, 1.91) scores below an intense pop song (*Gym Hero*, 2.92).
- **Limited diversity.** With only 20 songs, most genres appear once. A user with a niche favorite will always see that one song first however poorly it fits, and the rest of the top K fills up with weak matches. Different users will often see the same handful of songs.
- **Filter bubbles.** The system rewards songs that look like what the user already said they like, and nothing in the design pushes it to suggest something different. Users could keep seeing more of the same genre and mood and never discover other kinds of music. This is a hypothesis; we did not test it.

The first three were observed in our tests (see Limitations and Risks below and the Model Card).

---

## Getting Started

### Setup

1. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Mac or Linux
   .venv\Scripts\activate         # Windows
   ```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
python -m src.main
```

### Running Tests

Run the automated tests (18 tests) with:

```bash
python -m pytest -q
```

They are in `tests/test_recommender.py` and cover ranking order, scoring values, result limits, explanations, tie-breaking, and consistency between the `Recommender` class and the functional code.

---

## Sample Recommendation Output

Run the recommender from the repository root:

```bash
python -m src.main
```

The program loads `data/songs.csv`, then prints the top five recommendations for each of five built-in user profiles. For every song it shows the rank, title, artist, score out of 4.00, and the reasons behind the score. The full terminal output for each profile is in [Recommendation Evaluation — User Profiles](#recommendation-evaluation--user-profiles) below.

---

## Recommendation Evaluation — User Profiles

Baseline run with the original scoring weights (genre +2.0, mood +1.0, energy similarity up to +1.0). Command: `python -m src.main`. Each block below is the program's actual terminal output for one profile, split at the profile boundaries.

### High-Energy Pop

- Genre: `pop`
- Mood: `happy`
- Target energy: `0.85`

```text
Profile: High-Energy Pop (genre=pop, mood=happy, target energy=0.85)
============================================================
Top recommendations
============================================================

#1  Sunrise City by Neon Echo
    Score: 3.97 / 4.00
    Why:
      - genre match (+2.0)
      - mood match (+1.0)
      - energy similarity (+0.97)

#2  Gym Hero by Max Pulse
    Score: 2.92 / 4.00
    Why:
      - genre match (+2.0)
      - energy similarity (+0.92)

#3  Rooftop Lights by Indigo Parade
    Score: 1.91 / 4.00
    Why:
      - mood match (+1.0)
      - energy similarity (+0.91)

#4  Calle Luna by Los Faroles
    Score: 0.99 / 4.00
    Why:
      - energy similarity (+0.99)

#5  Storm Runner by Voltline
    Score: 0.94 / 4.00
    Why:
      - energy similarity (+0.94)
```

### Chill Lofi

- Genre: `lofi`
- Mood: `chill`
- Target energy: `0.4`

```text
Profile: Chill Lofi (genre=lofi, mood=chill, target energy=0.4)
============================================================
Top recommendations
============================================================

#1  Midnight Coding by LoRoom
    Score: 3.98 / 4.00
    Why:
      - genre match (+2.0)
      - mood match (+1.0)
      - energy similarity (+0.98)

#2  Library Rain by Paper Lanterns
    Score: 3.95 / 4.00
    Why:
      - genre match (+2.0)
      - mood match (+1.0)
      - energy similarity (+0.95)

#3  Focus Flow by LoRoom
    Score: 3.00 / 4.00
    Why:
      - genre match (+2.0)
      - energy similarity (+1.00)

#4  Spacewalk Thoughts by Orbit Bloom
    Score: 1.88 / 4.00
    Why:
      - mood match (+1.0)
      - energy similarity (+0.88)

#5  Coffee Shop Stories by Slow Stereo
    Score: 0.97 / 4.00
    Why:
      - energy similarity (+0.97)
```

### Deep Intense Rock

- Genre: `rock`
- Mood: `intense`
- Target energy: `0.92`

```text
Profile: Deep Intense Rock (genre=rock, mood=intense, target energy=0.92)
============================================================
Top recommendations
============================================================

#1  Storm Runner by Voltline
    Score: 3.99 / 4.00
    Why:
      - genre match (+2.0)
      - mood match (+1.0)
      - energy similarity (+0.99)

#2  Gym Hero by Max Pulse
    Score: 1.99 / 4.00
    Why:
      - mood match (+1.0)
      - energy similarity (+0.99)

#3  Pulse Horizon by Static Bloom
    Score: 0.96 / 4.00
    Why:
      - energy similarity (+0.96)

#4  Iron Cathedral by Black Meridian
    Score: 0.94 / 4.00
    Why:
      - energy similarity (+0.94)

#5  Calle Luna by Los Faroles
    Score: 0.92 / 4.00
    Why:
      - energy similarity (+0.92)
```

### Conflicting Preferences

- Genre: `classical`
- Mood: `intense`
- Target energy: `0.95`

```text
Profile: Conflicting Preferences (genre=classical, mood=intense, target energy=0.95)
============================================================
Top recommendations
============================================================

#1  Winter Nocturne by Elena Varga
    Score: 2.23 / 4.00
    Why:
      - genre match (+2.0)
      - energy similarity (+0.23)

#2  Gym Hero by Max Pulse
    Score: 1.98 / 4.00
    Why:
      - mood match (+1.0)
      - energy similarity (+0.98)

#3  Storm Runner by Voltline
    Score: 1.96 / 4.00
    Why:
      - mood match (+1.0)
      - energy similarity (+0.96)

#4  Pulse Horizon by Static Bloom
    Score: 0.99 / 4.00
    Why:
      - energy similarity (+0.99)

#5  Iron Cathedral by Black Meridian
    Score: 0.97 / 4.00
    Why:
      - energy similarity (+0.97)
```

### Absent Genre

- Genre: `k-pop`
- Mood: `happy`
- Target energy: `0.8`

```text
Profile: Absent Genre (genre=k-pop, mood=happy, target energy=0.8)
============================================================
Top recommendations
============================================================

#1  Sunrise City by Neon Echo
    Score: 1.98 / 4.00
    Why:
      - mood match (+1.0)
      - energy similarity (+0.98)

#2  Rooftop Lights by Indigo Parade
    Score: 1.96 / 4.00
    Why:
      - mood match (+1.0)
      - energy similarity (+0.96)

#3  Calle Luna by Los Faroles
    Score: 0.96 / 4.00
    Why:
      - energy similarity (+0.96)

#4  Night Drive Loop by Neon Echo
    Score: 0.95 / 4.00
    Why:
      - energy similarity (+0.95)

#5  Storm Runner by Voltline
    Score: 0.89 / 4.00
    Why:
      - energy similarity (+0.89)
```

---

## Experiments You Tried

### Weight shift: genre 2.0 → 1.0, energy 1.0 → 2.0

We changed the score to `1.0 * genre_match + 1.0 * mood_match + 2.0 * energy_similarity` (maximum still 4.0) and reran all five profiles. This was an evaluation experiment only: the original weights (2.0 / 1.0 / 1.0) are restored and are what the program uses. The raw outputs are in `baseline_results.txt` and `experiment_results.txt`.

| Profile | Baseline #1 | Experimental #1 | Ranking changed? |
|---|---|---|---|
| High-Energy Pop | Sunrise City, 3.97 | Sunrise City, 3.94 | No |
| Chill Lofi | Midnight Coding, 3.98 | Midnight Coding, 3.96 | No |
| Deep Intense Rock | Storm Runner, 3.99 | Storm Runner, 3.98 | No |
| Conflicting Preferences | Winter Nocturne, 2.23 | Gym Hero, 2.96 | **Yes** |
| Absent Genre | Sunrise City, 1.98 | Sunrise City, 2.96 | No |

- Four of the five profiles kept exactly the same full 20-song ranking; only their scores changed.
- Conflicting Preferences was the only profile whose ranking changed: Winter Nocturne fell from #1 to #10, Gym Hero rose to #1, and 10 of the 20 songs changed position.
- Experimental scores ranged from 0.52 to 3.98, within the valid 0 to 4 range.

### Different types of users

We tested three standard profiles (High-Energy Pop, Chill Lofi, Deep Intense Rock) and two adversarial ones: Conflicting Preferences (classical / intense / 0.95) and Absent Genre (k-pop / happy / 0.8). The standard profiles gave strong top results. Under the original weights, the conflicting profile ranked a quiet classical piece first, and the absent-genre profile had no genre match available, so its lower places were filled by energy alone.

### Not tried

We did not add tempo, valence or other features to the score, and we did not test any other weight settings.

---

## Limitations and Risks

**Observed in our tests**

- **Genre dominance:** with the original weights, a quiet classical song (Winter Nocturne, energy 0.18) ranked first for a listener targeting energy 0.95, and Focus Flow (lofi, "focused") outranked Spacewalk Thoughts (ambient, chill) for a chill listener.
- **Exact matching:** "pop" and "indie pop" are unrelated labels, so related genres get no partial credit.
- **Tiny catalog:** 15 of the 17 genres have only one song, and in the baseline results 11 of the 25 top-five slots went to songs that matched neither genre nor mood.
- **No warning for a missing genre:** the k-pop profile got a normal-looking list with no notice that nothing matched.

**Not tested (hypothetical)**

- Filter bubbles, where listeners keep seeing only familiar styles.
- Whether the system treats different groups of listeners unequally.

**Not measured:** listener satisfaction or recommendation accuracy. The system also ignores lyrics, language, tempo and the other data columns. See Section 6 of the [Model Card](model_card.md) for more.

---

## Reflection

For the full write-up, see the [**Model Card**](model_card.md).

This project helped me understand how a recommendation system can translate user preferences into numerical scores and ranked results without requiring a complex machine-learning model. One of my biggest learning moments was realizing how strongly the choice of scoring weights influences the behavior of an algorithm. A relatively simple formula could produce seemingly personalized recommendations while also generating unexpected results when different preferences conflicted.

The most surprising result came from the weight-shift experiment. I expected changing the relative importance of genre and energy to affect several recommendation lists, but four of the five profiles retained exactly the same rankings. Only the conflicting-preferences profile changed significantly, with Winter Nocturne falling from first to tenth place. This demonstrated that changes to an algorithm do not necessarily affect every user or produce universally better recommendations.
