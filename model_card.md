# 🎧 Model Card: Music Recommender Simulation

## 1. Model Name  

Give your model a short, descriptive name.  
Example: **VibeFinder 1.0**  

---

## 2. Intended Use  

Describe what your recommender is designed to do and who it is for. 

Prompts:  

- What kind of recommendations does it generate  
- What assumptions does it make about the user  
- Is this for real users or classroom exploration  

---

## 3. How the Model Works  

The recommender compares each song to what a listener says they like. The listener gives three things: a favorite genre, a favorite mood, and how energetic they want the music to feel, on a scale from 0 to 1. Every song in the catalog gets a score out of 4. A song earns 2 points if its genre matches the listener's favorite, 1 point if its mood matches, and up to 1 more point depending on how close its energy is to the listener's target. A song with exactly the right energy gets the full point, and the point shrinks as the energy gets further away. Once every song has a score, the songs are sorted from highest to lowest and the top few are shown, each with a short note explaining where its points came from. If two songs tie, the one that appears earlier in the catalog (the lower ID number) comes first. The system doesn't learn from other listeners. It only looks at the song's own genre, mood and energy, and it ignores tempo, danceability, and the other columns in the data.

Explain your scoring approach in simple language.  

Prompts:  

- What features of each song are used (genre, energy, mood, etc.)  
- What user preferences are considered  
- How does the model turn those into a score  
- What changes did you make from the starter logic  

Avoid code here. Pretend you are explaining the idea to a friend who does not program.

---

## 4. Data  

Describe the dataset the model uses.  

Prompts:  

- How many songs are in the catalog  
- What genres or moods are represented  
- Did you add or remove data  
- Are there parts of musical taste missing in the dataset  

---

## 5. Strengths  

Where does your system seem to work well  

Prompts:  

- User types for which it gives reasonable results  
- Any patterns you think your scoring captures correctly  
- Cases where the recommendations matched your intuition  

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

Ideas for how you would improve the model next.  

Prompts:  

- Additional features or preferences  
- Better ways to explain recommendations  
- Improving diversity among the top results  
- Handling more complex user tastes  

---

## 9. Personal Reflection  

A few sentences about your experience.  

Prompts:  

- What you learned about recommender systems  
- Something unexpected or interesting you discovered  
- How this changed the way you think about music recommendation apps  
