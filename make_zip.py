"""Build the team distribution ZIP.

Copies the project into a temp staging dir, skipping the virtualenv, caches and
throwaway databases, then zips it. Kept as a script (not a shell one-liner)
because PowerShell's Compress-Archive has no exclude support.
"""
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "CV_Attendance_Team.zip"

SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".git", ".ruff_cache",
             ".mypy_cache", "certbot", "node_modules"}
SKIP_FILES = {"test_cv_attendance.db", "CV_Attendance_Team.zip",
              "make_zip.py", "test_output.txt", "_res.txt",
              ".env"}
SKIP_SUFFIX = {".pyc", ".pyo", ".log"}

files = []
for p in ROOT.rglob("*"):
    if not p.is_file():
        continue
    rel = p.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in rel.parts):
        continue
    if p.name in SKIP_FILES or p.suffix in SKIP_SUFFIX:
        continue
    files.append((p, rel))

if OUT.exists():
    OUT.unlink()

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for src, rel in files:
        z.write(src, Path("CV_Attendance") / rel)

total = sum(s.stat().st_size for s, _ in files)
print(f"files={len(files)}")
print(f"raw={total / 1024 / 1024:.2f} MB")
print(f"zip={OUT.stat().st_size / 1024 / 1024:.2f} MB")
print(f"path={OUT}")
