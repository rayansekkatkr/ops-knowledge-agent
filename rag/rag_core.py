"""Minimal, readable RAG pipeline: load -> chunk -> embed -> retrieve -> generate.

Two retrieval backends:
  - "embeddings": OpenAI or Azure OpenAI embeddings + cosine similarity (numpy)
  - "tfidf":      local TF-IDF (scikit-learn), no API key needed, works offline

Generation uses OpenAI or Azure OpenAI if configured; otherwise the pipeline
returns the retrieved passages only (extractive mode), so the demo never breaks.

Configuration (environment variables):
  OpenAI:        OPENAI_API_KEY, RAG_CHAT_MODEL (default gpt-4.1-mini),
                 RAG_EMBED_MODEL (default text-embedding-3-small)
  Azure OpenAI:  AZURE_OPENAI_ENDPOINT (https://<resource>.openai.azure.com),
                 AZURE_OPENAI_API_KEY, RAG_CHAT_MODEL and RAG_EMBED_MODEL
                 = your *deployment names*
  Force a backend: RAG_RETRIEVER=tfidf|embeddings
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = Path(os.environ.get("RAG_DOCS_DIR", ROOT / "data"))
INDEX_DIR = Path(os.environ.get("RAG_INDEX_DIR", ROOT / ".index"))

MAX_CHUNK_CHARS = 1200  # sections longer than this are split on paragraphs
OVERLAP_PARAGRAPHS = 1  # paragraphs repeated between consecutive pieces


# ---------------------------------------------------------------------------
# 1. Chunking
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    id: str
    source: str  # file name
    title: str  # document title (H1)
    section: str  # section heading (H2)
    text: str  # chunk body

    def for_embedding(self) -> str:
        # "Contextual chunk header": prefixing the title and section gives a short
        # section ("5. Rollback") enough context to be found by a vague question.
        return f"{self.title}\n{self.section}\n\n{self.text}"

    def citation(self) -> str:
        return f"{self.source} § {self.section}"


def _split_long(text: str) -> list[str]:
    """Split on blank lines, keeping tables and lists in one piece, with overlap."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces, current = [], []
    for p in paras:
        if current and len("\n\n".join(current + [p])) > MAX_CHUNK_CHARS:
            pieces.append("\n\n".join(current))
            current = current[-OVERLAP_PARAGRAPHS:] if OVERLAP_PARAGRAPHS else []
        current.append(p)
    if current:
        pieces.append("\n\n".join(current))
    return pieces


def chunk_markdown(path: Path) -> list[Chunk]:
    """One chunk per H2 section (structure-aware chunking), long sections split."""
    raw = path.read_text(encoding="utf-8")
    title_match = re.search(r"^# (.+)$", raw, flags=re.M)
    title = title_match.group(1).strip() if title_match else path.stem
    parts = re.split(r"^## (.+)$", raw, flags=re.M)
    # parts = [preamble, heading1, body1, heading2, body2, ...]
    chunks: list[Chunk] = []
    preamble = re.sub(r"^# .+$", "", parts[0], flags=re.M).strip()
    sections = [("Header", preamble)] if preamble else []
    sections += [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts), 2)]
    for s_idx, (heading, body) in enumerate(sections):
        for p_idx, piece in enumerate(_split_long(body)):
            chunks.append(
                Chunk(
                    id=f"{path.stem}:{s_idx}:{p_idx}",
                    source=path.name,
                    title=title,
                    section=heading,
                    text=piece,
                )
            )
    return chunks


def load_chunks(docs_dir: Path = DOCS_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(docs_dir.glob("*.md")):
        chunks.extend(chunk_markdown(path))
    if not chunks:
        raise FileNotFoundError(f"No .md documents found in {docs_dir}")
    return chunks


# ---------------------------------------------------------------------------
# 2. LLM / embeddings client (OpenAI or Azure OpenAI)
# ---------------------------------------------------------------------------

def llm_client():
    """Return an OpenAI-compatible client, or None if nothing is configured."""
    try:
        from openai import OpenAI
    except ImportError:
        return None
    if os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY"):
        # Azure OpenAI "v1" API: same client as OpenAI, model = deployment name.
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
        return OpenAI(base_url=f"{endpoint}/openai/v1/", api_key=os.environ["AZURE_OPENAI_API_KEY"])
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAI()
    return None


def provider_name() -> str:
    if os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY"):
        return "azure-openai"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "none"


CHAT_MODEL = os.environ.get("RAG_CHAT_MODEL", "gpt-4.1-mini")
EMBED_MODEL = os.environ.get("RAG_EMBED_MODEL", "text-embedding-3-small")


# ---------------------------------------------------------------------------
# 3. Index (build, persist, search)
# ---------------------------------------------------------------------------

@dataclass
class Hit:
    chunk: Chunk
    score: float


class Index:
    def __init__(self, chunks: list[Chunk], backend: str, vectors=None, vectorizer=None):
        self.chunks = chunks
        self.backend = backend
        self.vectors = vectors  # np.ndarray (embeddings) or sparse matrix (tfidf)
        self.vectorizer = vectorizer

    # -- build ---------------------------------------------------------------
    @classmethod
    def build(cls, chunks: list[Chunk], backend: str | None = None) -> "Index":
        backend = backend or os.environ.get("RAG_RETRIEVER") or (
            "embeddings" if llm_client() else "tfidf"
        )
        texts = [c.for_embedding() for c in chunks]
        if backend == "embeddings":
            vectors = _normalize(_embed(texts))
            return cls(chunks, backend, vectors=vectors)
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        vectors = vectorizer.fit_transform(texts)
        return cls(chunks, "tfidf", vectors=vectors, vectorizer=vectorizer)

    # -- persistence (embeddings only: they cost API calls, TF-IDF is instant) -
    def save(self, index_dir: Path = INDEX_DIR) -> None:
        if self.backend != "embeddings":
            return
        index_dir.mkdir(parents=True, exist_ok=True)
        np.save(index_dir / "vectors.npy", self.vectors)
        meta = {"embed_model": EMBED_MODEL, "chunks": [asdict(c) for c in self.chunks]}
        (index_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))

    @classmethod
    def load_or_build(cls, rebuild: bool = False) -> "Index":
        chunks = load_chunks()
        wanted = os.environ.get("RAG_RETRIEVER") or ("embeddings" if llm_client() else "tfidf")
        meta_path = INDEX_DIR / "meta.json"
        if wanted == "embeddings" and not rebuild and meta_path.exists():
            meta = json.loads(meta_path.read_text())
            cached = [Chunk(**c) for c in meta["chunks"]]
            # Rebuild automatically if the documents or the model changed.
            if meta.get("embed_model") == EMBED_MODEL and cached == chunks:
                return cls(cached, "embeddings", vectors=np.load(INDEX_DIR / "vectors.npy"))
        index = cls.build(chunks, wanted)
        index.save()
        return index

    # -- search --------------------------------------------------------------
    def search(self, query: str, k: int = 4) -> list[Hit]:
        if self.backend == "embeddings":
            q = _normalize(_embed([query]))[0]
            scores = self.vectors @ q
        else:
            q = self.vectorizer.transform([query])
            scores = (self.vectors @ q.T).toarray().ravel()
        top = np.argsort(-scores)[:k]
        return [Hit(self.chunks[i], float(scores[i])) for i in top]


def _embed(texts: list[str]) -> np.ndarray:
    client = llm_client()
    if client is None:
        raise RuntimeError("Embeddings backend needs OPENAI_API_KEY or AZURE_OPENAI_* variables")
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return np.array([d.embedding for d in resp.data], dtype=np.float32)


def _normalize(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=1, keepdims=True)


# ---------------------------------------------------------------------------
# 4. Generation (grounded answer with citations)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an internal assistant for Hanbit Logistics.
Answer ONLY from the context passages provided. Each passage starts with its source in brackets.
- Cite the source in brackets after each fact, e.g. [02-support-sla-policy.md § 3. Service level objectives].
- If the answer is not in the context, say you don't know and suggest who to contact. Never invent numbers.
- Answer in the same language as the question. Be concise."""

MIN_SCORE = {"tfidf": 0.05, "embeddings": 0.25}  # below this, we consider nothing relevant


def build_context(hits: list[Hit]) -> str:
    return "\n\n---\n\n".join(f"[{h.chunk.citation()}]\n{h.chunk.text}" for h in hits)


def answer(question: str, index: Index, k: int = 4) -> dict:
    hits = index.search(question, k=k)
    relevant = [h for h in hits if h.score >= MIN_SCORE[index.backend]]
    result = {
        "question": question,
        "retriever": index.backend,
        "sources": [{"citation": h.chunk.citation(), "score": round(h.score, 3)} for h in hits],
    }
    if not relevant:
        result["answer"] = "I couldn't find this in the documents."
        result["mode"] = "no-context"
        return result

    client = llm_client()
    if client is None:
        # Extractive fallback: show the best passage, still grounded and cited.
        best = relevant[0].chunk
        result["answer"] = f"(no LLM configured, best passage)\n[{best.citation()}]\n{best.text}"
        result["mode"] = "extractive"
        return result

    completion = client.chat.completions.create(
        model=CHAT_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n\n{build_context(relevant)}\n\nQuestion: {question}"},
        ],
    )
    result["answer"] = completion.choices[0].message.content
    result["mode"] = f"generative ({provider_name()}, {CHAT_MODEL})"
    return result
