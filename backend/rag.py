"""Local PDF retrieval only: no LLM calls or generated answers."""

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

import faiss
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
CACHE_DIR = PROJECT_ROOT / "backend" / "data" / "rag_index"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_WORDS = 100
OVERLAP_WORDS = 20


def split_text(text: str) -> list[str]:
    """Group sentences into small chunks, with a little overlapping context."""
    # Some PDF bullet fonts extract as the DEL control character.
    text = " ".join(text.replace("\x7f", "-").split())
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = []
    for sentence in sentences:
        words = sentence.split()
        # Split unusually long sentences too, so chunks stay small.
        while len(words) > CHUNK_WORDS:
            if current:
                chunks.append(" ".join(current))
                current = []
            chunks.append(" ".join(words[:CHUNK_WORDS]))
            words = words[CHUNK_WORDS - OVERLAP_WORDS:]
        if current and len(current) + len(words) > CHUNK_WORDS:
            chunks.append(" ".join(current))
            overlap = min(OVERLAP_WORDS, CHUNK_WORDS - len(words))
            current = current[-overlap:] if overlap else []
        current.extend(words)
    if current:
        chunks.append(" ".join(current))
    return chunks


def extract_chunks(pdf_paths: list[Path]) -> list[dict]:
    """Extract page text, keeping the PDF filename and page for each chunk."""
    chunks = []
    for path in pdf_paths:
        try:
            with path.open("rb") as file:
                reader = PdfReader(file)
                for page_number, page in enumerate(reader.pages, start=1):
                    text = page.extract_text() or ""
                    if not text.strip():
                        raise ValueError(
                            f"No extractable text in {path.name}, page {page_number}. "
                            "Scanned PDFs need OCR, which this demo does not include."
                        )
                    for chunk in split_text(text):
                        chunks.append({"text": chunk, "source": path.name, "page": page_number})
        except ValueError:
            raise
        except Exception:
            raise RuntimeError(f"Could not read PDF: {path.name}") from None
    if not chunks:
        raise ValueError("The PDFs contain no extractable text.")
    return chunks


@lru_cache(maxsize=1)
def get_model():
    """Load the CPU model once; downloaded weights stay in the project cache."""
    options = {
        "device": "cpu",
        "cache_folder": str(PROJECT_ROOT / ".cache" / "sentence_transformers"),
    }
    try:
        return SentenceTransformer(MODEL_NAME, local_files_only=True, **options)
    except OSError:
        # Only the first run needs the public model download.
        return SentenceTransformer(MODEL_NAME, **options)


@lru_cache(maxsize=1)
def load_index(fingerprint: str):
    """Reuse a matching local index, or rebuild it from the current PDFs."""
    index_path = CACHE_DIR / "index.faiss"
    metadata_path = CACHE_DIR / "chunks.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        index_bytes = index_path.read_bytes()
        if (metadata["fingerprint"] == fingerprint
                and metadata["index_sha256"] == hashlib.sha256(index_bytes).hexdigest()):
            index = faiss.read_index(str(index_path))
            chunks = metadata["chunks"]
            if index.ntotal == len(chunks) and chunks:
                return index, chunks
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        # Missing, incomplete, or stale cache: rebuild from the source PDFs.
        pass

    manifest = json.loads(fingerprint)
    chunks = extract_chunks([KNOWLEDGE_DIR / name for name in manifest["pdfs"]])
    embeddings = get_model().encode(
        [chunk["text"] for chunk in chunks],
        normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
    ).astype("float32")
    # Inner product of normalized vectors is cosine similarity.
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    metadata_path.write_text(json.dumps({
        "fingerprint": fingerprint,
        "index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
        "chunks": chunks,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return index, chunks


def retrieve_context(question: str, top_k: int = 3) -> list[dict]:
    """Return the closest PDF chunks, including source filenames and pages."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Provide a non-empty retrieval question.")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer.")
    pdf_paths = sorted(path for path in KNOWLEDGE_DIR.glob("*") if path.suffix.lower() == ".pdf")
    if not pdf_paths:
        raise FileNotFoundError(f"No PDFs found. Place your documents in {KNOWLEDGE_DIR}")
    fingerprint = json.dumps({
        "model": MODEL_NAME, "chunk_words": CHUNK_WORDS,
        "overlap_words": OVERLAP_WORDS, "format_version": 1,
        "pdfs": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in pdf_paths},
    }, sort_keys=True)
    index, chunks = load_index(fingerprint)
    question_embedding = get_model().encode(
        [question], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
    ).astype("float32")
    _, indices = index.search(question_embedding, min(top_k, len(chunks)))
    return [dict(chunks[int(position)]) for position in indices[0] if position >= 0]
