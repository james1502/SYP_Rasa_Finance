# index_docs.py
from pathlib import Path
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss
import pickle

# Config - edit as needed
TXT_PATH = "docs/my_doc.txt"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 200
EMBED_MODEL = "all-MiniLM-L6-v2"
INDEX_PATH = "faiss_index.idx"
CHUNKS_PATH = "chunks.pkl"

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == length:
            break
        start = end - overlap
    return chunks

def main():
    txt_file = Path(TXT_PATH)
    if not txt_file.exists():
        raise SystemExit(f"Input file not found: {TXT_PATH}")

    text = txt_file.read_text(encoding="utf-8")
    chunks = chunk_text(text)
    if not chunks:
        raise SystemExit("No chunks produced from document.")

    model = SentenceTransformer(EMBED_MODEL)
    embeddings = model.encode(chunks, show_progress_bar=True, convert_to_numpy=True)
    embeddings = embeddings.astype("float32")

    # Use cosine similarity via inner product after normalization
    faiss.normalize_L2(embeddings)
    d = embeddings.shape[1]
    index = faiss.IndexFlatIP(d)
    index.add(embeddings)

    faiss.write_index(index, INDEX_PATH)
    with open(CHUNKS_PATH, "wb") as f:
        pickle.dump(chunks, f)

    print(f"Saved {len(chunks)} chunks -> {CHUNKS_PATH}")
    print(f"FAISS index saved -> {INDEX_PATH}")

if __name__ == "__main__":
    main()