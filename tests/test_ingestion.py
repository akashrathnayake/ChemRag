import os
import tempfile

from rag.ingestion import compute_file_hash, SUPPORTED_EXTENSIONS


def test_supported_extensions_include_pdf_txt_md():
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".txt" in SUPPORTED_EXTENSIONS
    assert ".md" in SUPPORTED_EXTENSIONS


def test_same_content_produces_same_hash():
    with tempfile.TemporaryDirectory() as d:
        path1 = os.path.join(d, "a.txt")
        path2 = os.path.join(d, "b.txt")  # different filename, same content
        content = b"Bohr's model describes quantized electron energy levels."
        with open(path1, "wb") as f:
            f.write(content)
        with open(path2, "wb") as f:
            f.write(content)

        assert compute_file_hash(path1) == compute_file_hash(path2)


def test_different_content_produces_different_hash():
    with tempfile.TemporaryDirectory() as d:
        path1 = os.path.join(d, "a.txt")
        path2 = os.path.join(d, "b.txt")
        with open(path1, "wb") as f:
            f.write(b"Content A")
        with open(path2, "wb") as f:
            f.write(b"Content B")

        assert compute_file_hash(path1) != compute_file_hash(path2)
