FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 300 torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --timeout 300 -r requirements.txt
COPY app/ ./app/
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY tests/ ./tests/
COPY pytest.ini ./pytest.ini
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
