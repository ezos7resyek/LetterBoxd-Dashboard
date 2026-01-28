import pandas as pd

EXPECTED_COLS = ["Date", "Name", "Year", "Letterboxd URI"]

def read_watched_csv(uploaded_file) -> pd.DataFrame:
    """
    Read and validate Letterboxd Watched.csv, return a cleaned DataFrame.
    Deduplicates films by 'Letterboxd URI' so rewatches don't over-count.
    """
    df = pd.read_csv(uploaded_file)
    df.columns = [c.strip() for c in df.columns]

    missing = [c for c in EXPECTED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}. Found: {list(df.columns)}")

    df["Name"] = df["Name"].astype(str).str.strip()
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")
    df["Letterboxd URI"] = df["Letterboxd URI"].astype(str).str.strip()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    df = df.drop_duplicates(subset=["Letterboxd URI"]).copy()
    return df
