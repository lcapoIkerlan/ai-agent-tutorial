"""Document index: extracts text, chunks it and keeps a Chroma collection in sync with a folder."""

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

import chromadb
from chromadb import EmbeddingFunction
from docx import Document
from pypdf import PdfReader

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".md", ".txt"})


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if ext == ".docx":
        doc = Document(str(path))
        rows = [
            " | ".join(cell.text for cell in row.cells)
            for table in doc.tables
            for row in table.rows
        ]
        return "\n".join([p.text for p in doc.paragraphs] + rows)
    return path.read_text(encoding="utf-8", errors="replace")


def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    if not text.strip():
        return []
    step = size - overlap
    chunks = []
    for start in range(0, len(text), step):
        chunks.append(text[start : start + size])
        if start + size >= len(text):
            break
    return chunks


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str


@dataclass
class SyncReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


class Index:
    def __init__(self, data_dir: Path, embedding_function: EmbeddingFunction | None = None):
        client = chromadb.PersistentClient(path=str(Path(data_dir) / "chroma"))
        self._max_batch = client.get_max_batch_size()
        # Production passes None and uses Chroma's default model, which the Dockerfile
        # pre-warms at build time; tests inject a fake to avoid any download.
        kwargs = {"embedding_function": embedding_function} if embedding_function else {}
        self._col = client.get_or_create_collection("documents", **kwargs)

    def count(self) -> int:
        return self._col.count()

    def _stored_hashes(self) -> dict[str, str]:
        metas = self._col.get(include=["metadatas"])["metadatas"] or []
        return {m["source"]: m["sha256"] for m in metas}

    def _add(self, source: str, digest: str, chunks: list[str]) -> None:
        for i in range(0, len(chunks), self._max_batch):
            part = chunks[i : i + self._max_batch]
            self._col.add(
                ids=[f"{source}:{digest[:12]}:{i + j}" for j in range(len(part))],
                documents=part,
                metadatas=[{"source": source, "sha256": digest}] * len(part),
            )

    def sync(self, documents_dir: Path) -> SyncReport:
        report = SyncReport()
        stored = self._stored_hashes()
        seen: set[str] = set()

        for path in sorted(Path(documents_dir).rglob("*")):
            name = path.name
            if (
                not path.is_file()
                or name.startswith(("~$", "."))
                or path.suffix.lower() not in SUPPORTED_EXTENSIONS
            ):
                continue
            source = path.relative_to(documents_dir).as_posix()
            seen.add(source)
            digest = None
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if stored.get(source) == digest:
                    continue
                chunks = chunk_text(extract_text(path))
                if not chunks:
                    log.warning("Skipped %s: no text extracted", source)
                    self._col.delete(where={"source": source})
                    report.skipped.append(source)
                    continue
                self._add(source, digest, chunks)
            except Exception as exc:
                log.warning("Skipped %s: cannot index (%s)", source, exc)
                if digest:
                    try:  # drop partial new chunks; the previous version stays intact
                        self._col.delete(where={"$and": [{"source": source}, {"sha256": digest}]})
                    except Exception:
                        pass
                report.skipped.append(source)
                continue
            if source in stored:
                # old chunks are removed only after the new ones were added
                self._col.delete(where={"$and": [{"source": source}, {"sha256": {"$ne": digest}}]})
            (report.updated if source in stored else report.added).append(source)
            log.info("%s %s (%d chunks)", "Updated" if source in stored else "Added", source, len(chunks))

        for source in sorted(set(stored) - seen):
            self._col.delete(where={"source": source})
            report.removed.append(source)
            log.info("Removed %s", source)
        return report

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        n = self.count()
        if n == 0:
            return []
        res = self._col.query(query_texts=[query], n_results=min(k, n))
        return [Chunk(text=d, source=m["source"]) for d, m in zip(res["documents"][0], res["metadatas"][0])]
