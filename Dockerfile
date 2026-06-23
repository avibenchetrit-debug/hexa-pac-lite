FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libffi-dev \
    libcairo2 \
    libfontconfig1 \
    libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright : installe le navigateur Chromium + ses dépendances système Debian.
# Placé après pip install (playwright doit être installé) et avant COPY . . (cache Docker).
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8080

# Shell form (no JSON array) so ${PORT} is expanded by /bin/sh at runtime.
# Railway injects $PORT; fall back to 8000 locally.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
