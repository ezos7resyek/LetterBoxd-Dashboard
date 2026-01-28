# app.py
import pandas as pd
import streamlit as st

from src.io import read_watched_csv
from src.config import TMDB_READ_TOKEN

from src.widgets.summary import render as render_summary
from src.widgets.directors_actors import render as render_directors_actors
from src.widgets.languages import render as render_languages
from src.widgets.country_map import render as render_country_map
from src.widgets.genres import render as render_genres


st.set_page_config(page_title="Letterboxd Dashboard", layout="wide")

# --- Letterboxd-ish base styling + minimal uploader ---
st.markdown(
    """
    <style>
    html, body, [data-testid="stApp"] {
        background: radial-gradient(
            1200px 600px at 20% -10%,
            #1f3d2b 0%,
            #14181c 45%,
            #14181c 100%
        );
        color: #e0e0e0;
        font-family: -apple-system, BlinkMacSystemFont,
                     "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    .block-container {
        padding-top: 1.0rem;
        padding-bottom: 2.5rem;
        max-width: 1600px;
    }

    h1, h2, h3 { color: #ffffff; font-weight: 600; letter-spacing: 0.2px; }
    .stCaption, .stMarkdown p { color: #9ab0a6; }
    hr { border-color: rgba(255,255,255,0.06); }

    header { visibility: hidden; }
    footer { visibility: hidden; }

    /* ---- Make file uploader compact + hide file name/size ---- */
    [data-testid="stFileUploader"] {
        max-width: 240px;
        margin-left: auto;
    }
    [data-testid="stFileUploader"] small {
        display: none !important; /* hides watched.csv + file size line */
    }
    [data-testid="stFileUploaderDropzoneInstructions"] {
        display: none !important; /* hides drag-drop helper text */
    }
    [data-testid="stFileUploaderDropzone"] {
        padding: 0.35rem 0.5rem !important;
        border-radius: 10px !important;
        border-color: rgba(255,255,255,0.10) !important;
        background: rgba(20,24,28,0.45) !important;
    }

    /* Make selectbox compact too */
    [data-testid="stSelectbox"] {
        max-width: 240px;
        margin-left: auto;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def apply_time_filter(df: pd.DataFrame, option: str) -> pd.DataFrame:
    """Filter df by Date for user-friendly time windows."""
    if "Date" not in df.columns:
        return df

    d = df.copy()
    d["Date"] = pd.to_datetime(d["Date"], errors="coerce")

    today = pd.Timestamp.today().normalize()

    if option == "All time":
        return d

    if option == "Last year":
        start = (today - pd.DateOffset(years=1)).normalize()
        return d[d["Date"] >= start]

    if option == "This Year":
        start = pd.Timestamp(year=today.year, month=1, day=1)
        return d[d["Date"] >= start]

    if option == "Last Month":
        start = (today - pd.DateOffset(months=1)).normalize()
        return d[d["Date"] >= start]

    if option == "Last Week":
        start = (today - pd.Timedelta(days=7)).normalize()
        return d[d["Date"] >= start]

    return d


# --- Header: logo (left) + time filter + uploader (right) ---
with st.container():
    left, right = st.columns([6, 2], vertical_alignment="center")

    with left:
        # Put your logo at: assets/letterboxd_logo.png
        st.image("assets/letterboxd_logo.png", width=140)

    with right:
        st.selectbox(
            "",
            ["All time", "Last year", "This Year", "Last Month", "Last Week"],
            index=0,
            key="time_filter",
            label_visibility="collapsed",
        )

        uploaded = st.file_uploader(
            label="",
            type=["csv"],
            label_visibility="collapsed",
        )

st.divider()

# --- Data load ---
if uploaded is None:
    st.info("Upload Watched.csv to continue.")
    st.stop()

try:
    df = read_watched_csv(uploaded)
except Exception as e:
    st.error("Could not read Watched.csv.")
    st.exception(e)
    st.stop()

# --- Apply global time filter ---
time_option = st.session_state.get("time_filter", "All time")
df_filtered = apply_time_filter(df, time_option)

# --- Widgets (use filtered df everywhere) ---
render_summary(df_filtered, TMDB_READ_TOKEN)
st.divider()
render_directors_actors(df_filtered, TMDB_READ_TOKEN)
st.divider()
render_languages(df_filtered, TMDB_READ_TOKEN)
st.divider()
render_country_map(df_filtered, TMDB_READ_TOKEN)
st.divider()
render_genres(df_filtered, TMDB_READ_TOKEN)
