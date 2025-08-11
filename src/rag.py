import os
import uuid
import hashlib
from typing import List, Dict, Any, Optional

from pypdf import PdfReader
from docx import Document

# chroma imports
import chromadb
from chromadb import PersistentClient
from chromadb.config import Settings
from chromadb.utils import embedding_functions

# --- Configuration (project-relative) ---
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data_sources")
CHROMA_DIR = os.path.join(BASE_DIR, "..", "chroma_db")
COLLECTION_NAME = "adgm_refs"

# Embedding model used for both ingestion and query
SENTENCE_MODEL_NAME = "paraphrase-MiniLM-L3-v2"

# --- Helpers ---
def file_checksum(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def read_pdf(path: str) -> List[Dict[str, Any]]:
    pages = []
    try:
        reader = PdfReader(path)
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append({"page": i, "text": text})
    except Exception as e:
        print(f"[RAG] read_pdf error for {path}: {e}")
    return pages

def read_docx(path: str) -> List[Dict[str, Any]]:
    try:
        doc = Document(path)
        # Break docx into paragraph-level pieces for better granularity
        chunks = []
        for i, p in enumerate(doc.paragraphs, start=1):
            t = (p.text or "").strip()
            if t:
                chunks.append({"page": 1, "text": t, "para_index": i})
        return chunks if chunks else []
    except Exception as e:
        print(f"[RAG] read_docx error for {path}: {e}")
        return []

def chunk_text_generator(text: str, chunk_size: int = 1200, overlap: int = 200):
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
        start = max(0, end - overlap)
        if start >= text_len:
            break

def clean_metadata(metadata: dict) -> dict:
    """Ensure metadata values are only bool, int, float, or str — no None."""
    clean = {}
    for k, v in metadata.items():
        if v is None:
            continue
        if isinstance(v, (bool, int, float, str)):
            clean[k] = v
        else:
            clean[k] = str(v)
    return clean

# --- Chroma helpers ---
def get_chroma_client() -> PersistentClient:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    # Use persistent client with duckdb+parquet
    client = PersistentClient(path=CHROMA_DIR)
    return client

def get_or_create_collection(client: PersistentClient):
    try:
        return client.get_collection(name=COLLECTION_NAME)
    except Exception:
        # create with sentence-transformer embedding function
        embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=SENTENCE_MODEL_NAME
        )
        return client.create_collection(name=COLLECTION_NAME, embedding_function=embedding_fn)

# --- Ingestion (idempotent by file hash) ---
def ingest_sources(data_dir: Optional[str] = None):
    data_dir = data_dir or DATA_DIR
    if not os.path.isdir(data_dir):
        print(f"[RAG] Data directory not found: {data_dir}")
        return

    client = get_chroma_client()
    collection = get_or_create_collection(client)

    # collect already ingested file_hashes
    try:
        existing = collection.get(include=["metadatas"])
    except Exception:
        existing = {}
    ingested_hashes = set()
    for meta in existing.get("metadatas", []):
        if meta and isinstance(meta, dict) and meta.get("file_hash"):
            ingested_hashes.add(meta["file_hash"])

    print(f"[RAG] Existing ingested files (by hash): {len(ingested_hashes)}")

    total_chunks = 0
    for fname in sorted(os.listdir(data_dir)):
        path = os.path.join(data_dir, fname)
        if not os.path.isfile(path):
            continue
        if not (fname.lower().endswith(".pdf") or fname.lower().endswith(".docx")):
            print(f"[RAG] Skipping unsupported file: {fname}")
            continue

        fhash = file_checksum(path)
        if fhash in ingested_hashes:
            print(f"[RAG] Skipping already ingested: {fname}")
            continue

        if fname.lower().endswith(".pdf"):
            pages = read_pdf(path)
        else:
            pages = read_docx(path)

        for page in pages:
            page_text = page.get("text", "") or ""
            max_seg = 6000
            segments = [page_text[i:i+max_seg] for i in range(0, len(page_text), max_seg)] if len(page_text) > max_seg else [page_text]
            for seg_idx, seg in enumerate(segments):
                for chunk_idx, chunk in enumerate(chunk_text_generator(seg)):
                    chunk_id = str(uuid.uuid4())
                    metadata = {
                        "source_file": fname,
                        "page": page.get("page", 1),
                        "para_index": page.get("para_index", None),
                        "segment_index": seg_idx,
                        "chunk_index": chunk_idx,
                        "char_count": len(chunk),
                        "file_hash": fhash
                    }
                    try:
                        collection.add(
                            ids=[chunk_id],
                            documents=[chunk],
                            metadatas=[clean_metadata(metadata)]  # ✅ Clean metadata before insert
                        )
                        total_chunks += 1
                    except Exception as e:
                        print(f"[RAG] Failed to add chunk for {fname}: {e}")

        print(f"[RAG] Ingested: {fname}")

    print(f"[RAG] Ingestion complete. Total chunks added: {total_chunks}")

# --- Retrieval (structured output) ---
def retrieve_relevant_sections(query_text: str,
                               n_results: int = 3,
                               return_raw: bool = False) -> List[Any]:
    """
    Retrieve relevant chunks from Chroma.
    - return_raw=True: returns list[str] (document texts)
    - return_raw=False: returns list[dict] with keys {text, meta, score}
    """
    try:
        client = get_chroma_client()
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception as e:
        print(f"[RAG] Chroma collection not available: {e}")
        return [] if return_raw else []

    try:
        results = collection.query(query_texts=[query_text], n_results=n_results, include=["documents", "metadatas", "distances"])
    except Exception as e:
        print(f"[RAG] Query error: {e}")
        return [] if return_raw else []

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if return_raw:
        return docs

    structured = []
    for d, m, dist in zip(docs, metas, dists):
        sim = None
        try:
            sim = max(0.0, min(1.0, 1.0 - float(dist)))
        except Exception:
            sim = None
        structured.append({
            "text": (d[:1000] + "...") if d and len(d) > 1000 else (d or ""),
            "meta": m or {},
            "score": round(sim, 4) if sim is not None else None
        })
    return structured

# --- CLI convenience ---
if __name__ == "__main__":
    print("[RAG] Running ingestion (if any new files present)...")
    ingest_sources()
    print("[RAG] Sample retrieval for 'ADGM jurisdiction requirement' ...")
    res = retrieve_relevant_sections("ADGM jurisdiction requirement", n_results=3)
    for i, item in enumerate(res, 1):
        print(f"Result {i}: score={item.get('score')} source={item.get('meta', {}).get('source_file')} text={item.get('text')[:120]}")
