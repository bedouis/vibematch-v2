# AI Interactions Log

> **Stretch features only.** The two sections below (Agentic Workflow and Design Pattern) are from the course template and are filled in for the V2 work. The sections after them record how AI was actually used during VibeMatch 2.0.

**How to read this log.** It is built from the repository history and the working record of the V2 development session, not from saved transcripts. It does **not** contain verbatim prompts. The conversation for the earliest V2 setup step (cloning V1 and verifying the baseline) was lost and is described only from what the repository shows. For VibeMatch 1.0, the original model card's reflection ([model_card.md](model_card.md), Appendix A, Section 9) is preserved and states that AI tools helped design the scoring algorithm, implement the functions and develop test cases.

---

## Agentic Workflow (SF8)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**What task did you give the agent?**

Build VibeMatch 2.0 on top of the finished V1 project, in separate stages, each with its own prompt: recover and audit the project state; prepare a Python 3.13 environment; build a 5,000-track catalog from real MTG-Jamendo metadata; write a deterministic recommender; add a Gemini intent interpreter; connect them in a Streamlit app; add result persistence; expand the catalog and results; write an offline evaluation; clean up the evaluation evidence; and write the final documentation.

**Prompts used:**

Verbatim prompts are not reproduced here. Every stage used the same structure, which was important to how the work went: an objective, a numbered task list, an explicit **constraints** section (for example "do not modify `src/recommender.py`", "no live Gemini calls", "do not commit or push", "do not fabricate evaluation results"), a required report format, and an instruction to **stop and wait for review** after reporting. Several prompts began with a preflight (verify the repository, branch, clean tree, test count and V1 parity) before any change.

**What did the agent generate or change?**

The assistant was Claude Code (Anthropic) running in the VS Code extension, using shell commands, file editing, and one web search. Work by stage, with the commit that recorded it:

| Stage | Commit | What the assistant produced |
|---|---|---|
| Environment | `0c45670` | Rebuilt `.venv` on Python 3.13, installed dependencies, pinned ranges in `requirements.txt`, extended `.gitignore` for secrets |
| Catalog | `5cb012a` | `scripts/prepare_jamendo.py`, `tests/test_jamendo_data.py`, `docs/DATASET.md`, `data/jamendo_2500.csv` (later replaced by the 5,000-track catalog) |
| Recommender | `cb08075` | `src/v2_recommender.py`, `tests/test_v2_recommender.py` |
| Gemini interpreter | `35ebad8` | `src/intent.py`, `tests/test_intent.py` (plus a later compatibility fix after live testing) |
| Pipeline and UI | `c79199a` | `src/pipeline.py`, `app.py`, `tests/test_pipeline.py`, `tests/test_app.py` |
| Expansion | `231c8f5` | `data/jamendo_5000.csv`, top-10 results, updated tests and `docs/DATASET.md` |
| Evaluation | `c0ef4bf` | `scripts/evaluate_v2.py`, `tests/test_evaluation.py`, `docs/EVALUATION.md`, `docs/evaluation_results.csv` |
| Final documentation | (this step) | `README.md`, `model_card.md`, `ai_interactions.md`, `diagrams/architecture.mmd` |

**What did you verify or fix manually?**

The project owner, not the assistant, did the following:

- Ran the Streamlit app in a browser and performed **all live Gemini searches**. The assistant never called Gemini and had no API key; every live result in the project came from the owner (the five page exports in [docs/evidence/live/](docs/evidence/live/README.md)).
- Discovered that `gemini-3.8-flash` timed out (HTTP 504) and that `gemini-3.5-flash-lite` worked, which led to the owner specifying a new default model and changes to some request settings.
- Reviewed each stage's report before approving the next, and made every commit.
- Supplied the exact query wording for the five live searches (the exports do not contain it) and the exports themselves.
- Had the evaluation write-up reviewed and asked for corrections (see below).

---

## Design Pattern (SF10)

> Document how AI helped you choose or implement a design pattern.

**Which design pattern did you use?**

**Dependency injection** for the two external-facing parts, plus a **validate-at-the-boundary** step for model output.

**How did AI help you brainstorm or implement it?**

The requirement came from the prompts: tests must run without credentials and without network access. The assistant implemented it by letting the interpreter accept an injected Gemini `client` (and the pipeline an injected `interpreter`), so tests substitute fakes. For the model's output, the prompt required treating it as untrusted, so the assistant wrote a separate pure function that validates the JSON against the catalog vocabulary before anything downstream sees it. The assistant also used immutable (frozen) dataclasses for the data passed between stages.

**How does the pattern appear in your final code?**

- `interpret_intent(query, vocabulary, *, client=None, model=None)` in `src/intent.py` and `run_pipeline(..., interpreter=None)` in `src/pipeline.py`.
- `parse_model_response(text, vocabulary)` in `src/intent.py` is the validation boundary.
- `MusicTrack`, `RankedRecommendation`, `MusicIntent` and `RecommendationResult` are frozen dataclasses.

---

## Where AI assisted in V2

| Area | What the AI contributed | What was checked |
|---|---|---|
| **Architectural planning** | Proposed the module split (catalog and ranking, intent interpreter, pipeline, UI), the error contract (one exception type per failure mode), and a strict "reject, never repair" rule for model output. The overall architecture and the exclusions (no vector database, embeddings, RAG or agents) were set by the owner's prompts. | Interfaces were inspected in the code before each later stage; the architecture diagram was written from the real call chain. |
| **Dataset processing** | Inspected the official MTG-Jamendo files, found that the two files have different schemas, designed the deterministic selection (rarest-genre group, SHA-256 order, round-robin, artist cap), and checked that 5,000 tracks were achievable (at most 5,887 under the cap). | Output regenerates byte-identically; a test enforces it; counts are reported in `docs/DATASET.md`. |
| **Gemini integration** | Inspected the installed `google-genai` 3.5.0 interfaces, used structured JSON output, wrote the prompt (instructions and vocabulary in the system message, the user's text as JSON data) and the independent validator. | Mocked tests only; the real API behavior was checked by the owner's live runs. |
| **Test generation** | Wrote the 257 V2 tests (the 18 V1 tests predate V2), using fakes for Gemini, blocking network access in test files, and using Streamlit's `AppTest` for the UI. | Tests were run, weak ones were rewritten, and checker tests were run against deliberately corrupted data to show they can fail. |
| **Debugging and review** | Diagnosed failures, re-ran regression checks (full suite and a byte-for-byte comparison of the V1 program's output) after each stage, and reported discrepancies in the prompts' own statements (for example an unclean working tree or a different test count than stated). | The owner reviewed every report. |
| **Evaluation documentation** | Designed the 12 scenarios and metrics, wrote the harness and `docs/EVALUATION.md`, and later transcribed the live observations from the owner's exports. | Numbers were recomputed from the CSV files; subjective ratings were left blank; the owner's independent review led to corrections (below). |
| **Final documentation** | Drafted the README, model card and this log from the code and the evidence files. | Commands were run or dry-run; figures were cross-checked against the evaluation and dataset documents. |

---

## AI suggestions: adopted, corrected, and rejected

**Adopted**

- **Strict validation with no partial results.** The prompt required that unsupported tags never be dropped silently; the assistant implemented whole-reply rejection and flagged a consequence: because every accepted tag exists in the catalog, a validated request can never return zero tracks, so the "no match" path is effectively unreachable. The owner kept the strict design.
- **Parsing with quoting disabled.** Inspecting the real data showed a stray `"` in one title would merge about 100 rows under default CSV parsing; the assistant chose to disable quote handling and added a test for it.
- **Reporting what the evidence cannot show.** When writing the evaluation, the assistant labeled the 100% offline figures as rule-conformance checks (the code is deterministic), and listed weaknesses (artist repetition, an ignored mood in "calm death metal") rather than hiding them.

**Corrected**

- **Default model choice.** The assistant picked `gemini-3.8-flash` from the SDK's documentation examples and a web search, while noting it could not verify availability without a key. The owner's live test returned a 504 while `gemini-3.5-flash-lite` succeeded; the owner directed the change, so the default became `gemini-3.5-flash-lite`, `candidate_count` and the explicit temperature were removed, and the timeout was raised to 60 seconds. Lesson: documentation examples are not evidence a model works for your request.
- **A wrong assumption in a test.** The assistant assumed "metalcore" was absent from the real vocabulary and wrote a test expecting rejection; the test failed because the catalog contains it (on one track). The test was changed to use a tag that really is absent, and the sparse tag became an evaluation scenario.
- **Test bugs the assistant made itself.** A fixture asked for more tracks than its own artist cap allowed; one test claimed to check a "no match" case that cannot occur under strict validation; a persistence test reused a fake from an earlier search and so asserted the wrong thing; some tests contained dead code. These were found by running and reading the tests, and rewritten.
- **A mislabeled guard in the evaluation.** The assistant's check that "Gemini must never be called" failed in an unexpected way, because the interpreter wraps any client exception as a service error. It was changed to count calls directly.
- **Evaluation wording after review.** The first write-up reported a mean artist diversity of 0.650 across ten result sets, one of which is a one-track list; after review, the document also states **0.611** across the nine full lists and explains the difference. A later read-only verification pass flagged the wording "implicit workout request" (the tester had written "workout") and a Q1 heading that could be confused with the earlier 2,500-track query; the owner asked for both to be corrected and added the original exports as evidence.

**Rejected or deferred**

- **Constraining tags with an enum in the response schema.** Considered as a way to reduce hallucinated tags, but not adopted because it could not be tested against the live API; listed as future work.
- **Diversifying results by artist.** The evaluation exposed the repetition problem, but changing the scoring was outside the approved scope, so it is documented as a limitation instead of being implemented.
- **Deleting the old 2,500-track file.** The assistant removed every code, test and document reference to it but left the file itself for the owner to decide; the owner then replaced it with the 5,000-track file in the expansion commit (it remains in git history).
- **Claiming more than was measured.** Claims the evidence cannot support (an accuracy or success rate for Gemini, the reason the rejected search failed, human ratings) were deliberately left out; those fields are marked "not captured" or left blank.

---

## What the AI did not do

- It made **no live Gemini calls**, held **no API key**, and never saw raw Gemini replies.
- It made **no commits or pushes**; the owner committed each stage.
- It did not run a browser session or listen to any track; no claim about how tracks sound is made anywhere.
- It did not supply any human rating, and no subjective ratings exist in the project.
- It did not use the older `vibematch-ai` project.

## How AI output was verified

- A preflight at the start of most stages (repository, branch, tree state, test count, V1 parity).
- The full test suite and a byte-for-byte comparison of V1's command-line output with `baseline_results.txt` after every stage (passing throughout).
- Reading real data and real library interfaces before writing code against them.
- Recomputing reported figures from the CSV files, and replaying the recorded live result lists through the real recommender to confirm they matched.
- Running checker tests against deliberately corrupted inputs to confirm they fail when they should.

## Limits of this log

It is a summary built from repository history and the session record, with no verbatim prompts and no record of the lost setup conversation. It documents Claude Code only; the owner's own work, other reviewers' identities and any other tools are not described here.
