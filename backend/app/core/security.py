from __future__ import annotations

from pathlib import Path


class SecurityError(ValueError):
    """Raised when a path or operation violates local safety policy."""


def resolve_local_path(path: str | Path, allowed_roots: list[Path] | None = None) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise SecurityError(f"Path does not exist: {resolved}")
    if not resolved.is_file():
        raise SecurityError(f"Path must be a file: {resolved}")

    roots = [root.expanduser().resolve() for root in (allowed_roots or [])]
    if roots and not any(resolved == root or root in resolved.parents for root in roots):
        allowed = ", ".join(str(root) for root in roots)
        raise SecurityError(f"Path is outside allowed roots. Allowed roots: {allowed}")

    return resolved


def safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)
    return cleaned.strip("._") or "file"
