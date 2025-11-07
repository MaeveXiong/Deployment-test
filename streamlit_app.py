import os
import json
import time
import zipfile
import tempfile
from pathlib import Path

import streamlit as st
import pandas as pd
from openai import OpenAI
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import pgeocode

# ======================================================
# 🧩 Step 0: Environment Setup & Proxy Handling
# ======================================================

# Remove any auto-injected proxy settings (important for Streamlit Cloud)
for var in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
    os.environ.pop(var, None)

st.set_page_config(page_title="🏥 Senior Living Placement Assistant", layout="wide")

# ======================================================
# ⚙️ Step 1: Sidebar Configuration
# ======================================================

with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("OpenAI API Key", type="password", help="Enter your OpenAI API key")

    if api_key:
        st.success("✅ API key configured")

@st.cache_resource(show_spinner=False)
def get_openai_client(api_key: str):
    """Safely initializes and caches OpenAI client."""
    try:
        return OpenAI(api_key=api_key)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize OpenAI client: {e}")

client = get_openai_client(api_key) if api_key else None

# ======================================================
# 🗂 Step 2: State Initialization
# ======================================================
if "transcription" not in st.session_state:
    st.session_state.transcription = None
if "preferences" not in st.session_state:
    st.session_state.preferences = None
if "results" not in st.session_state:
    st.session_state.results = None

# ======================================================
# 🧭 Step 3: App Layout (Tabs)
# ======================================================
st.title("🏥 Senior Living Placement Assistant")
st.markdown("Upload audio and community data to get automated placement recommendations")

tab1, tab2, tab3, tab4 = st.tabs(["📤 Upload Files", "🎧 Transcription", "🔍 Filtering & Ranking", "📊 Results"])

# ======================================================
# 📤 Tab 1 — Upload Files
# ======================================================
with tab1:
    st.header("Step 1: Upload Files")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Audio File (.zip)")
        audio_file = st.file_uploader("Upload ZIP containing .m4a audio", type=["zip"])
    with col2:
        st.subheader("Community Data (.xlsx)")
        excel_file = st.file_uploader("Upload Excel file", type=["xlsx"])

    if audio_file and excel_file:
        st.success("✅ Files uploaded successfully")

# ======================================================
# 🎧 Tab 2 — Transcription & Preference Extraction
# ======================================================
with tab2:
    st.header("Step 2: Transcription & Preference Extraction")

    if not api_key:
        st.warning("⚠️ Please enter your OpenAI API key in the sidebar")
    elif not audio_file:
        st.warning("⚠️ Please upload an audio file first")
    else:
        if st.button("🎧 Transcribe Audio", type="primary"):
            try:
                with st.spinner("Processing audio and extracting transcript..."):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        zip_path = Path(tmpdir) / "audio.zip"
                        with open(zip_path, "wb") as f:
                            f.write(audio_file.getbuffer())
                        with zipfile.ZipFile(zip_path, "r") as zip_ref:
                            zip_ref.extractall(tmpdir)
                        audio_files = list(Path(tmpdir).glob("*.m4a"))
                        if not audio_files:
                            st.error("❌ No .m4a files found in the ZIP archive")
                            st.stop()

                        with open(audio_files[0], "rb") as audio:
                            transcript = client.audio.transcriptions.create(
                                model="whisper-1", file=audio
                            )
                        st.session_state.transcription = transcript.text

                st.success("✅ Transcription complete!")
                st.text_area("Transcribed Text", st.session_state.transcription, height=200)

                with st.spinner("Extracting structured client preferences..."):
                    system_prompt = """You are a placement assistant for senior living communities.
                    Translate the transcript into structured JSON with:
                    name_of_patient, age_of_patient, injury_or_reason, care_level, 
                    preferred_location, max_budget, enhanced, enriched, 
                    move_in_window, pet_friendly, primary_contact_information, 
                    tour_availability, mentally, other_keywords."""
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": st.session_state.transcription},
                        ],
                        temperature=0.3,
                    )
                    st.session_state.preferences = json.loads(
                        response.choices[0].message.content
                    )

                st.success("✅ Preferences extracted!")
                st.json(st.session_state.preferences)

            except Exception as e:
                st.error(f"❌ Error during transcription: {e}")

# ======================================================
# 🔍 Tab 3 — Community Filtering & Ranking
# ======================================================
with tab3:
    st.header("Step 3: Filter & Rank Communities")

    if not st.session_state.preferences:
        st.warning("⚠️ Please complete Step 2 first")
    elif not excel_file:
        st.warning("⚠️ Please upload Excel file first")
    else:
        if st.button("🔍 Process Communities", type="primary"):
            try:
                prefs = st.session_state.preferences
                df = pd.read_excel(excel_file, engine="openpyxl")
                st.write(f"📋 Loaded {len(df)} communities")

                # Care Level Filter
                care_level = prefs.get("care_level")
                if care_level:
                    mask = df["Type of Service"].str.contains(care_level, na=False, case=False)
                    df = df[mask]
                    st.write(f"✓ Filtered by care level: {len(df)} remaining")

                # Enhanced / Enriched filters
                for field in ["Enhanced", "Enriched"]:
                    pref = prefs.get(field.lower())
                    if pref == "Yes" and field in df.columns:
                        df = df[df[field].astype(str).str.lower() == "yes"]
                        st.write(f"✓ Filtered by {field.lower()}: {len(df)} remaining")

                # Budget filter
                if prefs.get("max_budget"):
                    df["Monthly Fee"] = pd.to_numeric(df["Monthly Fee"], errors="coerce")
                    df = df[df["Monthly Fee"] <= prefs["max_budget"]]
                    st.write(f"✓ Filtered by budget: {len(df)} remaining")

                # Add Priority Ranking
                df["Priority_Level"] = df.apply(
                    lambda r: 1
                    if str(r.get("Contract (w rate)?", "")).strip().lower() not in ["no", "nan", ""]
                    else 2 if str(r.get("Work with Placement?", "")).strip().lower() == "yes"
                    else 3,
                    axis=1,
                )

                # Geographic Ranking
                geolocator = Nominatim(user_agent="senior_living_matcher")
                client_locations = prefs.get("preferred_location", ["Rochester, NY"])
                client_coords = []
                for loc in client_locations:
                    geo = geolocator.geocode(loc)
                    if geo:
                        client_coords.append((geo.latitude, geo.longitude))
                        time.sleep(1)
                if not client_coords:
                    client_coords = [(43.1566, -77.6088)]  # Default: Rochester

                zip_col = next((c for c in df.columns if "zip" in c.lower()), None)
                if zip_col:
                    nomi = pgeocode.Nominatim("us")
                    df["Town"] = df[zip_col].apply(
                        lambda z: nomi.query_postal_code(str(z)).place_name if pd.notna(z) else None
                    )
                    df["State"] = df[zip_col].apply(
                        lambda z: nomi.query_postal_code(str(z)).state_code if pd.notna(z) else None
                    )

                st.session_state.results = df.sort_values(by="Priority_Level")
                st.success(f"✅ Process complete! {len(df)} communities ranked")

            except Exception as e:
                st.error(f"❌ Error: {e}")

# ======================================================
# 📊 Tab 4 — Results & Download
# ======================================================
with tab4:
    st.header("Step 4: Recommendations")

    if st.session_state.results is None:
        st.warning("⚠️ Please complete Step 3 first")
    else:
        df = st.session_state.results
        top5 = df.head(5)
        st.subheader("🏆 Top 5 Communities")

        for i, row in top5.iterrows():
            with st.expander(f"#{i+1} — {row.get('Community Name', 'Unknown')}"):
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**Type:** {row.get('Type of Service', 'N/A')}")
                    st.write(f"**Town:** {row.get('Town', 'N/A')}")
                    st.write(f"**Monthly Fee:** ${row.get('Monthly Fee', 'N/A')}")
                with col2:
                    st.metric("Priority Level", int(row["Priority_Level"]))

        st.download_button("📥 Download All Results (CSV)", df.to_csv(index=False), "all_results.csv", "text/csv")
