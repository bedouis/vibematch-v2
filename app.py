"""VibeMatch 2.0 - Streamlit app.

Run:  .venv/bin/python -m streamlit run app.py

Gemini only translates the request into catalog genre/mood tags (configured
in src/intent.py via GEMINI_API_KEY / GEMINI_MODEL). Ranking is a fixed
rule-based score over those tags; no audio is analyzed.
"""

import re
from pathlib import Path

import streamlit as st

from src.intent import (
    MAX_QUERY_CHARS,
    GeminiServiceError,
    InvalidModelResponseError,
    InvalidQueryError,
    MissingApiKeyError,
    NoConfidentInterpretationError,
)
from src.pipeline import RecommendationError, RecommendationResult, run_pipeline
from src.v2_recommender import (
    GENRE_POINTS,
    MAX_SCORE,
    MOOD_POINTS,
    CatalogError,
    catalog_vocabulary,
    load_v2_catalog,
)

CATALOG_PATH = Path(__file__).resolve().parent / "data" / "jamendo_5000.csv"
TOP_K = 10
RESULT_KEY = "last_result"  # session_state: the last successful RecommendationResult
PLACEHOLDER = "Relaxing ambient music for reading"

# Fixed, user-safe messages. Exception text is never shown to the user.
ERROR_MESSAGES = {
    InvalidQueryError: f"Please describe what you want to hear, in up to {MAX_QUERY_CHARS} characters.",
    MissingApiKeyError: ("Gemini is not configured. Set the GEMINI_API_KEY environment variable "
                         "and restart the app to enable searching."),
    GeminiServiceError: "Gemini couldn't be reached or took too long to respond. Please try again in a moment.",
    InvalidModelResponseError: ("Gemini's answer couldn't be verified against our catalog, so it was "
                                "discarded. Try rephrasing your request."),
    NoConfidentInterpretationError: ("We couldn't match that to a genre or mood in our catalog. Try naming "
                                     "a genre (like ambient or rock) or a mood (like calm or happy)."),
    RecommendationError: "Something went wrong while ranking tracks. Please try again.",
}
GENERIC_ERROR = "Something unexpected went wrong. Please try again."


@st.cache_resource(show_spinner=False)
def load_catalog():
    """Load and validate the catalog once per server process."""
    catalog = load_v2_catalog(CATALOG_PATH)
    return catalog, catalog_vocabulary(catalog)


def error_message(exc: Exception) -> str:
    for error_type, message in ERROR_MESSAGES.items():
        if isinstance(exc, error_type):
            return message
    return GENERIC_ERROR


def md(text: str) -> str:
    """Escape Markdown so catalog text renders literally."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>~$:<&])", r"\\\1", text)


def tag_list(tags) -> str:
    return ", ".join(f"`{t}`" for t in tags) if tags else "_none_"


def render_intent(result: RecommendationResult) -> None:
    st.subheader("How Gemini interpreted your request")
    st.markdown(f"**Genres:** {tag_list(result.intent.genres)}  \n**Moods:** {tag_list(result.intent.moods)}")
    st.caption("Chosen by Gemini from your words, limited to tags that exist in our catalog.")


def render_recommendations(result: RecommendationResult) -> None:
    if not result.recommendations:
        st.info("No tracks in the catalog matched those preferences. Try a different description.")
        return
    st.subheader("Top matches")
    st.caption(
        f"Match score is a fixed rule, not an AI confidence: +{GENRE_POINTS} for a genre match and "
        f"+{MOOD_POINTS} for a mood match, out of {MAX_SCORE}. It is based on catalog tags only; "
        "no audio was analyzed."
    )
    for rank, rec in enumerate(result.recommendations, start=1):
        with st.container(border=True):
            left, right = st.columns([4, 1])
            with left:
                st.markdown(f"**{rank}. {md(rec.track.title)}**  \n{md(rec.track.artist)}")
            with right:
                st.markdown(f"**{rec.score}/{MAX_SCORE}**  \nmatch score")
            st.write(rec.explanation)
            st.markdown(
                f"Matched genres: {tag_list(rec.matched_genres)}  \n"
                f"Matched moods: {tag_list(rec.matched_moods)}"
            )
            st.link_button("Open on Jamendo", rec.track.track_url)


def main() -> None:
    st.set_page_config(page_title="VibeMatch 2.0", page_icon="🎵")
    st.title("VibeMatch 2.0")
    st.subheader("Discover music that matches your mood.")

    try:
        catalog, vocabulary = load_catalog()
    except (CatalogError, OSError):
        st.error("The music catalog could not be loaded, so searching is unavailable.")
        st.stop()

    with st.form("search_form"):
        query = st.text_input(
            "What do you want to hear?",
            placeholder=PLACEHOLDER,
            max_chars=MAX_QUERY_CHARS,
        )
        submitted = st.form_submit_button("Find my vibe", type="primary")

    if submitted:
        # A new submission always discards the previous result, so a failed or
        # empty search never leaves stale results looking like its own.
        st.session_state.pop(RESULT_KEY, None)
        if not query.strip():
            st.warning("Describe what you want to hear first, for example: " + PLACEHOLDER)
        else:
            try:
                with st.spinner("Gemini is interpreting your request..."):
                    result = run_pipeline(query, catalog, vocabulary, k=TOP_K)
            except Exception as exc:  # shown as a fixed message; details are never displayed
                st.error(error_message(exc))
            else:
                st.session_state[RESULT_KEY] = result  # only the immutable result is stored

    stored = st.session_state.get(RESULT_KEY)
    if stored is not None:
        render_intent(stored)
        render_recommendations(stored)

    st.divider()
    st.caption(
        f"Catalog: {len(catalog):,} tracks from the MTG-Jamendo Dataset (metadata licensed CC BY-NC-SA 4.0, "
        "for non-commercial research and academic use). Track links come from the dataset and may no "
        "longer be available."
    )


if __name__ == "__main__":
    main()
