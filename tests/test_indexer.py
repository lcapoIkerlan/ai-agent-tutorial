import hashlib

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
