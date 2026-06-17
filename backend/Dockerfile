FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        curl \
        tesseract-ocr \
        ocrmypdf \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
# The 'pdf' extra pulls in Docling (+ ML models) for PDF/OCR ingestion. It
# meaningfully increases image size and downloads models on first use. Drop it
# from this line if you only ingest CSV/structured exports.
RUN pip install --no-cache-dir -e ".[dev,pdf]"

COPY . .

EXPOSE 8000
