import streamlit as st
import zipfile
import json
import pandas as pd
import tempfile
from pathlib import Path
from openai import OpenAI
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import pgeocode
import time
import re

# Page config
st.set_page_config(page_title="Senior Living Placement Assistant", layout="wide")

# Title
st.title("🏥 Senior Living Placement Assistant")
st.markdown("Upload audio and data files to get personalized community recommendations")

# Initialize session state
if 'transcription' not in st.session_state:
    st.session_state.transcription = None
if 'preferences' not in st.session_state:
    st.session_state.preferences = None
if 'results' not in st.session_state:
    st.session_state.results = None

# Sidebar for API key
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("OpenAI API Key", type="password", help="Enter your OpenAI API key")
    
    if api_key:
        st.success("✅ API key configured")

# Main workflow
tab1, tab2, tab3, tab4 = st.tabs(["📤 Upload Files", "🎧 Transcription", "🔍 Filtering & Ranking", "📊 Results"])

with tab1:
    st.header("Step 1: Upload Files")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Audio File")
        audio_file = st.file_uploader("Upload ZIP with .m4a audio", type=['zip'])
        
    with col2:
        st.subheader("Community Data")
        excel_file = st.file_uploader("Upload community Excel file", type=['xlsx'])
    
    if audio_file and excel_file:
        st.success("✅ All files uploaded!")

with tab2:
    st.header("Step 2: Transcription & Preference Extraction")
    
    if not api_key:
        st.warning("⚠️ Please enter your OpenAI API key in the sidebar")
    elif not audio_file:
        st.warning("⚠️ Please upload audio file in Step 1")
    else:
        if st.button("🎧 Transcribe Audio", type="primary"):
            try:
                client = OpenAI(api_key=api_key)
                
                with st.spinner("Extracting and transcribing audio..."):
                    # Create temp directory
                    with tempfile.TemporaryDirectory() as tmpdir:
                        # Extract ZIP
                        zip_path = Path(tmpdir) / "audio.zip"
                        with open(zip_path, "wb") as f:
                            f.write(audio_file.getbuffer())
                        
                        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                            zip_ref.extractall(tmpdir)
                        
                        # Find audio file
                        audio_files = list(Path(tmpdir).glob("*.m4a"))
                        if not audio_files:
                            st.error("❌ No .m4a files found in ZIP")
                            st.stop()
                        
                        # Transcribe
                        with open(audio_files[0], "rb") as audio:
                            transcript = client.audio.transcriptions.create(
                                model="whisper-1",
                                file=audio
                            )
                        
                        st.session_state.transcription = transcript.text
                
                st.success("✅ Transcription complete!")
                st.text_area("Transcribed Text", st.session_state.transcription, height=200)
                
                # Extract preferences
                with st.spinner("Extracting structured preferences..."):
                    system_prompt = """You are a placement assistant for senior living communities. 
Translate the user's transcribed preferences into structured, filterable fields.
Return JSON with these fields:
- name_of_patient 
- age_of_patient: "blank years old" 
- injury_or_reason
- primary_contact_information 
- mentally: "very sharp", "not very sharp"
- care_level: one of ["Independent Living", "Assisted Living", "Memory Care"]
- preferred_location: list of "City, State" format (e.g., ["Webster, NY", "Penfield, NY"])
- enhanced: "Yes" or "No"
- enriched: "Yes" or "No"
- move_in_window: one of ["Immediate (0-1 months)", "Near-term (1-6 months)", "Flexible (6+ months)"]
- max_budget: integer (max monthly budget)
- pet_friendly: "Yes" or "No"
- tour_availability: when can family tour
- other_keywords: list of amenities/preferences"""
                    
                    response = client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Here is the transcribed text:\n\n{st.session_state.transcription}\n\nConvert to structured JSON."}
                        ],
                        temperature=0.3
                    )
                    
                    st.session_state.preferences = json.loads(response.choices[0].message.content)
                
                st.success("✅ Preferences extracted!")
                st.json(st.session_state.preferences)
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

with tab3:
    st.header("Step 3: Filter & Rank Communities")
    
    if not st.session_state.preferences:
        st.warning("⚠️ Please complete transcription in Step 2")
    elif not excel_file:
        st.warning("⚠️ Please upload Excel file in Step 1")
    else:
        if st.button("🔍 Process Communities", type="primary"):
            try:
                prefs = st.session_state.preferences
                df = pd.read_excel(excel_file, engine="openpyxl")
                
                st.write(f"📋 Loaded {len(df)} communities")
                
                # Filter by care level
                with st.spinner("Filtering by care level..."):
                    if prefs.get("care_level") != "Unknown":
                        mask = df["Type of Service"].str.contains(prefs["care_level"], na=False, case=False)
                        df = df[mask]
                        st.write(f"✓ After care level filter: {len(df)} communities")
                
                # Filter by enhanced
                if prefs.get("enhanced") == "Yes":
                    mask = df["Enhanced"].astype(str).str.lower() == "yes"
                    df = df[mask]
                    st.write(f"✓ After enhanced filter: {len(df)} communities")
                
                # Filter by enriched
                if prefs.get("enriched") == "Yes":
                    mask = df["Enriched"].astype(str).str.lower() == "yes"
                    df = df[mask]
                    st.write(f"✓ After enriched filter: {len(df)} communities")
                
                # Filter by move-in time
                move_in = prefs.get("move_in_window")
                if move_in == "Immediate (0-1 months)":
                    allowed = ["Available", "Unconfirmed"]
                elif move_in == "Near-term (1-6 months)":
                    allowed = ["Available", "Unconfirmed", "1-2 months", "2-4 months", "4-6 months"]
                else:
                    allowed = []
                
                if allowed:
                    mask = df["Est. Waitlist Length"].isin(allowed)
                    df = df[mask]
                    st.write(f"✓ After waitlist filter: {len(df)} communities")
                
                # Filter by budget
                if prefs.get("max_budget"):
                    df["Monthly Fee"] = pd.to_numeric(df["Monthly Fee"], errors="coerce")
                    mask = df["Monthly Fee"] <= prefs["max_budget"]
                    df = df[mask]
                    st.write(f"✓ After budget filter: {len(df)} communities")
                
                # Priority ranking
                with st.spinner("Assigning priority levels..."):
                    def assign_priority(row):
                        contract = str(row.get("Contract (w rate)?", "")).strip().lower()
                        placement = str(row.get("Work with Placement?", "")).strip().lower()
                        
                        if contract not in ["no", "nan", ""]:
                            return 1
                        elif contract == "no" and placement == "yes":
                            return 2
                        else:
                            return 3
                    
                    df["Priority_Level"] = df.apply(assign_priority, axis=1)
                    df = df.sort_values(by="Priority_Level", ascending=True)
                
                # Geographic ranking
                with st.spinner("Computing distances..."):
                    geolocator = Nominatim(user_agent="senior_living_matcher")
                    
                    # Get client locations
                    client_locations = prefs.get("preferred_location", ["Rochester, NY"])
                    if isinstance(client_locations, str):
                        client_locations = [client_locations]
                    
                    client_coords_list = []
                    for loc_text in client_locations:
                        try:
                            geo = geolocator.geocode(loc_text)
                            if geo:
                                client_coords_list.append((geo.latitude, geo.longitude))
                            time.sleep(1)
                        except:
                            pass
                    
                    if not client_coords_list:
                        client_coords_list = [(43.1566, -77.6088)]  # Rochester default
                    
                    # Find ZIP column
                    zip_col = None
                    for col in df.columns:
                        if "zip" in col.lower() or "postal" in col.lower():
                            zip_col = col
                            break
                    
                    if zip_col:
                        # Geocode communities
                        def geocode_community(row):
                            geo_val = row.get("Geocode")
                            if pd.notna(geo_val) and isinstance(geo_val, str) and "," in geo_val:
                                try:
                                    lat, lon = map(float, geo_val.split(","))
                                    return (lat, lon)
                                except:
                                    pass
                            
                            # Fallback to ZIP
                            zip_code = row.get(zip_col)
                            if pd.notna(zip_code):
                                try:
                                    query = f"{str(int(float(zip_code))).zfill(5)}, NY, USA"
                                    loc = geolocator.geocode(query)
                                    time.sleep(1)
                                    if loc:
                                        return (loc.latitude, loc.longitude)
                                except:
                                    pass
                            return None
                        
                        df["Community_Coords"] = df.apply(geocode_community, axis=1)
                        
                        # Calculate distances
                        def compute_distance(coords):
                            if coords is None:
                                return None
                            try:
                                distances = [geodesic(coords, c).miles for c in client_coords_list]
                                return min(distances)
                            except:
                                return None
                        
                        df["Distance_miles"] = df["Community_Coords"].apply(compute_distance)
                        
                        # Add Town/State
                        nomi = pgeocode.Nominatim('us')
                        df["Town"] = df[zip_col].apply(
                            lambda z: nomi.query_postal_code(str(int(float(z))).zfill(5)).place_name if pd.notna(z) else None
                        )
                        df["State"] = df[zip_col].apply(
                            lambda z: nomi.query_postal_code(str(int(float(z))).zfill(5)).state_code if pd.notna(z) else None
                        )
                        
                        # Sort by priority and distance
                        df = df.sort_values(by=["Priority_Level", "Distance_miles"], ascending=[True, True])
                
                st.session_state.results = df
                st.success(f"✅ Processing complete! {len(df)} communities ranked")
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

with tab4:
    st.header("Step 4: Top Recommendations")
    
    if st.session_state.results is None:
        st.warning("⚠️ Please complete processing in Step 3")
    else:
        df = st.session_state.results
        
        # Get top 5
        top5 = df.nsmallest(5, "Distance_miles") if "Distance_miles" in df.columns else df.head(5)
        
        st.subheader("🏆 Top 5 Communities")
        
        for idx, row in top5.iterrows():
            with st.expander(f"#{idx+1} - Community ID {row.get('CommunityID', 'N/A')}"):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"**Type:** {row.get('Type of Service', 'N/A')}")
                    st.write(f"**Location:** {row.get('Town', 'N/A')}, {row.get('State', 'N/A')}")
                    st.write(f"**Monthly Fee:** ${row.get('Monthly Fee', 'N/A')}")
                    if 'Distance_miles' in row and pd.notna(row['Distance_miles']):
                        st.write(f"**Distance:** {round(row['Distance_miles'], 1)} miles")
                
                with col2:
                    st.metric("Priority Level", int(row['Priority_Level']))
                    st.write(f"**Apartment Type:** {row.get('Apartment Type', 'N/A')}")
                
                # Generate AI explanation
                if api_key and st.session_state.preferences:
                    try:
                        client = OpenAI(api_key=api_key)
                        prompt = f"""Explain in 2-3 short sentences why this community matches the client's needs:
Client preferences: {json.dumps(st.session_state.preferences)}
Community: {row.get('Type of Service')} in {row.get('Town')}, ${row.get('Monthly Fee')}/month"""
                        
                        response = client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.4
                        )
                        st.info(f"**Why this matches:** {response.choices[0].message.content}")
                    except:
                        pass
        
        # Download options
        st.subheader("📥 Download Results")
        col1, col2 = st.columns(2)
        
        with col1:
            csv = top5.to_csv(index=False)
            st.download_button("Download Top 5 (CSV)", csv, "top5_recommendations.csv", "text/csv")
        
        with col2:
            full_csv = df.to_csv(index=False)
            st.download_button("Download All Results (CSV)", full_csv, "all_results.csv", "text/csv")
