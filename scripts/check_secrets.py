import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".codex",
    ".github",  # workflow examples may contain token names but not values
    "__pycache__",
    "node_modules",
    "dist",
    ".venv",
    "instance",
    "uploads",
    "backups",
}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".zip", ".tar", ".sqlite", ".db", ".pyc"}

PATTERNS = [
    ("OpenAI/DeepSeek style API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    ("Private key", re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----")),
    ("JWT secret assignment", re.compile(r"JWT_SECRET\s*=\s*(?!replace-|test-secret|demo-secret)[A-Za-z0-9_./+=-]{24,}")),
]


def iter_files(root):
    tracked = tracked_files(root)
    if tracked:
        for relative in tracked:
            path = root / relative
            if path.exists() and path.is_file() and path.suffix.lower() not in SKIP_SUFFIXES:
                yield path
        return
    for current, dir_names, file_names in os.walk(root):
        dir_names[:] = [name for name in dir_names if name not in SKIP_DIRS]
        current_path = Path(current)
        for file_name in file_names:
            path = current_path / file_name
            if path.suffix.lower() in SKIP_SUFFIXES:
                continue
            yield path


def tracked_files(root):
    try:
        result = subprocess.run(["git", "ls-files"], cwd=root, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return []
    return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def scan_file(path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    findings = []
    for name, pattern in PATTERNS:
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            snippet = match.group(0)
            if "replace-" in snippet:
                continue
            findings.append((name, line_no, snippet[:12] + "***"))
    return findings


def main():
    parser = argparse.ArgumentParser(description="Scan repository files for accidentally committed secrets.")
    parser.add_argument("--root", default=str(ROOT), help="Repository root")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    all_findings = []
    for path in iter_files(root):
        for name, line_no, snippet in scan_file(path):
            all_findings.append((path.relative_to(root).as_posix(), line_no, name, snippet))

    if all_findings:
        print("Potential secrets found:")
        for file_name, line_no, name, snippet in all_findings:
            print(f"- {file_name}:{line_no} {name}: {snippet}")
        return 1

    print("No committed secrets detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
