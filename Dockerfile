# Single image used by both the API and the UI services (see docker-compose.yml).
FROM python:3.11-slim

# Don't write .pyc files; flush logs immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better layer caching).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[ui]"

# App code (UI + scripts live outside the package).
COPY app ./app
COPY scripts ./scripts

# Default command runs the API; the UI service overrides this in compose.
EXPOSE 8000 8501
CMD ["uvicorn", "cloud_alliance_score.api:app", "--host", "0.0.0.0", "--port", "8000"]
