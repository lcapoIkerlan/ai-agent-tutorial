FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Download the embedding model now so the first start needs no internet access.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as E; E()(['warm-up'])"
COPY app/ app/
CMD ["python", "-m", "app.main"]
