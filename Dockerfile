FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HOME=/hf-cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    ANONYMIZED_TELEMETRY=False

WORKDIR /app

# 1) CPU-only torch first (PyTorch CPU index, much lighter than the CUDA build)
COPY requirements-api.txt .
RUN pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements-api.txt

# 2) code + data (explicit copy: only what the API uses; never .env)
COPY api.py .
COPY src/ src/
COPY data/index/ data/index/
COPY data/processed/chunks.json data/processed/chunks.json

# 3) non-root user; Chroma (SQLite) must be able to write in data/index
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /hf-cache/hub && chown -R app:app /app/data /hf-cache
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=240s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5).status==200 else 1)"

# REWRITE_CACHE and LLM_PROVIDER are set HERE (not with ENV) so --env-file cannot override them.
ENTRYPOINT ["env", "REWRITE_CACHE=0", "LLM_PROVIDER=anthropic", \
            "python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
