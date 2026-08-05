"""
Simple Mutation Testing for CV Attendance System.
Targets key logic files with operator replacements.
"""
import os
import sys
import subprocess
import tempfile
import re
from pathlib import Path


def mutate_source(source: str) -> list[tuple[str, str, str]]:
    """
    Return list of (mutant_name, description, mutated_source).
    Uses regex-based mutations for reliability.
    """
    mutants = []

    # 1. == → !=
    for m in re.finditer(r"(?<!\w)(\w+)\s*==\s*(\w+)", source):
        start, end = m.start(), m.end()
        mutated = source[:start] + f"{m.group(1)} != {m.group(2)}" + source[end:]
        mutants.append((f"eq_to_ne", f"Line ~{source[:start].count(chr(10))+1}", mutated))

    # 2. != → ==
    for m in re.finditer(r"(?<!\w)(\w+)\s*!=\s*(\w+)", source):
        start, end = m.start(), m.end()
        mutated = source[:start] + f"{m.group(1)} == {m.group(2)}" + source[end:]
        mutants.append((f"ne_to_eq", f"Line ~{source[:start].count(chr(10))+1}", mutated))

    # 3. and → or
    for m in re.finditer(r"(\w+)\s+and\s+(\w+)", source):
        start, end = m.start(), m.end()
        mutated = source[:start] + f"{m.group(1)} or {m.group(2)}" + source[end:]
        mutants.append((f"and_to_or", f"Line ~{source[:start].count(chr(10))+1}", mutated))

    # 4. or → and
    for m in re.finditer(r"(\w+)\s+or\s+(\w+)", source):
        start, end = m.start(), m.end()
        mutated = source[:start] + f"{m.group(1)} and {m.group(2)}" + source[end:]
        mutants.append((f"or_to_and", f"Line ~{source[:start].count(chr(10))+1}", mutated))

    # 5. >= → <
    for m in re.finditer(r"(?<!\w)(\w+)\s*>=\s*(\w+)", source):
        start, end = m.start(), m.end()
        mutated = source[:start] + f"{m.group(1)} < {m.group(2)}" + source[end:]
        mutants.append((f"gte_to_lt", f"Line ~{source[:start].count(chr(10))+1}", mutated))

    # 6. <= → >
    for m in re.finditer(r"(?<!\w)(\w+)\s*<=\s*(\w+)", source):
        start, end = m.start(), m.end()
        mutated = source[:start] + f"{m.group(1)} > {m.group(2)}" + source[end:]
        mutants.append((f"lte_to_gt", f"Line ~{source[:start].count(chr(10))+1}", mutated))

    # 7. if X → if True
    for m in re.finditer(r"if\s+(.+?)\s*:", source):
        expr = m.group(1).strip()
        if len(expr) > 3 and expr != "True":
            start, end = m.start(), m.end()
            mutated = source[:start] + f"if True:" + source[end:]
            mutants.append((f"if_true", f"Line ~{source[:start].count(chr(10))+1}", mutated))

    return mutants


def run_tests(test_files: list[str]) -> tuple[int, str]:
    """Run pytest and return (returncode, output)."""
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": "sqlite:///data/test_mutant.db",
        "CAMERA_ENABLED": "false",
        "CAMERA_INDEX": "-1",
        "METRICS_ENABLED": "false",
        "REDIS_URL": "redis://localhost:6379/1",
        "LOG_LEVEL": "ERROR",
    })
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *test_files, "-x", "--tb=line", "-q"],
        capture_output=True, text=True, timeout=30,
        env=env,
    )
    return result.returncode, result.stdout + result.stderr


def main():
    targets = {
        "attendance.py": ["tests/test_attendance.py"],
        "models/repository.py": ["tests/test_repository.py"],
        "auth.py": ["tests/test_auth.py"],
        "config.py": ["tests/test_config.py"],
    }

    total_mutants = 0
    killed = 0
    survived = 0
    errors = 0

    for target, test_files in targets.items():
        target_path = Path(target)
        if not target_path.exists():
            print(f"[SKIP] {target}: not found")
            continue

        source = target_path.read_text(encoding="utf-8")
        mutants = mutate_source(source)
        print(f"\n{'='*55}")
        print(f"  Target: {target} ({len(mutants)} mutants)")
        print(f"{'='*55}")

        total_mutants += len(mutants)

        for name, desc, mutant_source in mutants:
            # Write mutant to temp file
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", dir=str(target_path.parent),
                    delete=False, encoding="utf-8"
                ) as f:
                    mutant_path = f.name
                    f.write(mutant_source)
            except Exception as e:
                print(f"  [ERR] {name} {desc}: write failed - {e}")
                errors += 1
                continue

            try:
                # Swap files: atomic replace on Windows
                import os as _os
                backup = target_path.with_suffix(".py.bak")
                _os.replace(str(target_path), str(backup))
                _os.replace(str(mutant_path), str(target_path))

                # Run tests
                rc, output = run_tests(test_files)
                if rc == 0:
                    survived += 1
                    print(f"  [SURVIVED] {name} {desc}")
                else:
                    killed += 1
                    print(f"  [KILLED]   {name} {desc}")

            except subprocess.TimeoutExpired:
                errors += 1
                print(f"  [TIMEOUT]  {name} {desc}")
            except Exception as e:
                errors += 1
                print(f"  [ERROR]    {name} {desc}: {e}")
            finally:
                # Restore original
                if backup.exists() and target_path.exists():
                    _os.replace(str(backup), str(target_path))
                elif backup.exists():
                    _os.replace(str(backup), str(target_path))
                if Path(mutant_path).exists():
                    Path(mutant_path).unlink()

    print(f"\n{'='*55}")
    print(f"  FINAL RESULTS:")
    print(f"  Total mutants: {total_mutants}")
    print(f"  Killed:       {killed}")
    print(f"  Survived:     {survived}")
    print(f"  Errors:       {errors}")
    covered = total_mutants - errors
    if covered > 0:
        print(f"  Mutation Score: {killed / covered * 100:.1f}%")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
