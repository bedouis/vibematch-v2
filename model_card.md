# 🎧 Model Card: VibeMatch 2.0

This card describes **VibeMatch 2.0** (Gemini-assisted intent interpretation plus deterministic ranking of 5,000 real Jamendo tracks). The original **VibeMatch 1.0** card (a rule-based recommender over 20 synthetic songs) is preserved unchanged in [Appendix A](#appendix-a-model-card-for-vibematch-10-original). Measured figures come from [docs/EVALUATION.md](docs/EVALUATION.md) and [docs/DATASET.md](docs/DATASET.md). **No accuracy or listener-satisfaction metric exists for this system, and none is claimed.**

| | **VibeMatch 1.0** | **VibeMatch 2.0** |
|---|---|---|
| Kind | Rule-based, content-based recommender | Gemini maps a sentence to catalog tags; a rule-based scorer ranks tracks |
| Catalog | 20 synthetic songs | 5,000 real Jamendo tracks |
| Input | Genre, mood, target energy | One free-text sentence, up to 500 characters |
| Maximum score | 4 | 3 |
| Interface | Command line | Streamlit web app |

---

## 1. Intended Use

**Goal.** Let a listener describe music in everyday words and get up to ten tracks from a fixed catalog whose catalog tags match, each with an explanation that names the tags that matched.

**Intended use.** A course project and portfolio demonstration of an LLM-assisted, *grounded* recommender: the language model is restricted to a known tag vocabulary, its output is independently validated, and the ranking is transparent and reproducible. Suitable for non-commercial research, teaching and demonstration.

**Not intended for.**
- Commercial use. The dataset metadata is CC BY-NC-SA 4.0 and limited to non-commercial research and academic use.
- A production music service, or any decision about artists, royalties, ranking fairness or listener wellbeing.
- Claims about how music *sounds*. The system uses uploader-provided text tags only, and analyzes no audio.
- Sensitive or personal queries: the text is sent to a third-party API.

## 2. Input and Output

**Input:** one natural-language request, 1 to 500 characters (blank, non-text and longer inputs are rejected before any API call).

**Output on success:**
- An *interpretation*: up to 2 genres and up to 2 moods, each a tag that exists in the catalog (either list may be empty, never both).
- Up to **10** tracks, each with rank, title, artist, a score of 1 to 3 (a fixed rule, not a confidence), a sentence naming the matched tags, the matched genre and mood tags, and a link to the Jamendo track page.

**Output on failure:** one fixed message (blank query, missing API key, Gemini unreachable, reply rejected as unverifiable, no usable interpretation, no matches). Exception text and keys are never shown.

## 3. Model and Algorithm Roles

| Component | Role | What it does **not** do |
|---|---|---|
| **Gemini** (`google-genai` SDK; default `gemini-3.5-flash-lite`, overridable with `GEMINI_MODEL`) | Interprets the request into catalog genre and mood tags, returned as structured JSON (`genres`, `moods`, at most 2 each). It receives the full catalog vocabulary and instructions to return only supported tags, to return an empty list when evidence is unclear, and to treat the request as data. | Does not rank, choose tracks, or write explanations. No fine-tuning or training. One call per request, no retry. |
| **Python validator** (`parse_model_response`) | Checks the reply independently: JSON object with exactly `genres` and `moods`, lists of non-empty strings, tags normalized and de-duplicated, each genre in the genre vocabulary and each mood in the mood vocabulary, at most 2 per category, at least one tag. Any violation rejects the whole reply. | Does not repair, remap or partially accept tags. |
| **Recommender** (`recommend_v2`) | Deterministic scoring and ranking (Section 5) and template explanations. | Uses no machine learning, randomness, embeddings or audio. |

Gemini's temperature and other sampling settings are left at the model's defaults, so the *same sentence may produce different tags on different runs* (run-to-run variation was not measured). Everything downstream of the validated tags is fully deterministic.

## 4. Dataset Provenance

Source: official **MTG-Jamendo Dataset** metadata (`raw_30s_cleantags.tsv`, `raw.meta.tsv`), joined by track ID. Only metadata is used; no audio. Metadata license **CC BY-NC-SA 4.0**, non-commercial research and academic use only; citation: Bogdanov et al. (2019), *The MTG-Jamendo Dataset for Automatic Music Tagging*, ICML 2019 workshop.

- 55,701 source tracks; **21,712 eligible**. The main filter is the mood/theme tag: 33,669 tracks (about 60%) have none. Another 318 have no genre tag and 2 have no matching metadata.
- **5,000 selected**, by 1,538 artists (at most 5 per artist), with 221 genres, 216 moods and 123 instruments. About 47% of the selected tracks have no instrument tags.
- Selection is deterministic and independent of source row order: tracks are grouped by their rarest genre, ordered by a hash of the track ID, and taken round-robin with the artist cap.
- Titles, artists, tags and URLs are copied from the source. No energy, tempo, valence or other audio features were created.

Full details and regeneration steps: [docs/DATASET.md](docs/DATASET.md).

## 5. Ranking Methodology

For the validated tags, every track receives:

- **+2** if it has *any* requested genre (genre matching is OR; the category is credited once however many requested genres match),
- **+1** if it has *any* requested mood (same rule),
- so the maximum is **3**.

Matching is exact on normalized tags (lowercased, whitespace-trimmed): `rock` does not match `poprock`, and there are no synonyms. Tracks scoring 0 are dropped; remaining tracks sort by score descending and then by **numeric track ID ascending**; the first 10 are returned. If fewer than 10 tracks score above zero, fewer are returned and nothing is added to fill the list. Instruments are stored but not scored. The explanation is a fixed template over the tags that matched (for example, "Matches your requested ambient genre and relaxing mood."), shown with the matched tags.

## 6. Validation and Reliability Safeguards

Query validation; structured JSON output; independent Python validation; rejection (never repair) of unsupported tags; distinct error types with fixed user-safe messages; one Gemini call per request; deterministic ranking; no zero-score filler; explanations from a template; no audio claims; no keys in the repository (key read from `GEMINI_API_KEY` only); result persistence in the UI. Each safeguard is mapped to its code and tests in [docs/EVALUATION.md](docs/EVALUATION.md#7-reliability-safeguards-implemented). The suite has **275 automated tests** (18 V1, 257 V2) that need no API key or network.

## 7. Offline Evaluation Findings

12 scenarios (10 valid, 2 negative) plus 18 invalid-input cases, run offline through the real validator, pipeline and recommender on the 5,000-track catalog. The interpretations are **human-chosen references or hand-written invalid candidates, not Gemini outputs**; the references were written by the project's own authors, not by an independent reviewer.

| Metric | Result |
|---|---|
| Offline execution success | 12/12 |
| Ranking correctness (independent recomputation of the documented rule) | 10/10 result sets |
| Evidence consistency (matched tags and explanation) | 91/91 recommendations |
| Coverage of valid scenarios | 10/10 |
| Invalid scenarios / invalid-input cases rejected | 2/2 / 18/18 |
| Artist diversity at 10 | mean 0.650 over 10 result sets (includes a one-track list); **0.611** over the 9 full lists; lowest 0.400 |

These are **rule-conformance checks** of deterministic code (the checkers were shown to fail on deliberately corrupted results), not measures of recommendation quality. Coverage is close to guaranteed by design. **Artist diversity is the informative result**: in the offline runs a single artist held up to 5 of 10 places (S04, S06, S09).

## 8. Live Gemini Observations

Five searches were run manually in the real app (5,000-track catalog, top 10). Evidence: preserved UI exports in [docs/evidence/live/](docs/evidence/live/README.md). The query text was recorded by the tester (not in the exports); Gemini's raw replies, model version, timing and track IDs were not captured.

| # | Request (tester-recorded) | Observed in the UI | Distinct artists |
|---|---|---|---:|
| Q1 | Relaxing ambient music for reading on a rainy afternoon | genre `ambient`, mood `relaxing`; 10 results, all 3/3 | 7 |
| Q2 | Upbeat, energetic music for an intense workout | no genre; moods `energetic`, `workout`; 10 results, all 1/3 | 3 |
| Q3 | Dark, atmospheric electronic music, cinematic feeling | reply rejected as unverifiable; no results (cause not captured) | n/a |
| Q4 | Peaceful, relaxing rock, not too aggressive | genre `rock`; moods `peaceful`, `relaxing`; nine 3/3 and one 2/3 | 6 |
| Q5 | Traditional zydeco with a lively accordion sound | no usable interpretation; no results | n/a |

Three searches returned lists, one was rejected and one abstained. These are five hand-picked observations, **not a success or accuracy rate**; mean artist diversity over the three lists was 0.533. A human rating sheet exists in the evaluation document with all subjective ratings **left blank**; no listening or rating study has been done.

## 9. Limitations

- **The AI step is unmeasured.** How often Gemini picks appropriate tags here is unknown.
- **Strict rejection costs availability.** One unsupported or misplaced tag rejects the whole reply (seen once in five searches). No retry or fallback.
- **Tag matching, not music matching.** Results reflect uploader tags; nothing confirms how a track sounds. The workout search returned tracks tagged `energetic`, none tagged `workout`.
- **Coarse scoring and ID tie-breaking.** Only scores 0 to 3 exist; ties go to the lowest track ID. Mood-only requests cap at 1 out of 3.
- **Artist repetition.** One artist can fill much of a top 10 (3 distinct artists in the workout search).
- **A requested tag can go unmatched.** For "calm death metal" (offline scenario S09) no track has both tags, so all ten results are death metal without `calm`, while the interpretation panel still lists *calm*.
- **Sparse tags give short lists** (for example `metalcore` occurs on one track).
- **The first step may vary between runs.** Sampling is left at model defaults and the variation was not measured.
- **English only** was tested.
- **Links may be stale.**

## 10. Dataset and Representation Bias

- **Whose music.** Jamendo hosts Creative Commons music uploaded by its artists, so the catalog reflects who uploads there, not music generally or what listeners commonly hear, and it should not be assumed to include the commercial catalogs most listeners know.
- **Genre skew.** In the 5,000 selected tracks, `electronic` appears on 1,264 (25%), `soundtrack` on 740, `rock` on 705, `ambient` on 693 and `pop` on 654. The selection method flattens genre frequencies relative to Jamendo, so these shares are not Jamendo's true distribution either. 19 genres appear on fewer than 5 tracks.
- **Tag selection effects.** Only tracks that carry a mood/theme tag were eligible (about 39% of the source), so the catalog favors tracks whose uploaders chose to add mood tags. Tags are uploader-provided and subjective.
- **The tag vocabulary is English-named and uneven.** Genres are single lowercase tokens (`rockfrancais`, `electroambient`) of very different granularity, and near-duplicates are not merged (`rock`, `poprock`). How well these tags fit non-Western musical categories was not assessed. The mood/theme set also includes non-mood labels such as countries (for example `brazil`, `india`, `japan`) and topics (`advertising`, `news`, `youtube`), so "mood" matching is not always about feeling.
- **Artist exposure.** Ties go to the lowest track ID, which tends to favor older uploads and lets a few artists dominate result lists. This is a mechanism visible in the results; exposure across many searches was not measured. The 5-tracks-per-artist cap applies only when building the catalog, not to a result list.
- **Languages.** Queries were tested only in English; non-English requests and non-English genre names were not tested.

## 11. Potential Misuse

- **Commercial use of the catalog or links** would violate the dataset's non-commercial license.
- **Presenting tag matches as audio analysis or presenting scores as AI confidence.** The UI states otherwise; copies of the output should too.
- **Reporting the offline 100% figures as AI accuracy.** They check deterministic code against its own documented rules, not model quality.
- **Entering sensitive information.** Queries go to Google's Gemini API.
- **Prompt manipulation.** A user can try to instruct the model through the query. The validator blocks any non-catalog tag, so the effect is limited to a rejected request or a different valid tag choice; this was tested with mocked replies, not adversarially against the live model.
- **Quota abuse.** The app has no authentication or rate limiting, so a deployed copy could exhaust an API key's quota.

## 12. Ethical Considerations

- **Transparency.** Interpretation, matched tags and explanation are shown for every result, and scores are labeled as a fixed rule.
- **Privacy.** No accounts, listening history or personal data are used. Query text is sent to Gemini; the app keeps only the current session's last result in memory.
- **Artists' rights.** Tracks are linked to their Jamendo pages, never copied or hosted. The metadata license requires attribution and non-commercial use.
- **Fairness to artists.** The ID tie-break and uneven tags mean some artists will be shown more than others for reasons unrelated to quality. No diversification has been implemented.
- **Content.** Titles and tags are shown as published and were not moderated; some content may be unsuitable for all audiences.
- **Honest limits.** The project makes no claim that results match listener taste.

## 13. Surprising Findings

1. **Most of the source lacks mood tags.** About 60% of Jamendo's 30-second-plus tracks have none, which determines what the catalog can recommend.
2. **Raw data broke a standard parse.** A stray double quote in one title made default CSV parsing merge about 100 rows, so the preparation script disables quote handling.
3. **The category of a word matters.** `atmospheric` exists only as a genre, not a mood; `metalcore` exists but on a single track.
4. **A fully "correct" result can still be one artist's tracks.** Ten results by 3 artists, all with the maximum score the query allowed.
5. **A conflicting request returned an honest but unsatisfying list** ("calm death metal": no track has both tags).
6. **The model chosen from documentation timed out in live testing.** `gemini-3.8-flash` returned an HTTP 504 while `gemini-3.5-flash-lite` worked, so the default was changed.
7. **The one rejected live search is undiagnosable.** The raw reply was not captured, so the cause of the rejection is unknown.

## 14. AI-Assisted Development Reflection

V2 was built with an AI coding assistant (Claude Code) working through staged prompts, each with explicit scope, constraints ("do not commit or push", "stop after reporting") and a required report. The author reviewed each step, ran the application, supplied every live Gemini observation (the assistant never called Gemini), and made the commits.

What helped: fast implementation, broad test generation, and systematic data inspection before coding. What needed correction: a default model that failed live, tests with wrong assumptions that were fixed, an evaluation write-up whose summary statistic and wording were tightened after review, and several claims that had to be reduced to what was actually observed. The main lesson was that every AI-produced claim needed an independent check (a run, a recount, a byte comparison) before it was trusted. Details, including adopted, corrected and rejected suggestions: [ai_interactions.md](ai_interactions.md). A personal reflection on the project is in [Section 16](#16-personal-reflection-what-i-learned-building-vibematch-20).

## 15. Future Improvements

In priority order:

1. Collect human ratings and run more live queries on the 5,000-track catalog; record raw model replies and model version.
2. Limit repeats of one artist within a result list and replace pure track-ID tie-breaking.
3. Retry once or offer supported tags when a reply is rejected.
4. Constrain tags in the response schema (untested live) to reduce rejections.
5. Tell the user when a requested tag matched none of the results shown.
6. Evaluate relevance by listening, and widen the catalog's coverage and tag vocabulary.

## 16. Personal Reflection: What I Learned Building VibeMatch 2.0

Building VibeMatch 2.0 changed how I think about AI-powered software. At the beginning, my goal was to transform a simple rule-based music recommender into an application that could understand natural-language requests and recommend music from a much larger, real-world catalog. As the project progressed, I realized that the most important engineering decisions were not necessarily about making the AI more capable, but about **deciding what the AI should be responsible for, how to verify its output, and how to evaluate the system honestly.**

### Engineering: Knowing Where AI Adds Value

One of the most valuable lessons was learning to separate probabilistic AI behavior from deterministic application logic.

In VibeMatch 1.0, users supplied predefined genres, moods, and energy preferences, and the recommendation algorithm calculated scores using fixed rules. For VibeMatch 2.0, I wanted users to describe what they were looking for naturally, such as music for reading on a rainy afternoon or something energetic for a workout.

My initial instinct was to give the language model a larger role in the recommendation process. However, as I explored the architecture, I began to see why this could make the system harder to test, explain, and reproduce.

I ultimately chose a hybrid approach: **Gemini interprets the user's language, while Python performs the actual recommendation and ranking.** Gemini identifies relevant genres and moods from the catalog's vocabulary. The deterministic engine then matches those preferences against real track metadata, assigns scores, and generates explanations based on verified attributes.

This separation helped me understand an important software engineering principle: using AI effectively doesn't mean using it everywhere. A language model is valuable where ambiguity and natural language are involved, while conventional algorithms may be better suited to operations that require consistency, predictability, and reproducibility.

### Reliability: Correctness Comes With Trade-offs

Implementing strict validation was another turning point in the project.

I wanted to prevent Gemini from inventing genres or moods that didn't exist in the catalog. To accomplish this, I added structured-output requirements and Python validation that checks the model's response against the actual available tags.

Initially, I saw validation mainly as a safeguard against hallucinations. The live evaluation showed me that its consequences are more complicated.

When I searched for *dark, atmospheric electronic music with a cinematic feeling*, the application rejected Gemini's response because it couldn't be validated against the catalog. From a technical perspective, the safeguard worked: the system refused to proceed with unverified information. But from a user's perspective, it was a disappointing experience because the original request was perfectly reasonable.

In contrast, when I requested traditional zydeco music, the application couldn't identify supported preferences and appropriately declined to generate unrelated recommendations.

These two cases helped me distinguish between **preventing incorrect output and providing a good user experience**. A system can behave correctly according to its rules while still failing to satisfy a legitimate request.

If I continue developing VibeMatch, one improvement I would prioritize is helping users recover from validation failures through clearer feedback, clarification, or carefully controlled alternatives, without compromising the integrity of the recommendations.

### Evaluation: Passing Tests Is Not the Same as Building a Good Recommender

Perhaps the biggest lesson came from evaluating the finished application.

By the end of development, VibeMatch had **275 passing automated tests**, including tests for input validation, deterministic ranking, evidence consistency, and regression protection. The offline evaluation also confirmed that the recommendation engine followed its documented scoring rules.

These results gave me confidence in the software's correctness. However, the five live Gemini searches revealed limitations that the tests alone could not capture.

For example, my energetic-workout query produced ten recommendations from only three distinct artists. The recommendations followed the ranking algorithm correctly, but the resulting list lacked variety. Another query returned several songs from the same artist because many tracks received identical scores and were ordered by track ID.

I also realized that matching catalog tags does not necessarily mean a song is musically appropriate for a particular listener. Since VibeMatch does not analyze audio, I cannot claim that a recommendation actually sounds relaxing, energetic, or suitable for a workout simply because its metadata contains those labels.

This experience taught me to distinguish between several different questions: Does the code work as intended? Does the language model interpret the request appropriately? Do the recommendations satisfy the user's expectations? These questions require different evaluation methods, and success in one does not guarantee success in the others.

I became more comfortable documenting weaknesses rather than treating every unexpected result as something that needed to be hidden or immediately fixed. The repeated artists, coarse scoring system, and rejected requests became meaningful findings that helped me understand where the next improvements should be made.

### Final Takeaway

This project was also an exercise in learning how to collaborate critically with AI coding tools. I used AI assistance throughout planning, implementation, debugging, and documentation, but I learned the importance of reviewing proposed changes, questioning assumptions, preserving working behavior, and requiring evidence before accepting results.

My perspective shifted from simply getting an AI-assisted application to work toward understanding **why it works, where it fails, and what the available evidence actually proves**.

VibeMatch 2.0 is not a perfect recommendation system, and I don't consider its limitations a failure of the project. Instead, they are among its most valuable outcomes. I now have a better appreciation for how software architecture, reliability engineering, automated testing, and human evaluation work together.

Most importantly, I learned that building trustworthy AI applications requires more than integrating a powerful model. It requires thoughtful boundaries, transparent behavior, and the willingness to critically evaluate the system—even when all the tests are passing.

---

## Appendix A: Model Card for VibeMatch 1.0 (original)

> **Preserved from the original V1 model card.** Everything below describes **VibeMatch 1.0** only: the rule-based recommender over 20 synthetic songs. Its section numbers (1 to 9) are the original V1 numbering and are independent of the V2 sections above. The only edit to this text is one-level heading demotion.

### 1. Model Name

**VibeMatch 1.0**, a rule-based music recommender simulation.

---

### 2. Intended Use

**Goal.** Given a listener's favorite genre, favorite mood and target energy level, suggest the five songs in a small catalog that fit best, and explain each suggestion.

**Intended use.** Classroom exploration of how a content-based recommender turns data into a ranking, and of where bias can appear. It assumes a listener can state one favorite genre, one favorite mood and an energy level from 0 to 1, and that these describe what they want right now.

**Not intended for.** Real users of a music service, ranking real songs or artists, or any decision where fairness to listeners or artists matters. It was tested only on this 20-song catalog and five profiles, and we have no evidence of how well it predicts what real people enjoy.

---

### 3. How the Model Works

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

### 4. Data

The catalog is `data/songs.csv`: **20 songs**, one row each, with title, artist, genre, mood and five numeric features (energy, tempo, valence, danceability, acousticness). Only genre, mood and energy are used for scoring.

- **Genres:** 17 different labels. Lofi has 3 songs and pop has 2; the other 15 genres (for example rock, jazz, metal and classical) have exactly one song each.
- **Moods:** 15 different labels. "Chill" appears 3 times, "happy", "intense" and "relaxed" twice each, and the other 11 moods once.
- **Energy:** ranges from 0.18 to 0.98. Eight songs are at 0.75 or higher, eight are at 0.45 or lower, and only four fall in between.
- **Missing:** lyrics, language, release year, popularity and listening history. Each song has a single genre and mood label, and related genres such as "pop" and "indie pop" are separate labels. Some tastes are covered by one song or none, so a rock listener has only one rock song to match.

---

### 5. Strengths

These are observations from our five test profiles and our automated tests, not measures of recommendation quality.

- **Clear top results when the profile fits the catalog.** For High-Energy Pop, Chill Lofi and Deep Intense Rock, the #1 song matched genre, mood and energy (scores 3.97, 3.98 and 3.99). In our judgment these matched what each profile asked for. Chill Lofi gave the cleanest list, with three lofi songs in the top three.
- **Explainable recommendations.** Every recommendation lists which rules earned points (genre, mood, energy), so it is easy to see why a song ranked where it did.
- **Deterministic ranking.** The same input always gives the same output, regardless of the order of songs in the catalog, and ties are broken by song ID. All scores stayed between 0 and 4 in every run.
- **Tested behavior.** 18 automated tests pass. They cover ranking order, expected score values, result limits (including `k=0` and `k` larger than the catalog), explanation contents, tie-breaking, and consistency between the `Recommender` class and the functional code. These tests check that the code does what we intended, not that the recommendations suit real listeners.

---
### 6. Limitations and Bias

In the baseline evaluation, the high genre weight sometimes produced questionable rankings: Winter Nocturne, with energy 0.18, ranked first for a user targeting energy 0.95, while Focus Flow outranked Spacewalk Thoughts despite the latter matching the user's preferred mood. The system also relies on exact genre and mood matching, and 15 of the 17 genres in our 20-song dataset contain only one song, limiting the variety of relevant recommendations. Across the five baseline profiles, 11 of the 25 top-five recommendations matched neither genre nor mood, demonstrating how the system fills remaining positions using energy similarity alone. The weight-shift experiment changed the rankings for only one of the five profiles, showing that the impact of adjusting weights depends on the particular preferences and available songs. Although these results demonstrate limitations in ranking behavior, we have not measured actual listener satisfaction, and potential filter bubbles remain a theoretical concern rather than an observed outcome.

---

### 7. Evaluation

#### How we tested

We ran the recommender on the 20-song catalog (`data/songs.csv`) with five profiles: three standard (High-Energy Pop, Chill Lofi, Deep Intense Rock) and two adversarial (Conflicting Preferences, Absent Genre). Each run returns five ranked songs, and we checked each score out of 4.00 and its explanation (points for genre, mood and energy closeness). We then ran a weight-shift experiment to test how sensitive the rankings are. The full terminal output for every profile is in the README under "Recommendation Evaluation — User Profiles".

#### Standard profiles

All three produced strong top recommendations that matched genre, mood and energy.

- **High-Energy Pop (pop / happy / 0.85):** #1 was Sunrise City (3.97). Notably, #3 Rooftop Lights (1.91) is happy and high-energy but labeled "indie pop", so it earned no genre credit.
- **Chill Lofi (lofi / chill / 0.40):** #1 was Midnight Coding (3.98), and the top three were all lofi. Notably, Focus Flow (lofi, "focused", 3.00) outranked Spacewalk Thoughts (ambient, chill, 1.88).
- **Deep Intense Rock (rock / intense / 0.92):** #1 was Storm Runner (3.99). The rest of the list was weaker because the catalog has only one rock song: #2 Gym Hero (1.99) is a pop song matching only the mood, and #3 to #5 (all under 1.0) matched neither genre nor mood.

#### Comparing the standard profiles

- **Pop vs. Lofi:** no songs in common. Every Pop result has energy 0.76 or higher, every Lofi result 0.42 or lower. The cause is mainly the energy targets (0.85 vs. 0.40), plus different genres and moods.
- **Pop vs. Rock:** three songs appear on both lists, for different reasons. Gym Hero is #2 on both: 2.92 for the genre "pop" in one, 1.99 for the mood "intense" in the other. Storm Runner is #5 for Pop (0.94, energy only) but #1 for Rock (3.99). Both profiles want high energy, which explains the overlap; genre and mood explain the differences.
- **Lofi vs. Rock:** no songs in common. Lofi's top three all score 3.00 or higher, while Rock has one strong result, then 1.99, then below 1.0. The energy targets are far apart (0.40 vs. 0.92), and the catalog holds three lofi songs but one rock song.

#### Adversarial profiles

**Conflicting Preferences (classical / intense / 0.95).** *Observation:* under the original weights, #1 was Winter Nocturne (2.23), a quiet classical piece (energy 0.18), ahead of Gym Hero (1.98) and Storm Runner (1.96), which match the mood and energy target. *Why:* as the only classical song, it earned the full +2.0 genre bonus plus +0.23 for energy, while Gym Hero earned +1.0 for mood and +0.98 for energy. The 1.0-point genre-over-mood advantage exceeded Gym Hero's 0.75-point energy advantage. *Interpretation:* one heavily weighted category can outweigh a poor fit on everything else.

**Absent Genre (k-pop / happy / 0.80).** *Observation:* no song is k-pop, so none could earn genre points. The top two (Sunrise City 1.98, Rooftop Lights 1.96) are the only "happy" songs. Places #3 to #5 (Calle Luna 0.96, Night Drive Loop 0.95, Storm Runner 0.89) matched neither genre nor mood and were chosen only for energy near 0.80. The program gave no notice that the genre was missing. *Interpretation:* a missing genre simply scores zero and the remaining slots are filled by energy, so the system cannot say "I couldn't find what you asked for."

#### Weight-shift experiment

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

#### Summary

The system worked well when a listener's preferences matched the catalog: the standard profiles all produced strong top recommendations with sensible explanations. We were surprised that the weight change rarely altered a ranking, and that a calm classical piece could win a request for very high energy. Remaining limitations are exact text matching, a small catalog, and lists filled out by energy alone once real matches run out (see Section 6). We cannot claim objective accuracy, because we have no listener feedback or ground-truth data; these tests show how the algorithm behaves, not how well it predicts what people enjoy.

---

### 8. Future Work

In priority order:

1. **Expand the dataset and represent musical diversity better.** Add many more songs, with several songs per genre and mood, so a profile like rock has real alternatives after its first match. Allow a song to carry more than one genre or mood, and cover a wider range of styles.
2. **Introduce listener feedback and evaluate relevance.** Collect real signals such as likes, skips and replays, or ratings. This would let us check whether the rankings match what people enjoy, which our tests cannot show, and tune the weights from evidence instead of by hand.
3. **Improve related-genre matching and diversity.** Give partial credit to related genres (for example pop and indie pop), keep the top five from being all one style, and tell the listener when nothing in the catalog matches their genre instead of silently filling the list by energy alone.

A possible extension is to use the data columns we currently ignore, such as tempo, valence and acousticness.

---

### 9. Personal Reflection

This project helped me understand how a recommendation system can translate user preferences into numerical scores and ranked results without requiring a complex machine-learning model. One of my biggest learning moments was realizing how strongly the choice of scoring weights influences the behavior of an algorithm. A relatively simple formula could produce seemingly personalized recommendations while also generating unexpected results when different preferences conflicted.

AI tools were particularly useful for designing the scoring algorithm, implementing the Python functions, and developing test cases. They also helped me identify edge cases that I might not have considered initially, such as conflicting preferences and genres missing from the dataset. However, I needed to verify the generated code, check the score calculations, and compare the AI's predictions against actual program output rather than relying on its explanations alone.

The most surprising result came from the weight-shift experiment. I expected changing the relative importance of genre and energy to affect several recommendation lists, but four of the five profiles retained exactly the same rankings. Only the conflicting-preferences profile changed significantly, with Winter Nocturne falling from first to tenth place. This demonstrated that changes to an algorithm do not necessarily affect every user or produce universally better recommendations.

If I continued developing this project, I would expand the dataset to include a wider range of musical styles and more nuanced musical features. I would also explore ways to incorporate listener feedback, recognize similarities between related genres, and balance personalized recommendations with musical discovery. As a musician, I am especially interested in how a recommendation system might represent musical characteristics that are not adequately captured by broad categories such as genre, mood, or energy.
