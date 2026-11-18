# VibeMatch 2.0 Reliability Evaluation

This report separates **offline pipeline checks**, **mocked-model tests**, and **five live Gemini observations** for VibeMatch 2.0. The offline checks measure conformity to documented rules; the live sample shows observed behavior on a small set of requests. Neither establishes general Gemini accuracy or listener satisfaction.

## Three kinds of evidence (kept separate)

| Kind | What it is | Where | What it can show |
|---|---|---|---|
| **Offline deterministic evaluation** | 12 scenarios run through the real validator, pipeline and recommender on the real 5,000-track catalog, using *predefined* interpretations. No model, no network, no API key. | `scripts/evaluate_v2.py`, `docs/evaluation_results.csv` | Ranking, evidence and validation behave as documented; result-set diversity. |
| **Mocked-model tests** | Unit tests with a fake Gemini client returning chosen text. | `tests/test_intent.py`, `tests/test_pipeline.py`, `tests/test_app.py` | The validation contract and error handling work. Says nothing about model quality. |
| **Live Gemini observations** | Real model responses seen by a human. | Section 5 below | Five manually observed interactions using the 5,000-track catalog (UI exports in [`evidence/live/`](evidence/live/README.md)); an earlier 2,500-track observation is kept separate as historical context. |

In the offline evaluation, **no Gemini output is simulated and labeled as model performance.** The interpretation for each scenario is either a human-selected *reference interpretation* (what a sensible reader would expect, chosen by the project author and open to review) or a *hand-written candidate response* used to test rejection. Both are labeled "not a Gemini response" in every result row.

## Reproduce

```bash
.venv/bin/python scripts/evaluate_v2.py        # offline; rewrites docs/evaluation_results.csv
.venv/bin/python -m pytest -q tests/test_evaluation.py
```

Output is deterministic (no timestamps, randomness or network). A test regenerates the results and fails if `docs/evaluation_results.csv` is out of date.

`docs/live_recommendations.csv` is **not** produced by this script: it was transcribed by hand from the live UI exports. A small offline test checks its shape and cross-checks it against those exports (Section 5.1).

## 1. Scenarios

Reference tags were checked against the actual `data/jamendo_5000.csv` vocabulary (a test enforces this, and that each reference matches at least one track).

| ID | Request | Reference genres | Reference moods | Purpose |
|---|---|---|---|---|
| S01 | Relaxing ambient music | ambient | relaxing | Genre + mood |
| S02 | Energetic rock | rock | energetic | Genre + mood |
| S03 | Happy pop | pop | happy | Genre + mood |
| S04 | Calm jazz | jazz | calm | Genre + mood; few tracks carry both |
| S05 | Dark atmospheric music | atmospheric | dark | `atmospheric` exists only as a *genre* tag |
| S06 | Music for reading | (none) | calm, relaxing | Mood-only; no genre implied |
| S07 | Music for exercise | (none) | workout, sport | Mood-only; alternatives (OR) |
| S08 | Classical music | classical | (none) | Genre-only |
| S09 | Calm death metal | deathmetal | calm | Conflicting/unusual: no track has both |
| S10 | Metalcore | metalcore | (none) | Supported but very sparse (1 track) |
| S11 | Vaporwave | (none) | (none) | **Negative:** unsupported subgenre; candidate `vaporwave` must be rejected |
| S12 | Surprise me | (none) | (none) | **Negative:** ambiguous; empty interpretation must be rejected |

S01–S10 are positive scenarios (expected: recommendations). S11–S12 are negative (expected: a specific rejection). In S11/S12 the reference interpretation is empty because nothing supported is justified.

In addition, 18 invalid-input cases (`X01`–`X18`) are tested for rejection: blank, whitespace-only, non-string and over-length queries; unsupported tags; a mood in the genre field and vice versa; more than 2 tags; missing or extra fields; non-JSON and markdown-fenced JSON; wrong types; one valid plus one unsupported tag (no partial acceptance); an empty interpretation; and unsupported or empty preferences sent straight to the recommender.

## 2. Metric definitions

All counts are `numerator/denominator` with the denominator stated.

- **A. Offline execution success:** scenarios whose outcome matches the expectation (recommendations for S01–S10, the named rejection for S11–S12), over all 12.
- **B. Ranking correctness:** for each result set, an *independent re-implementation inside the harness* of the documented rule (+2 if any requested genre matches, +1 if any requested mood matches, drop zero scores, sort by score descending then numeric track ID ascending, keep 10) must reproduce the returned track IDs, scores and order exactly. Denominator: result sets produced (10).
- **C. Evidence consistency:** for every returned recommendation, the matched genres and moods must equal exactly the requested tags the track really carries, and the explanation must equal the fixed template over those tags with no audio-claim words. Reported per recommendation and per scenario.
- **D. Artist diversity at 10:** `distinct_artists / returned_tracks` for each result set (case-insensitive artist name). The denominator is the number *returned*, so a short list is not penalized. Reported as mean, min and max over result sets.
- **E. Recommendation coverage:** valid scenarios returning at least one positive-score match, over valid scenarios (10).
- **F. Invalid-input rejection:** F1 = negative scenarios rejected with the expected error and no recommendations, over negative scenarios (2). F2 = the same check over the 18 invalid-input cases. For query cases it also requires that Gemini was never called.

## 3. Measured results (offline, 5,000-track catalog, k = 10)

| Metric | Result |
|---|---|
| A. Offline execution success | 12/12 (100%) |
| B. Ranking correctness | 10/10 result sets (100%) |
| C. Evidence consistency | 91/91 recommendations (100%); 10/10 scenarios |
| D. Artist diversity at 10 | mean 0.650 (all 10 result sets, including one 1-track list); **mean 0.611** across 9 full top-10 lists; min 0.400 among full lists |
| E. Recommendation coverage | 10/10 (100%) |
| F1. Invalid scenarios rejected | 2/2 |
| F2. Invalid-input cases rejected | 18/18 |
| Short result lists (< 10) | S10 only (1 result) |

Per scenario:

| ID | Results | Score distribution (score×count) | Distinct artists | Diversity | Distinct genres in results | Most repeated artist |
|---|---:|---|---:|---:|---:|---|
| S01 | 10 | 3×10 | 7 | 0.700 | 12 | Dreamweaver (4) |
| S02 | 10 | 3×10 | 6 | 0.600 | 11 | Creo (3) |
| S03 | 10 | 3×10 | 9 | 0.900 | 21 | Disconauts Music Production (2) |
| S04 | 10 | 3×4, 2×6 | 6 | 0.600 | 17 | Tom La Meche (5) |
| S05 | 10 | 3×10 | 5 | 0.500 | 14 | David Schombert (4) |
| S06 | 10 | 1×10 | 4 | 0.400 | 10 | Mel's (5) |
| S07 | 10 | 1×10 | 7 | 0.700 | 19 | Fresh Body Shop (2) |
| S08 | 10 | 2×10 | 6 | 0.600 | 7 | Fadièse (3) |
| S09 | 10 | 2×10 | 5 | 0.500 | 9 | APOC4LYP53 (5) |
| S10 | 1 | 2×1 | 1 | 1.000 | 5 | Badger (1) |
| S11 | 0 | rejected: `InvalidModelResponseError` | | | | |
| S12 | 0 | rejected: `NoConfidentInterpretationError` | | | | |

Full rows, including the recommended track IDs, are in `docs/evaluation_results.csv`. **Diversity denominator note:** S10 has one returned track, hence a diversity ratio of 1/1 = 1.000; its inclusion raises the unweighted mean to (0.700 + 0.600 + 0.900 + 0.600 + 0.500 + 0.400 + 0.700 + 0.600 + 0.500 + 1.000) / 10 = **0.650**. Across only the nine complete 10-track lists, the mean is 5.500 / 9 = **0.611**. The 0.611 value is more representative of variety within full recommendation lists; neither mean is a listener-satisfaction measure.

### How to read these numbers

- **A, B, C, E, F are regression guards, not accuracy claims.** The recommender is deterministic and the checks recompute its own documented rules, so 100% is the expected outcome. They show the system behaves as specified and that the checkers *can* fail (tests feed them deliberately corrupted results). They do not show that the recommendations are good.
- **E (coverage) is close to guaranteed by design.** Requests are rejected unless every tag exists in the catalog, and every catalog tag occurs on at least one track, so a validated request cannot return nothing. It is therefore not an informative quality signal.
- **D is the informative result, and it is a weakness** (see below).

## 4. Notable weaknesses found

1. **Low artist diversity in some top-10 lists.** Ties are broken by lowest track ID only, so one artist's consecutive uploads can fill the list: S06 returns 4 artists for 10 tracks (Mel's has 5), S04 and S09 have an artist with 5 of 10. The catalog caps artists at 5 tracks, but nothing limits repeats within a result set. No diversification has been implemented.
2. **A requested mood can be ignored in practice (S09, "Calm death metal").** No track has both `deathmetal` and `calm`, so the top 10 are all deathmetal tracks with score 2 and none is calm. The scores and explanations are honest ("Matches your requested deathmetal genre."), but the interpretation panel will show *calm* even though no result matches it.
3. **Mood-only requests cap at 1 out of 3 (S06, S07).** A perfect mood match scores 1/3 because genre points are unavailable. The score is a fixed rule, not a quality rating, but it can look low to a user.
4. **Scores are coarse.** Only 0, 1, 2 or 3 are possible, so large groups tie and are ordered by ID, which favors older uploads.
5. **Sparse tags give short lists (S10).** Only 1 track carries `metalcore`. The app shows 1 card rather than padding, which is correct but may feel thin.
6. **Category confusion fails the whole request.** `atmospheric` is a genre here, not a mood (S05). If Gemini placed it in the mood field the response would be rejected entirely, by design, rather than corrected. This protects correctness but costs the user a retry.
7. **The reference interpretations are one author's judgment.** They have not been reviewed by an independent person, and some are debatable (for example mapping "exercise" to `workout` and `sport`, or "reading" to `calm` and `relaxing`).

## 5. Live Gemini evaluation — five observed searches

### 5.1 Method, provenance, and limitations

Five natural-language requests were submitted manually through the **Streamlit UI** using the **5,000-track MTG-Jamendo catalog** (top-k = 10). Gemini produced the interpretations; Python validated them against the catalog vocabulary; the deterministic recommender selected songs and generated match explanations. The offline evaluation script did not produce any of this.

**Three kinds of live evidence, and which one backs what.** The five original UI exports are preserved in [`docs/evidence/live/`](evidence/live/README.md) ([`query1.md`](evidence/live/query1.md) to [`query5.md`](evidence/live/query5.md)).

| Item | Status | Source |
|---|---|---|
| **Observed UI output:** the interpretation panel (genres and moods), result cards with ranks, titles, artists, scores, matched tags and explanations, and the two fixed error messages | **Corroborated** by the exports | `evidence/live/query1.md` to `query5.md` |
| **Query text** (the sentence the tester typed) | **Manually recorded** by the tester. It is **not** in the exports (the exported pages do not echo the query), so it cannot be verified from the repository. | Tester's record, reproduced in Section 5.3 |
| **Raw Gemini responses** (JSON), model version, token usage, latency, timestamps, track IDs | **Not captured** | None |

So the displayed tags (for example `workout` in Q2) are things Gemini's validated answer led the UI to show; the exports do not show the raw model output behind them. The exports also cannot show what was typed, and for Q3 and Q5 they show only a fixed message.

`docs/live_recommendations.csv` records **all 30 displayed tracks** from Q1, Q2 and Q4 by query, rank, title, artist, score and matched tags. It was transcribed by hand from the exports and does **not** invent missing track IDs. `tests/test_evaluation.py` checks it offline: 30 rows, query IDs, ranks, scores, artist counts, agreement with the exports, and the diversity means quoted below. The Q3 export does not reveal the invalid field, so that is unknown.

These five intentionally varied requests are **observations**, not a representative sample or a population-level accuracy estimate. URLs pointing to `localhost:8501` inside the exports are local-only page anchors.

### 5.2 Live results at a glance

| ID | Request focus | Observed genres | Observed moods | UI outcome | Results | Distinct artists | Highest score | UI export |
|---|---|---|---|---|---:|---:|---:|---|
| **Q1** | Relaxing ambient music for reading on a rainy afternoon | `ambient` | `relaxing` | Recommendations returned | 10 | 7 | 3/3 | [query1](evidence/live/query1.md) |
| **Q2** | Upbeat music for a workout | None | `energetic`, `workout` | Recommendations returned | 10 | 3 | 1/3 | [query2](evidence/live/query2.md) |
| **Q3** | Dark, atmospheric electronic music | Not captured | Not captured | Invalid model response rejected | 0 | N/A | N/A | [query3](evidence/live/query3.md) |
| **Q4** | Peaceful, relaxing rock | `rock` | `peaceful`, `relaxing` | Recommendations returned | 10 | 6 | 3/3 | [query4](evidence/live/query4.md) |
| **Q5** | Traditional zydeco with accordion | None available in UI | None available in UI | No usable interpretation | 0 | N/A | N/A | [query5](evidence/live/query5.md) |

**Outcome breakdown (denominator = five live searches):** 3/5 returned track lists; 1/5 was rejected because the interpretation failed validation; 1/5 produced the no-interpretation message. The latter two are distinct, expected UI error paths, though neither produces usable recommendations. A refused or unverified interpretation is not automatically a correct semantic decision.

**Live artist diversity@10:** Q1 = 7/10 (70%), Q2 = 3/10 (30%), Q4 = 6/10 (60%). The unweighted mean across these **three completed top-10 lists** is (0.70 + 0.30 + 0.60) / 3 = **0.533 (53.3%)**. Q3 and Q5 have no results, so diversity is **N/A**, not zero. The corresponding mean for nine *offline* full top-10 lists is 61.1%; the two small samples use different requests and should not be pooled.

### 5.3 Individual observed results

#### Q1 — Relaxing ambient music for reading, on a rainy afternoon

**Manually recorded request** (tester-recorded; not in the export):

> I'm looking for relaxing ambient music to listen to while reading on a rainy afternoon.

This is a different, longer request from the shorter historical query described in the note at the end of Section 5.4, which was run on the 2,500-track catalog.

**Observed UI output** ([`query1.md`](evidence/live/query1.md)): Gemini interpretation panel shows genres `ambient`; moods `relaxing`. **Outcome:** 10 results, all with displayed match score **3/3**; **7 distinct artists** (diversity@10 = 0.70).

| Rank | Song | Artist | Displayed score |
|---:|---|---|---:|
| 1 | New day | Alexander Blu | 3/3 |
| 2 | La gruta del agua | Carlos Saura | 3/3 |
| 3 | FEAT THE VIBE - The dream that you wanted | Alterlabel | 3/3 |

**Observation:** The extraction aligns with explicit words in the request. The ten displayed explanations cite actual matching `ambient` and `relaxing` tags. Dreamweaver occupies ranks 5–8 (four tracks), illustrating artist repetition despite perfect tag scores. This is *tag alignment*, not evidence that the tracks sounded relaxing to listeners.

#### Q2 — Energetic workout music

**Manually recorded request** (tester-recorded; not in the export):

> I need something upbeat and energetic to keep me motivated during an intense workout.

The request names "workout" explicitly, so the `workout` tag is a direct mapping rather than an inferred one.

**Observed UI output** ([`query2.md`](evidence/live/query2.md)): interpretation panel shows no genre; moods `energetic`, `workout`. **Outcome:** 10 results, all **1/3**; **3 distinct artists** (diversity@10 = 0.30).

| Rank | Song | Artist | Displayed score |
|---:|---|---|---:|
| 1 | Virtual defect | POSITIV HATE | 1/3 |
| 2 | Hymn of Darkness | POSITIV HATE | 1/3 |
| 3 | Destruction of christrian's dream | POSITIV HATE | 1/3 |

**Observation:** The model chose supported mood tags without inventing a genre. All ten shown results match `energetic` in the catalog (the export's explanations cite only that tag); none of the displayed explanations claims measured acoustic energy or a `workout` match, and none of the ten carries the `workout` tag. Four positions are by POSITIV HATE, five by Piergiorgio Lucidi, and one by St Adam. **The model's two mood choices do not earn 2 points:** the V2 scorer awards at most +1 for the mood category, and there was no genre credit. This is the clearest live example of low result diversity.

#### Q3 — Dark atmospheric electronic music

**Manually recorded request** (tester-recorded; not in the export):

> I'm in the mood for dark, atmospheric electronic music with a cinematic feeling.

**Observed UI output** ([`query3.md`](evidence/live/query3.md)), the message shown:

> Gemini's answer couldn't be verified against our catalog, so it was discarded. Try rephrasing your request.

**Outcome:** No recommendations. The raw model response was not recorded, so **the rejected tags, category assignment, and exact failure cause are unknown**. The failure must not be attributed specifically to `atmospheric` or any other field. The guardrail prevented an unverified interpretation from reaching ranking, but the user had to retry or rephrase. This demonstrates a **safety-versus-availability trade-off**, not successful music discovery.

#### Q4 — Peaceful, relaxing rock music

**Manually recorded request** (tester-recorded; not in the export):

> Find me peaceful, relaxing rock music that isn't too aggressive.

**Observed UI output** ([`query4.md`](evidence/live/query4.md)): interpretation panel shows genre `rock`; moods `peaceful`, `relaxing`. **Outcome:** 10 results, **nine at 3/3** and **one at 2/3**; **6 distinct artists** (diversity@10 = 0.60).

| Rank | Song | Artist | Displayed score |
|---:|---|---|---:|
| 1 | Flying on the Sea II | Giulio Nightfall | 3/3 |
| 2 | Why | Kai Klaas | 3/3 |
| 3 | Psalm 148 | Jason Silver | 3/3 |

**Observation:** Gemini retained the explicit rock genre and interpreted the softer mood. The top nine explanations cite `rock` and `relaxing`; the tenth ("Anastasia" by AS-POTIRONT!) cites `rock` only, earning 2/3. Ant_DK appears at ranks 4–8 (five tracks). No audio was analyzed, so the result cannot confirm that the songs are actually non-aggressive.

#### Q5 — Traditional zydeco with accordion

**Manually recorded request** (tester-recorded; not in the export):

> I want traditional zydeco music with a lively accordion sound.

**Observed UI output** ([`query5.md`](evidence/live/query5.md)), the message shown:

> We couldn't match that to a genre or mood in our catalog. Try naming a genre (like ambient or rock) or a mood (like calm or happy).

**Outcome:** No recommendations. The UI exposes **no usable genre or mood**. That is consistent with the application's abstention behavior, and it avoids presenting unrelated matches merely to fill the list. The export does **not** disclose the raw model output, and this observation does not establish whether suitable zydeco tracks exist outside the selected catalog or that an accordion-feature request can never be served.

### 5.4 What these five live searches establish

- **Interpretation and integration:** Three searches produced catalog-supported tags and track lists in the real application, including a mood-only request whose wording named "upbeat", "energetic" and "workout" (mapped to `energetic` and `workout`) and a rock request combined with softer moods (`peaceful`, `relaxing`).
- **Defensive validation:** One response was rejected and one request produced no usable interpretation. The UI handled both without manufacturing recommendations; neither outcome guarantees that Gemini understood the query correctly.
- **Artist diversity:** Three completed top-10 lists included between three and seven distinct artists. Equal-score tie-breaking by track ID can cluster one artist's tracks.
- **Evidence boundaries:** The shown match scores and explanations describe **tag-based rule matches**, not AI confidence, audio similarity, quality, or human enjoyment.
- **Evidence boundaries of the exports:** the interpretation panels, result cards and the two error messages are corroborated by the preserved exports. The typed query text is the tester's manual record, and raw Gemini responses were not captured.
- **Human judgment:** No numeric appropriateness, musical-relevance, or explanation-quality ratings have been assigned. No systematic listening review has been carried out.

**Historical observation — different query and catalog, excluded from the five-query metrics:** An earlier live request, the short query "Relaxing ambient music for reading", returned Gemini tags `ambient` and `relaxing` on the **2,500-track** catalog. It is **not** Q1: Q1 is the longer rainy-afternoon request above, run later on the **5,000-track** catalog. The two share a topic and the same two displayed tags, but they are different requests on different catalogs, and the historical one has no preserved export.

## 6. Human evaluation rubric and recording sheet

The five live interactions above have **observed model outputs**, but they have **not been assigned human ratings**. Complete ratings only after a reviewer evaluates them explicitly. The exact commands to run the app are `.venv/bin/python -m streamlit run app.py` with `GEMINI_API_KEY` configured. The displayed titles and catalog tags alone do not demonstrate acoustic similarity; listening via Jamendo links would strengthen any claim about musical relevance.

**Rating scales (1–5)**

| Rating | Interpretation appropriateness | Recommendation relevance | Explanation accuracy |
|---|---|---|---|
| **1** | Returned tags are unrelated to or contradict the request. | None of the returned tracks plausibly fits the request. | Explanations name tags the track lacks or make unsupported claims. |
| **3** | Partly right: a key preference is missing or a chosen tag is questionable. | About half of the returned tracks plausibly fit. | Grounded tags are used, but multiple explanations are contextually unhelpful or misleading. |
| **5** | Every chosen tag is justified by the request, without an obvious missing preference. | Nearly all returned tracks plausibly fit (preferably checked by listening). | Each explanation is factually grounded and useful to a listener. |

Values 2 and 4 indicate intermediate quality. Use **N/A** for a dimension that cannot be assessed (for example, recommendation relevance when no tracks were returned); leave **unrated** dimensions blank, not zero. For Q3 the model tags are **not captured**, so model-level interpretation appropriateness cannot be rated from this evidence. For Q5 a reviewer may assess whether *abstention* is sensible, separately from a tag-accuracy rating. Offline metric C already checks exact template/tag consistency; this human scale asks whether the explanations are *useful*.

| ID | Query focus | Actual Gemini genres | Actual Gemini moods | Interpretation (1–5) | Musical relevance (1–5) | Explanation (1–5) | Artists in results | Reviewer notes |
|---|---|---|---|---|---|---|---|---|
| Q1 | Ambient reading (rainy afternoon) | `ambient` | `relaxing` | | | | 7 of 10 | All 10 shown at 3/3; 4 Dreamweaver tracks |
| Q2 | Energetic workout | None | `energetic`, `workout` | | | | 3 of 10 | All 10 shown at 1/3; 4 POSITIV HATE and 5 Piergiorgio Lucidi tracks |
| Q3 | Dark electronic | Not captured | Not captured | | N/A | N/A | N/A | Validation rejection; cause not captured |
| Q4 | Peaceful rock | `rock` | `peaceful`, `relaxing` | | | | 6 of 10 | Nine 3/3, one 2/3; 5 Ant_DK tracks |
| Q5 | Zydeco/accordion | No usable tags shown | No usable tags shown | | N/A | N/A | N/A | No confident interpretation; abstention merits separate review |

**Review procedure to complete later:** Record reviewer identity (or anonymized reviewer ID), date, whether tracks were listened to, rating rationale, and any re-run differences. None of these attributes is inferred from the captured exports.

## 7. Reliability safeguards (implemented)

| Safeguard | Where | Covered by |
|---|---|---|
| Query validation: rejects blank, whitespace-only, non-string and over-500-character queries before any API call | `src/intent.py` (`validate_query`) | `tests/test_intent.py`, cases X01–X04 |
| Gemini structured output: JSON mode with an explicit schema (`genres`, `moods`, max 2 each, no extra fields) | `src/intent.py` (`RESPONSE_SCHEMA`) | `tests/test_intent.py` (mocked client) |
| Independent Python validation of the response: structure, types, normalization, deduplication, per-category vocabulary, at most 2 tags, at least one tag | `src/intent.py` (`parse_model_response`) | `tests/test_intent.py`, cases X05–X16 |
| Unsupported-tag rejection with no partial acceptance and no remapping | `src/intent.py`; `src/v2_recommender.py` (`UnsupportedTagError`) | S11, X05–X08, X15, X17 |
| Distinct error types (invalid query, missing key, service failure, invalid response, no interpretation) with fixed, safe user messages | `src/intent.py`, `src/pipeline.py`, `app.py` | `tests/test_pipeline.py`, `tests/test_app.py` |
| Deterministic ranking: fixed scoring (+2 genre, +1 mood), ties by ascending track ID, no randomness | `src/v2_recommender.py` | `tests/test_v2_recommender.py`, metric B |
| No zero-score filler: fewer than 10 matches returns fewer than 10 | `src/v2_recommender.py` | S10, `tests/test_evaluation.py` |
| Evidence-grounded explanations built from a fixed template over actually matched tags | `src/v2_recommender.py` | metric C |
| No fabricated audio analysis: the catalog has no energy, tempo or valence, the UI states that no audio is analyzed, and the score is labeled a fixed rule rather than an AI confidence | `data/jamendo_5000.csv`, `app.py` | `tests/test_jamendo_data.py`, `tests/test_app.py` |
| Gemini called once per request, never retried, and never used for ranking or explanations | `src/pipeline.py` | `tests/test_pipeline.py` |
| No API keys in the repository: read from `GEMINI_API_KEY` only; `.env` and `.streamlit/secrets.toml` are git-ignored; error messages never include exception text | `src/intent.py`, `.gitignore`, `app.py` | `tests/test_intent.py`, `tests/test_app.py` |
| Streamlit result persistence: the last successful result survives reruns without a new Gemini call, and a failed or empty new search clears it | `app.py` (`st.session_state`) | `tests/test_app.py` |
| No automated test uses the network or a real key | test fixtures | `tests/test_*.py` |

## 8. Limitations of this evaluation

- **Offline scope:** only 12 scenarios with reference interpretations authored by one person. The 100% execution, ranking and evidence metrics are **rule-conformance regression checks**, not independent measures of recommendation quality.
- **Live scope:** only five deliberately selected, manually observed requests. We saw three usable results, one rejected interpretation, and one no-interpretation message. Those observed counts do not estimate general accuracy, rejection rate, or availability.
- **Missing raw model data:** the live exports omit raw Gemini JSON, exact model/version metadata, track IDs, timestamps, latency, and the cause of Q3's invalid response. We therefore cannot diagnose Q3's specific failure or independently replay the five model calls from these exports.
- **No listening study:** subjective musical relevance, listener satisfaction, and audio properties have **not** been measured. Tags are uploader-provided and subjective; explanations confirm catalog matching, not sonic quality.
- **Artist repetition and coarse ranking:** scores only reflect genre (+2) and mood (+1). Many tracks tie; track-ID tie-breaking can favor clusters of releases by the same artist. No within-list diversification is implemented.
- **Catalog limits:** 5,000 selected Jamendo tracks are not representative of Jamendo overall. Some requested styles are absent or too sparse; existing URLs may be stale. See `docs/DATASET.md` for provenance and licensing.
- **Strict rejection trade-off:** validation prevents unsupported tags from reaching ranking but requires the user to rephrase after any rejected response. No automatic retry, fallback interpretation, or semantic tag recovery is implemented.
- **Comparability:** the 0.611 offline and 0.533 live full-list diversity means come from different scenario sets and should be compared descriptively only, not as a statistically valid performance difference.
