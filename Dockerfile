FROM python:3.11-slim

# System tools the Python code calls: Tesseract + Hebrew data (OCR), Poppler (PDF -> image)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-heb poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
COPY tests/ tests/
COPY samples/ samples/
RUN pip install --no-cache-dir -e ".[dev]"

ENTRYPOINT ["attendance-report"]
