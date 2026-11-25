import hashlib
from pathlib import Path

import pytest
from chromadb import EmbeddingFunction
from docx import Document
from pypdf import PdfWriter

from app.indexer import Chunk, Index, SyncReport, chunk_text, extract_text


class FakeEmbedding(EmbeddingFunction):
    """Deterministic hash-based vectors; no network."""

    def __init__(self):
        pass

    def __call__(self, input):
        return [[b / 255 for b in hashlib.sha256(t.encode()).digest()[:16]] for t in input]

    @staticmethod
    def name():
        return "fake-hash"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return FakeEmbedding()


@pytest.fixture
def docs(tmp_path):
    d = tmp_path / "documents"
    d.mkdir()
    return d


@pytest.fixture
def index(tmp_path):
    return Index(tmp_path / "data", embedding_function=FakeEmbedding())


def test_chunk_text_overlaps_and_covers():
    text = "".join(chr(97 + i % 26) for i in range(2000))
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)
    assert chunks[0][-100:] == chunks[1][:100]
    assert chunks[0] + "".join(c[100:] for c in chunks[1:]) == text


def test_chunk_text_blank():
    assert chunk_text("") == []
    assert chunk_text("  \n ") == []


def test_extract_text_md_txt(tmp_path):
    (tmp_path / "a.md").write_text("# Hola", encoding="utf-8")
    (tmp_path / "b.txt").write_text("plain", encoding="utf-8")
    assert extract_text(tmp_path / "a.md") == "# Hola"
    assert extract_text(tmp_path / "b.txt") == "plain"


def test_extract_text_docx(tmp_path):
    p = tmp_path / "x.docx"
    d = Document()
    d.add_paragraph("word content")
    d.save(p)
    assert "word content" in extract_text(p)


def test_sync_add_unchanged_update_remove(index, docs):
    (docs / "a.md").write_text("alpha text", encoding="utf-8")
    (docs / "b.txt").write_text("beta text", encoding="utf-8")
    r = index.sync(docs)
    assert isinstance(r, SyncReport)
    assert sorted(r.added) == ["a.md", "b.txt"]
    assert not (r.updated or r.removed or r.skipped)

    assert index.sync(docs) == SyncReport([], [], [], [])

    n = index.count()
    (docs / "a.md").write_text("alpha changed", encoding="utf-8")
    r = index.sync(docs)
    assert r.updated == ["a.md"] and not r.added
    assert index.count() == n

    (docs / "b.txt").rename(docs / "c.txt")
    r = index.sync(docs)
    assert r.removed == ["b.txt"] and r.added == ["c.txt"]
    assert {c.source for c in index.search("beta text", k=10)} == {"a.md", "c.txt"}


def test_removed_chunks_gone_from_search(index, docs):
    (docs / "a.md").write_text("alpha", encoding="utf-8")
    index.sync(docs)
    (docs / "a.md").unlink()
    assert index.sync(docs).removed == ["a.md"]
    assert index.search("alpha") == []
    assert index.count() == 0


def test_subfolder_source_and_search(index, docs):
    (docs / "sub").mkdir()
    (docs / "sub" / "a.md").write_text("nested", encoding="utf-8")
    assert index.sync(docs).added == ["sub/a.md"]
    hits = index.search("nested")
    assert hits and all(isinstance(h, Chunk) for h in hits)
    assert hits[0].source == "sub/a.md" and hits[0].text == "nested"


def test_ignored_and_skipped(index, docs):
    (docs / ".DS_Store").write_bytes(b"x")
    (docs / "~$x.docx").write_bytes(b"x")
    (docs / "img.png").write_bytes(b"x")
    (docs / "bad.pdf").write_bytes(b"not a pdf")
    blank = PdfWriter()
    blank.add_blank_page(100, 100)
    with open(docs / "blank.pdf", "wb") as f:
        blank.write(f)
    r = index.sync(docs)
    assert sorted(r.skipped) == ["bad.pdf", "blank.pdf"]
    assert not r.added


def test_empty_folder(index, docs):
    assert index.sync(docs) == SyncReport([], [], [], [])


def test_small_batch_size_stores_all_chunks(index, docs):
    index._max_batch = 3
    (docs / "big.txt").write_text("x" * 5000, encoding="utf-8")
    assert index.sync(docs).added == ["big.txt"]
    assert index.count() == len(chunk_text("x" * 5000))


def test_failed_update_keeps_previous_version(index, docs, monkeypatch):
    (docs / "a.txt").write_text("old content", encoding="utf-8")
    index.sync(docs)
    (docs / "a.txt").write_text("new content", encoding="utf-8")
    monkeypatch.setattr(index, "_add", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    assert index.sync(docs).skipped == ["a.txt"]
    assert index.search("old")[0].text == "old content"


def test_unreadable_file_is_skipped(index, docs, monkeypatch):
    (docs / "bad.txt").write_text("secret", encoding="utf-8")
    (docs / "ok.txt").write_text("fine", encoding="utf-8")
    real = Path.read_bytes

    def fake(self):
        if self.name == "bad.txt":
            raise PermissionError("denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", fake)
    r = index.sync(docs)
    assert r.skipped == ["bad.txt"] and r.added == ["ok.txt"]


def test_extract_text_docx_tables(tmp_path):
    p = tmp_path / "t.docx"
    d = Document()
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "cellA"
    t.rows[0].cells[1].text = "cellB"
    d.save(p)
    assert "cellA | cellB" in extract_text(p)


def test_nested_folders_indexed_hidden_ignored(docs, index):
    for rel in ["a/b/c/deep.txt", "con espacios/mi doc.md", ".git/x.txt", "a/.cache/y.txt"]:
        f = docs / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("contenido", encoding="utf-8")
    report = index.sync(docs)
    assert {"a/b/c/deep.txt", "con espacios/mi doc.md"} <= set(report.added)
    assert not any(".git" in s or ".cache" in s for s in report.added)
