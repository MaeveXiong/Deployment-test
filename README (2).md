# senior-living-placement-app
Senior Living Placement Assistant
An AI-powered application that helps match seniors with appropriate living communities based on audio intake interviews.
Features

🎧 Audio Transcription: Automatically transcribes client intake interviews using OpenAI Whisper

🤖 AI Preference Extraction: Uses GPT-4 to extract structured preferences from conversations

🔍 Smart Filtering: Filters communities based on care level, budget, waitlist, and amenities

📍 Geographic Ranking: Ranks by distance from preferred locations

💰 Priority System: Prioritizes revenue-generating partners

📊 Interactive Dashboard: Easy-to-use Streamlit interface



Enter your OpenAI API key in the sidebar when the app opens

Deployment to Streamlit Cloud
Step 1: Prepare Your Repository

Create a new GitHub repository
Add these files to your repo:

streamlit_app.py (main application)
requirements.txt (dependencies)
.gitignore (to exclude sensitive files)
README.md (this file)


IMPORTANT: Do NOT commit:

API keys
Data files (.xlsx, .csv)
Audio files



Step 2: Deploy on Streamlit Cloud

Go to share.streamlit.io
Sign in with your GitHub account
Click "New app"
Select your repository, branch (usually main), and main file (streamlit_app.py)
Click "Deploy"

Step 3: Configure Secrets (Optional)
If you want to pre-configure the API key:

In Streamlit Cloud, go to your app settings
Click on "Secrets"
Add your OpenAI API key:

tomlOPENAI_API_KEY = "sk-..."

Update streamlit_app.py to read from secrets:

python# In sidebar section, add:
try:
    api_key = st.secrets.get("OPENAI_API_KEY", "")
except:
    api_key = ""

if not api_key:
    api_key = st.text_input("OpenAI API Key", type="password")
Usage

Upload Files: Upload the ZIP file containing audio and the Excel file with community data
Transcribe: Click to transcribe the audio and extract preferences
Process: Filter and rank communities based on extracted preferences
Review: View top 5 recommendations with AI-generated explanations
Download: Export results as CSV

File Structure
project/
├── streamlit_app.py      # Main application
├── requirements.txt      # Python dependencies
├── .gitignore           # Git ignore rules
└── README.md            # Documentation
Data Requirements
Audio File

Must be in ZIP format containing .m4a file
Contains client intake interview

Community Excel File
Required columns:

CommunityID
Type of Service
Enhanced
Enriched
Est. Waitlist Length
Monthly Fee
Contract (w rate)?
Work with Placement?
ZIP or Postal Code
Geocode (optional)
Apartment Type

Security Notes

API keys are entered through the UI (not hardcoded)
No data files are committed to the repository
Use Streamlit secrets for production deployment
All processing happens in temporary directories

Troubleshooting
API Key Issues: Make sure your OpenAI API key has sufficient credits and access to Whisper and GPT-4 models.
File Upload Errors: Ensure files are in the correct format (.zip for audio, .xlsx for data).
Geocoding Errors: The app uses free geocoding services which may have rate limits. If you see errors, wait a moment and try again.
Distance Calculation Issues: Some communities may not have valid coordinates. These will be ranked lower.

License
[Your License Here]

Contributors
[Your Team Names]
