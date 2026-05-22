FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

COPY chroma_db/ ./chroma_db/
COPY chroma_docs/ ./chroma_docs/

ENV PYTHONPATH=/app
ENV ENVIRONMENT=production
ENV CHROMA_STORAGE_DIR=/app/chroma_db
ENV DOC_CHROMA_DIR=/app/chroma_docs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "src.api.handler:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
