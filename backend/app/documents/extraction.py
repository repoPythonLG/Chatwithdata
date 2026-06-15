from __future__ import annotations

import importlib
import logging
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".csv", ".json", ".md", ".rtf", ".text", ".txt"}
DOCLING_EXTENSIONS = {".doc", ".docx", ".html", ".htm", ".pdf", ".pptx", ".xlsx", ".xlsm", ".xls"}
EASYOCR_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass
class ExtractionResult:
    text_path: Path | None
    engine: str
    error: str | None = None


def extract_document_text(path: Path, extract_dir: Path, document_id: str) -> ExtractionResult:
    """Extract searchable text for an uploaded document.

    Runtime behavior is intentionally offline-safe:
    - Docling/EasyOCR are loaded dynamically only when installed.
    - EasyOCR runs with download_enabled=False so runtime never tries the internet.
    - Lightweight fallbacks keep text/PDF/DOCX support working without optional engines.
    """

    settings = get_settings()
    extract_dir.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    if suffix in TEXT_EXTENSIONS:
        target = extract_dir / f"{document_id}.txt"
        shutil.copy2(path, target)
        return ExtractionResult(text_path=target, engine="text-copy")

    if suffix in DOCLING_EXTENSIONS:
        docling_result = _extract_with_docling(path, extract_dir, document_id, settings)
        if docling_result.text_path:
            return docling_result
        logger.info("Docling extraction unavailable for %s: %s", path.name, docling_result.error)

    if suffix in EASYOCR_EXTENSIONS:
        ocr_result = _extract_with_easyocr(path, extract_dir, document_id, settings)
        if ocr_result.text_path:
            return ocr_result
        logger.info("EasyOCR extraction unavailable for %s: %s", path.name, ocr_result.error)

    if suffix == ".docx":
        fallback = _extract_docx_text(path, extract_dir, document_id)
        if fallback.text_path:
            return fallback

    if suffix == ".pdf":
        fallback = _extract_pdf_text(path, extract_dir, document_id)
        if fallback.text_path:
            return fallback

    return ExtractionResult(text_path=None, engine="none", error="No extractor produced text.")


def _extract_with_docling(
    path: Path,
    extract_dir: Path,
    document_id: str,
    settings: Settings,
) -> ExtractionResult:
    try:
        if settings.docling_artifacts_path:
            os.environ.setdefault("DOCLING_ARTIFACTS_PATH", str(settings.docling_artifacts_path))
        converter = _build_docling_converter(settings)
        result = converter.convert(str(path))
        document = result.document
        if hasattr(document, "export_to_markdown"):
            text = document.export_to_markdown()
        elif hasattr(document, "export_to_text"):
            text = document.export_to_text()
        else:
            text = str(document)
    except Exception as exc:
        return ExtractionResult(text_path=None, engine="docling", error=str(exc))

    return _write_extracted_text(
        text=text,
        extract_dir=extract_dir,
        document_id=document_id,
        engine="docling",
    )


def _build_docling_converter(settings: Settings):
    module = importlib.import_module("docling.document_converter")
    document_converter = module.DocumentConverter

    artifacts_path = settings.docling_artifacts_path
    if not artifacts_path:
        return document_converter()

    try:
        base_models = importlib.import_module("docling.datamodel.base_models")
        pipeline_options_module = importlib.import_module("docling.datamodel.pipeline_options")
        converter_module = importlib.import_module("docling.document_converter")

        input_format = base_models.InputFormat
        pdf_pipeline_options = pipeline_options_module.PdfPipelineOptions
        pdf_format_option = converter_module.PdfFormatOption

        pipeline_options = pdf_pipeline_options()
        pipeline_options.artifacts_path = str(artifacts_path)
        return document_converter(
            format_options={
                input_format.PDF: pdf_format_option(pipeline_options=pipeline_options),
            }
        )
    except Exception:
        logger.warning("Could not configure Docling artifacts_path; using default converter.")
        return document_converter()


def _extract_with_easyocr(
    path: Path,
    extract_dir: Path,
    document_id: str,
    settings: Settings,
) -> ExtractionResult:
    try:
        easyocr = importlib.import_module("easyocr")
        model_dir = settings.easyocr_model_dir or (settings.offline_assets_dir / "easyocr")
        reader = easyocr.Reader(
            settings.easyocr_languages,
            gpu=False,
            model_storage_directory=str(model_dir),
            download_enabled=False,
        )
        parts = reader.readtext(str(path), detail=0, paragraph=True)
        text = "\n".join(str(part) for part in parts if str(part).strip())
    except Exception as exc:
        return ExtractionResult(text_path=None, engine="easyocr", error=str(exc))

    return _write_extracted_text(
        text=text,
        extract_dir=extract_dir,
        document_id=document_id,
        engine="easyocr",
    )


def _extract_docx_text(path: Path, extract_dir: Path, document_id: str) -> ExtractionResult:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        text = "\n".join(node.text for node in root.iter() if node.text and node.text.strip())
    except Exception as exc:
        return ExtractionResult(text_path=None, engine="docx-fallback", error=str(exc))

    return _write_extracted_text(
        text=text,
        extract_dir=extract_dir,
        document_id=document_id,
        engine="docx-fallback",
    )


def _extract_pdf_text(path: Path, extract_dir: Path, document_id: str) -> ExtractionResult:
    try:
        pypdf = importlib.import_module("pypdf")
        reader = pypdf.PdfReader(str(path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        return ExtractionResult(text_path=None, engine="pypdf-fallback", error=str(exc))

    return _write_extracted_text(
        text=text,
        extract_dir=extract_dir,
        document_id=document_id,
        engine="pypdf-fallback",
    )


def _write_extracted_text(
    *,
    text: str,
    extract_dir: Path,
    document_id: str,
    engine: str,
) -> ExtractionResult:
    if not text.strip():
        return ExtractionResult(text_path=None, engine=engine, error="No text extracted.")

    target = extract_dir / f"{document_id}.txt"
    target.write_text(text.strip() + "\n", encoding="utf-8")
    return ExtractionResult(text_path=target, engine=engine)
