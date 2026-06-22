FROM python:3.13-slim

WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

# Install deps first for layer caching. The deployed app only queries Postgres and
# the model gateway — it does NOT scrape, so no Playwright browser is downloaded.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + agent + tools + skills (skills are read at runtime from /app/skills).
COPY src/ ./src/
COPY tools/ ./tools/
COPY agent/ ./agent/
COPY skills/ ./skills/
COPY app/ ./app/

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
