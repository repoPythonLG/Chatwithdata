#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE_DIR = ROOT / "offline" / "bundle"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Install Chat with Contracts backend dependencies and models from an offline bundle."
        )
    )
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    parser.add_argument("--target-root", type=Path, default=ROOT)
    parser.add_argument("--skip-python-install", action="store_true")
    parser.add_argument("--keep-archive", action="store_true")
    args = parser.parse_args()

    bundle_dir = args.bundle_dir.resolve()
    target_root = args.target_root.resolve()
    manifest_path = bundle_dir / "manifest.json"
    chunks_dir = bundle_dir / "chunks"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="chat-contracts-offline-") as tmp:
        tmp_dir = Path(tmp)
        archive_path = tmp_dir / manifest["archive_name"]
        _reassemble_archive(manifest, chunks_dir, archive_path)
        _verify_sha256(archive_path, manifest["archive_sha256"])
        payload_extract_dir = tmp_dir / "extracted"
        with tarfile.open(archive_path, "r") as archive:
            _safe_extract(archive, payload_extract_dir)
        payload_dir = payload_extract_dir / "payload"
        if not payload_dir.exists():
            raise RuntimeError("Offline archive did not contain a payload directory.")

        _copy_model_assets(payload_dir, target_root)
        _write_env_settings(target_root, manifest.get("easyocr_languages") or "en")
        if not args.skip_python_install:
            _install_backend_python(payload_dir, target_root)

        if args.keep_archive:
            destination = bundle_dir / manifest["archive_name"]
            shutil.copy2(archive_path, destination)
            print(f"Kept verified archive at {destination}")

    print("Offline installation completed.")
    return 0


def _reassemble_archive(manifest: dict[str, object], chunks_dir: Path, archive_path: Path) -> None:
    with archive_path.open("wb") as output:
        for chunk in manifest["chunks"]:
            chunk_path = chunks_dir / chunk["name"]
            _verify_sha256(chunk_path, chunk["sha256"])
            with chunk_path.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)


def _copy_model_assets(payload_dir: Path, target_root: Path) -> None:
    model_root = payload_dir / "models"
    backend_assets = target_root / "backend" / ".data" / "offline-assets"
    for name in ("docling", "easyocr"):
        source = model_root / name
        destination = backend_assets / name
        destination.mkdir(parents=True, exist_ok=True)
        if source.exists():
            shutil.copytree(source, destination, dirs_exist_ok=True)


def _write_env_settings(target_root: Path, easyocr_languages: str) -> None:
    env_path = target_root / "backend" / ".env"
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updates = {
        "DOCLING_ARTIFACTS_PATH": ".data/offline-assets/docling",
        "EASYOCR_MODEL_DIR": ".data/offline-assets/easyocr",
        "EASYOCR_LANGUAGES": str(easyocr_languages),
    }
    written_keys: set[str] = set()
    new_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        key = (
            stripped.split("=", 1)[0]
            if "=" in stripped and not stripped.startswith("#")
            else None
        )
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            written_keys.add(key)
        else:
            new_lines.append(line)
    for key, value in updates.items():
        if key not in written_keys:
            new_lines.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")


def _install_backend_python(payload_dir: Path, target_root: Path) -> None:
    backend_dir = target_root / "backend"
    venv_dir = backend_dir / ".venv"
    if not _venv_python(venv_dir).exists():
        venv.EnvBuilder(with_pip=True).create(venv_dir)
    python = _venv_python(venv_dir)
    wheelhouse = payload_dir / "wheelhouse"
    requirements = payload_dir / "requirements-offline.txt"
    _run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "-r",
            str(requirements),
        ],
        cwd=backend_dir,
    )


def _safe_extract(archive: tarfile.TarFile, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    for member in archive.getmembers():
        member_path = (target_dir / member.name).resolve()
        if member_path != target_root and not str(member_path).startswith(
            f"{target_root}{os.sep}"
        ):
            raise RuntimeError(f"Unsafe path in offline archive: {member.name}")
    archive.extractall(target_dir)


def _verify_sha256(path: Path, expected: str) -> None:
    actual = _sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"SHA256 mismatch for {path}: expected {expected}, got {actual}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _venv_python(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
