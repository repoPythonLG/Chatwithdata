#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "offline" / "bundle"
DEFAULT_REQUIREMENTS = ROOT / "offline" / "requirements-offline.txt"
DEFAULT_CHUNK_MB = 95
DEFAULT_TARGET_PLATFORM = "manylinux2014_x86_64"
DEFAULT_TARGET_PYTHON_VERSION = "310"
DEFAULT_TARGET_IMPLEMENTATION = "cp"
DEFAULT_TARGET_ABI = "cp310"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build an offline install bundle for Chat with Contracts. Run this on an "
            "internet-connected machine with the same OS/CPU family as the target."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--chunk-mb", type=int, default=DEFAULT_CHUNK_MB)
    parser.add_argument("--easyocr-languages", default="en")
    parser.add_argument("--target-platform", default=DEFAULT_TARGET_PLATFORM)
    parser.add_argument("--target-python-version", default=DEFAULT_TARGET_PYTHON_VERSION)
    parser.add_argument("--target-implementation", default=DEFAULT_TARGET_IMPLEMENTATION)
    parser.add_argument("--target-abi", default=DEFAULT_TARGET_ABI)
    parser.add_argument("--only-binary", default=":all:")
    parser.add_argument("--include-wheelhouse", action="store_true")
    parser.add_argument(
        "--skip-dependency-download",
        action="store_true",
        help="Deprecated alias; wheelhouse download is skipped unless --include-wheelhouse is set.",
    )
    parser.add_argument("--skip-frontend-build", action="store_true")
    parser.add_argument("--skip-model-download", action="store_true")
    parser.add_argument("--skip-docling-model-download", action="store_true")
    parser.add_argument("--skip-easyocr-model-download", action="store_true")
    parser.add_argument(
        "--preserve-output",
        action="store_true",
        help="Keep an existing payload directory and only refresh requested parts plus chunks.",
    )
    args = parser.parse_args()

    if args.chunk_mb <= 0 or args.chunk_mb > 99:
        raise SystemExit(
            "--chunk-mb must be between 1 and 99 so GitHub's 100MB limit is respected."
        )

    output_dir = args.output_dir.resolve()
    payload_dir = output_dir / "payload"
    chunks_dir = output_dir / "chunks"
    wheelhouse = payload_dir / "wheelhouse"
    models_dir = payload_dir / "models"
    frontend_dist_dir = payload_dir / "frontend" / "dist"
    docling_models = models_dir / "docling"
    easyocr_models = models_dir / "easyocr"
    archive_path = output_dir / "chat-with-contracts-offline.tar"
    manifest_path = output_dir / "manifest.json"

    if args.preserve_output:
        output_dir.mkdir(parents=True, exist_ok=True)
        archive_path.unlink(missing_ok=True)
        shutil.rmtree(chunks_dir, ignore_errors=True)
    else:
        _clean_output(output_dir)
    wheelhouse.mkdir(parents=True, exist_ok=True)
    docling_models.mkdir(parents=True, exist_ok=True)
    easyocr_models.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    requirements = args.requirements.resolve()
    shutil.copy2(requirements, payload_dir / "requirements-offline.txt")

    if args.include_wheelhouse and not args.skip_dependency_download:
        _download_python_wheels(
            python_executable=args.python,
            wheelhouse=wheelhouse,
            requirements=requirements,
            target_platform=args.target_platform,
            target_python_version=args.target_python_version,
            target_implementation=args.target_implementation,
            target_abi=args.target_abi,
            only_binary=args.only_binary,
        )

    download_venv = output_dir / ".build" / "download-venv"
    if not args.skip_model_download:
        _prepare_download_venv(download_venv, args.python)
        venv_python = _venv_python(download_venv)
        if not args.skip_docling_model_download:
            _download_docling_models(venv_python, docling_models)
        if not args.skip_easyocr_model_download:
            _download_easyocr_models(venv_python, easyocr_models, args.easyocr_languages)

    if not args.skip_frontend_build:
        _build_frontend(frontend_dist_dir)

    _write_env_example(payload_dir, args.easyocr_languages)
    _write_readme(payload_dir)
    _create_tar(payload_dir, archive_path)
    chunk_paths = _split_archive(archive_path, chunks_dir, args.chunk_mb * 1024 * 1024)
    manifest = _write_manifest(
        manifest_path=manifest_path,
        archive_path=archive_path,
        chunk_paths=chunk_paths,
        requirements=requirements,
        easyocr_languages=args.easyocr_languages,
        chunk_mb=args.chunk_mb,
        target_platform=args.target_platform,
        target_python_version=args.target_python_version,
        target_implementation=args.target_implementation,
        target_abi=args.target_abi,
    )

    print("Offline bundle created.")
    print(f"Manifest: {manifest_path}")
    print(f"Chunks: {chunks_dir}")
    print(f"Chunk count: {len(manifest['chunks'])}")
    print("Commit only manifest.json and chunks/*.part* if you want the bundle in GitHub.")
    return 0


def _clean_output(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def _download_python_wheels(
    *,
    python_executable: str,
    wheelhouse: Path,
    requirements: Path,
    target_platform: str,
    target_python_version: str,
    target_implementation: str,
    target_abi: str,
    only_binary: str,
) -> None:
    command = [
        python_executable,
        "-m",
        "pip",
        "download",
        "--dest",
        str(wheelhouse),
        "-r",
        str(requirements),
    ]
    if target_platform:
        command.extend(["--platform", target_platform])
    if target_python_version:
        command.extend(["--python-version", target_python_version])
    if target_implementation:
        command.extend(["--implementation", target_implementation])
    if target_abi:
        command.extend(["--abi", target_abi])
    if only_binary:
        command.extend(["--only-binary", only_binary])
    _run(command, cwd=ROOT)


def _prepare_download_venv(
    download_venv: Path,
    python_executable: str,
) -> None:
    if download_venv.exists():
        shutil.rmtree(download_venv)
    _run([python_executable, "-m", "venv", str(download_venv)])
    venv_python = _venv_python(download_venv)
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    _run(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--extra-index-url",
            "https://download.pytorch.org/whl/cpu",
            "torch==2.5.1+cpu",
            "torchvision==0.20.1+cpu",
            "docling>=2.40.0",
            "easyocr>=1.7.2",
        ]
    )
    print(f"Prepared model download environment with {python_executable}")


def _download_docling_models(venv_python: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    commands = [
        [
            str(_venv_bin(venv_python.parent.parent, "docling-tools")),
            "models",
            "download",
            "-o",
            str(target),
        ],
        [
            str(venv_python),
            "-m",
            "docling.tools.models",
            "download",
            "-o",
            str(target),
        ],
    ]
    errors: list[str] = []
    for command in commands:
        try:
            _run(command)
            return
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            errors.append(f"{' '.join(command)} -> {exc}")

    script = textwrap.dedent(
        f"""
        from pathlib import Path
        from docling.utils.model_downloader import download_models
        download_models(output_dir=Path({str(target)!r}))
        """
    )
    try:
        _run([str(venv_python), "-c", script])
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        errors.append(f"programmatic docling download -> {exc}")
        raise RuntimeError(
            "Docling model download failed. Try upgrading docling/docling-tools, "
            "or rerun with --skip-model-download for a wheel-only smoke test.\n"
            + "\n".join(errors)
        ) from exc


def _download_easyocr_models(venv_python: Path, target: Path, languages: str) -> None:
    target.mkdir(parents=True, exist_ok=True)
    langs = [item.strip() for item in languages.split(",") if item.strip()] or ["en"]
    script = textwrap.dedent(
        f"""
        import easyocr
        easyocr.Reader(
            {langs!r},
            gpu=False,
            model_storage_directory={str(target)!r},
            download_enabled=True,
        )
        """
    )
    _run([str(venv_python), "-c", script])


def _build_frontend(target: Path) -> None:
    frontend_dir = ROOT / "frontend"
    _run(["npm", "ci"], cwd=frontend_dir)
    env = os.environ.copy()
    env["VITE_API_BASE_URL"] = "/api"
    print("+ npm run build")
    subprocess.run(["npm", "run", "build"], cwd=frontend_dir, env=env, check=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(frontend_dir / "dist", target)


def _write_env_example(payload_dir: Path, easyocr_languages: str) -> None:
    (payload_dir / "offline.env.example").write_text(
        "\n".join(
            [
                "# Copy these values into backend/.env after offline installation.",
                "DOCLING_ARTIFACTS_PATH=.data/offline-assets/docling",
                "EASYOCR_MODEL_DIR=.data/offline-assets/easyocr",
                f"EASYOCR_LANGUAGES={easyocr_languages}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_readme(payload_dir: Path) -> None:
    (payload_dir / "README_OFFLINE_PAYLOAD.md").write_text(
        textwrap.dedent(
            """
            # Chat with Contracts Offline Payload

            This payload contains local Docling/EasyOCR model assets and the
            prebuilt React frontend under `frontend/dist`.
            When built with `--include-wheelhouse`, it also contains Python wheels.
            It is intended for installation by `scripts/install_offline_bundle.py`.

            Runtime extraction is configured to use local model folders only. EasyOCR is
            called with `download_enabled=False`, so missing OCR models fail visibly
            instead of trying the internet during a user chat.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _create_tar(payload_dir: Path, archive_path: Path) -> None:
    with tarfile.open(archive_path, "w") as archive:
        archive.add(payload_dir, arcname="payload")


def _split_archive(archive_path: Path, chunks_dir: Path, chunk_size: int) -> list[Path]:
    chunk_paths: list[Path] = []
    with archive_path.open("rb") as source:
        index = 1
        while True:
            data = source.read(chunk_size)
            if not data:
                break
            chunk_path = chunks_dir / f"{archive_path.name}.part{index:04d}"
            chunk_path.write_bytes(data)
            chunk_paths.append(chunk_path)
            index += 1
    return chunk_paths


def _write_manifest(
    *,
    manifest_path: Path,
    archive_path: Path,
    chunk_paths: list[Path],
    requirements: Path,
    easyocr_languages: str,
    chunk_mb: int,
    target_platform: str,
    target_python_version: str,
    target_implementation: str,
    target_abi: str,
) -> dict[str, object]:
    manifest = {
        "name": "chat-with-contracts-offline",
        "created_by": "scripts/build_offline_bundle.py",
        "format_version": 1,
        "archive_name": archive_path.name,
        "archive_size": archive_path.stat().st_size,
        "archive_sha256": _sha256_file(archive_path),
        "chunk_size_mb": chunk_mb,
        "requirements_file": str(requirements.relative_to(ROOT)),
        "easyocr_languages": easyocr_languages,
        "target_platform": target_platform,
        "target_python_version": target_python_version,
        "target_implementation": target_implementation,
        "target_abi": target_abi,
        "chunks": [
            {
                "name": chunk.name,
                "size": chunk.stat().st_size,
                "sha256": _sha256_file(chunk),
            }
            for chunk in chunk_paths
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


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


def _venv_bin(venv_path: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / f"{name}.exe"
    return venv_path / "bin" / name


def _run(command: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
