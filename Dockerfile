# AML memory system — self-contained service image.
# Model weights are downloaded at build time; no binaries are committed to git.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_MODEL=BAAI/bge-small-en-v1.5 \
    HF_HOME=/opt/models \
    DB_PATH=/data/memory.db

WORKDIR /app

# onnxruntime (used by fastembed) needs libgomp.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Pre-download embedding weights so the image is self-contained and starts fast.
RUN python -c "import os; from fastembed import TextEmbedding; \
m = TextEmbedding(model_name=os.environ.get('EMBEDDING_MODEL', 'BAAI/bge-small-en-v1.5')); \
next(m.embed(['warmup']))"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
