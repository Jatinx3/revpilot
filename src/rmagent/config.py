import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
DATA_SITE_URL = os.environ.get(
    "DATA_SITE_URL", "https://otel-hackathon-data-site.vercel.app"
)
MODEL_ID = os.environ.get("MODEL_ID", "openrouter:google/gemini-2.5-flash")

# Supabase Auth (Project Settings -> API). Anon key is safe to expose to the browser.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
