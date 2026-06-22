import pathlib
import sys

# Make repo root importable (src/, etl/, tools/) and load .env via src.rmagent.config.
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
