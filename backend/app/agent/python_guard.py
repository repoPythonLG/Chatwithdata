from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class PythonValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PythonGuard:
    allowed_import_roots = {
        "datetime",
        "duckdb",
        "math",
        "numpy",
        "pandas",
        "plotly",
        "statistics",
    }
    blocked_import_roots = {
        "builtins",
        "ctypes",
        "glob",
        "importlib",
        "marshal",
        "multiprocessing",
        "os",
        "pathlib",
        "pickle",
        "requests",
        "shutil",
        "socket",
        "subprocess",
        "sys",
        "tempfile",
        "threading",
        "urllib",
    }
    blocked_calls = {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "input",
        "locals",
        "memoryview",
        "open",
        "setattr",
        "vars",
    }
    blocked_attributes = {
        "chmod",
        "chown",
        "connect",
        "delete",
        "exec",
        "execfile",
        "getenv",
        "kill",
        "mkdir",
        "open",
        "popen",
        "putenv",
        "remove",
        "rename",
        "replace",
        "rmdir",
        "rmtree",
        "send",
        "socket",
        "system",
        "unlink",
        "walk",
        "write",
    }

    def __init__(self, max_chars: int):
        self.max_chars = max_chars

    def validate(self, code: str) -> PythonValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if len(code) > self.max_chars:
            errors.append(f"Python code is too large ({len(code)} chars > {self.max_chars}).")
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return PythonValidationResult(False, [f"Python syntax error: {exc}"])

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module)
                for name in names:
                    root = name.split(".")[0]
                    if root in self.blocked_import_roots or root not in self.allowed_import_roots:
                        errors.append(f"Import is not allowed: {name}")
            if isinstance(node, ast.Call):
                call_name = self._call_name(node.func)
                if call_name in self.blocked_calls:
                    errors.append(f"Call is not allowed: {call_name}")
            if isinstance(node, ast.Attribute) and (
                node.attr.startswith("__") or node.attr in self.blocked_attributes
            ):
                errors.append(f"Attribute access is not allowed: {node.attr}")
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                errors.append(f"Dunder name access is not allowed: {node.id}")

        if "query(" not in code:
            warnings.append("Code should usually use the provided query(sql) function.")

        return PythonValidationResult(not errors, sorted(set(errors)), warnings)

    @staticmethod
    def _call_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""
