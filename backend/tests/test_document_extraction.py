from __future__ import annotations

import zipfile

from app.documents import extraction


def test_text_document_is_copied_for_qwen_context(tmp_path):
    source = tmp_path / "contract.txt"
    source.write_text("Contract CT-9001 requires 60 days notice.", encoding="utf-8")

    result = extraction.extract_document_text(source, tmp_path / "extracted", "doc-1")

    assert result.engine == "text-copy"
    assert result.text_path is not None
    assert result.text_path.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_docx_fallback_extracts_text_when_docling_is_unavailable(monkeypatch, tmp_path):
    def disabled_docling(*_args, **_kwargs):
        return extraction.ExtractionResult(text_path=None, engine="docling", error="disabled")

    monkeypatch.setattr(extraction, "_extract_with_docling", disabled_docling)
    source = tmp_path / "contract.docx"
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>Supplier must provide insurance.</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", xml)

    result = extraction.extract_document_text(source, tmp_path / "extracted", "doc-2")

    assert result.engine == "docx-fallback"
    assert result.text_path is not None
    assert "Supplier must provide insurance." in result.text_path.read_text(encoding="utf-8")


def test_supported_document_types_include_docling_and_easyocr_formats():
    assert ".pdf" in extraction.DOCLING_EXTENSIONS
    assert ".pptx" in extraction.DOCLING_EXTENSIONS
    assert ".png" in extraction.EASYOCR_EXTENSIONS
    assert ".tiff" in extraction.EASYOCR_EXTENSIONS
