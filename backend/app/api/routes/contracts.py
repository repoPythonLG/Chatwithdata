from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import admin_user, current_user
from app.core.config import get_settings
from app.core.security import safe_filename
from app.datasources.catalog import DataSourceCatalog
from app.datasources.excel_scanner import EXCEL_EXTENSIONS, read_excel_sheet
from app.datasources.normalize import dedupe_identifiers, normalize_identifier
from app.db.models import ContractDocument, DataSource, User
from app.db.session import get_session
from app.documents.extraction import (
    DOCLING_EXTENSIONS,
    EASYOCR_EXTENSIONS,
    TEXT_EXTENSIONS,
    extract_document_text,
)
from app.schemas.contracts import ContractDocumentOut, ContractWorkspaceOut
from app.schemas.datasource import DataSourceCreate

router = APIRouter(prefix="/contracts", tags=["contracts"])

CONTRACT_DB_ROLE = "contract_database"
CONTRACT_SOURCE_NAME = "Contract database"
DOCUMENT_EXTENSIONS = TEXT_EXTENSIONS | DOCLING_EXTENSIONS | EASYOCR_EXTENSIONS


@router.get("", response_model=ContractWorkspaceOut)
async def get_contract_workspace(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    return ContractWorkspaceOut(
        database=await _contract_database_source(session),
        documents=await _contract_documents(session, user.id),
    )


@router.post("/database/upload", response_model=ContractWorkspaceOut)
async def upload_contract_database(
    file: UploadFile = File(...),
    admin: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
):
    original_name = file.filename or "contract-register.xlsx"
    extension = Path(original_name).suffix.lower()
    if extension not in EXCEL_EXTENSIONS:
        supported = ", ".join(sorted(EXCEL_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Contract database upload must be an Excel workbook: {supported}",
        )

    settings = get_settings()
    upload_dir = settings.contracts_work_dir / "database_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = upload_dir / f"{uuid.uuid4().hex}_{safe_filename(original_name)}"
    db_path = settings.contracts_work_dir / "contract_database.sqlite"

    try:
        await _write_upload(file, workbook_path, max_bytes=250 * 1024 * 1024)
        await _remove_existing_contract_databases(session)
        await _excel_to_sqlite(workbook_path, db_path)

        source = await DataSourceCatalog(session).create_source(
            DataSourceCreate(
                name=CONTRACT_SOURCE_NAME,
                source_type="sqlite",
                path=str(db_path.resolve()),
            )
        )
        source.profile = {
            **(source.profile or {}),
            "role": CONTRACT_DB_ROLE,
            "original_workbook_name": original_name,
            "original_workbook_path": str(workbook_path.resolve()),
        }
        await session.commit()
        await DataSourceCatalog(session).rebuild_relationships()
        return ContractWorkspaceOut(
            database=source,
            documents=await _contract_documents(session, admin.id),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


@router.post("/documents/upload", response_model=list[ContractDocumentOut])
async def upload_contract_documents(
    files: list[UploadFile] = File(...),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    document_dir = settings.contracts_work_dir / "documents"
    document_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = settings.contracts_work_dir / "document_text"
    extract_dir.mkdir(parents=True, exist_ok=True)

    created: list[ContractDocument] = []
    for file in files:
        original_name = file.filename or "contract-document"
        extension = Path(original_name).suffix.lower()
        if extension not in DOCUMENT_EXTENSIONS:
            supported = ", ".join(sorted(DOCUMENT_EXTENSIONS))
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported contract document type. Supported extensions: {supported}",
            )

        document_id = str(uuid.uuid4())
        target = document_dir / f"{document_id}_{safe_filename(original_name)}"
        try:
            size_bytes = await _write_upload(file, target, max_bytes=100 * 1024 * 1024)
            extraction = extract_document_text(target, extract_dir, document_id)
            document = ContractDocument(
                id=document_id,
                user_id=user.id,
                name=Path(original_name).stem,
                filename=original_name,
                path=str(target.resolve()),
                extracted_text_path=(
                    str(extraction.text_path.resolve()) if extraction.text_path else None
                ),
                content_type=file.content_type,
                size_bytes=size_bytes,
            )
            session.add(document)
            created.append(document)
        finally:
            await file.close()

    await session.commit()
    for document in created:
        await session.refresh(document)
    return [ContractDocumentOut.model_validate(document) for document in created]


@router.delete("/documents", status_code=204)
async def clear_contract_documents(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    documents = await _contract_documents(session, user.id)
    for document in documents:
        _unlink_if_safe(document.path)
        if document.extracted_text_path:
            _unlink_if_safe(document.extracted_text_path)
    await session.execute(delete(ContractDocument).where(ContractDocument.user_id == user.id))
    await session.commit()


@router.delete("/documents/{document_id}", status_code=204)
async def delete_contract_document(
    document_id: str,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    document = await session.get(ContractDocument, document_id)
    if document is None or document.user_id != user.id:
        return
    _unlink_if_safe(document.path)
    if document.extracted_text_path:
        _unlink_if_safe(document.extracted_text_path)
    await session.delete(document)
    await session.commit()


async def _write_upload(file: UploadFile, destination: Path, max_bytes: int) -> int:
    bytes_written = 0
    with destination.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > max_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file is too large.")
            output.write(chunk)
    return bytes_written


async def _excel_to_sqlite(workbook_path: Path, db_path: Path) -> None:
    settings = get_settings()
    db_path.unlink(missing_ok=True)
    workbook = pd.ExcelFile(workbook_path)
    used_table_names: list[str] = []
    table_count = 0
    with sqlite3.connect(db_path) as conn:
        for sheet_name in workbook.sheet_names:
            df = read_excel_sheet(workbook_path, sheet_name, settings)
            if df.empty and not len(df.columns):
                continue
            table_name = _dedupe_table_name(
                normalize_identifier(sheet_name, fallback="sheet"),
                used_table_names,
            )
            used_table_names.append(table_name)
            df = _sqlite_safe_dataframe(df)
            df.columns = dedupe_identifiers(list(df.columns), fallback="column")
            df.to_sql(table_name, conn, index=False, if_exists="replace")
            table_count += 1
    if table_count == 0:
        db_path.unlink(missing_ok=True)
        raise ValueError("No readable worksheets were found in the uploaded workbook.")


def _sqlite_safe_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    safe_df = df.copy()
    for column in safe_df.columns:
        if pd.api.types.is_datetime64_any_dtype(safe_df[column]):
            safe_df[column] = safe_df[column].dt.strftime("%Y-%m-%d")
            continue
        safe_df[column] = safe_df[column].map(_sqlite_safe_value)
    return safe_df.astype(object).where(pd.notna(safe_df), None)


def _sqlite_safe_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


async def _remove_existing_contract_databases(session: AsyncSession) -> None:
    catalog = DataSourceCatalog(session)
    sources = list((await session.execute(select(DataSource))).scalars().all())
    for source in sources:
        profile = source.profile or {}
        if profile.get("role") != CONTRACT_DB_ROLE:
            continue
        source_path = source.path
        await catalog.delete_source(source.id)
        _unlink_if_safe(source_path)


async def _contract_database_source(session: AsyncSession) -> DataSource | None:
    sources = list(
        (
            await session.execute(
                select(DataSource).order_by(DataSource.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    for source in sources:
        if (source.profile or {}).get("role") == CONTRACT_DB_ROLE:
            return source
    return None


async def _contract_documents(session: AsyncSession, user_id: str) -> list[ContractDocument]:
    result = await session.execute(
        select(ContractDocument)
        .where(ContractDocument.user_id == user_id)
        .order_by(ContractDocument.created_at)
    )
    return list(result.scalars().all())


def _dedupe_table_name(table_name: str, used: list[str]) -> str:
    if table_name not in used:
        return table_name
    index = 2
    while f"{table_name}_{index}" in used:
        index += 1
    return f"{table_name}_{index}"


def _unlink_if_safe(path: str) -> None:
    try:
        resolved = Path(path).resolve()
        contracts_dir = get_settings().contracts_work_dir.resolve()
        if resolved == contracts_dir or contracts_dir not in resolved.parents:
            return
        resolved.unlink(missing_ok=True)
    except Exception:
        return
