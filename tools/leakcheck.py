#!/usr/bin/env python3
"""Проверка, что в публичную документацию не попали приватные данные.

Режимы:
    --staged   проверить файлы, добавленные в индекс (используется pre-commit-хуком)
    --all      проверить все отслеживаемые файлы (используется в CI)

Что проверяется:
  1. IPv4-адреса вне документационных диапазонов и списка разрешённых.
     Публичные адреса — ошибка, приватные (RFC 1918) — предупреждение.
  2. Строки из личного списка `.leakcheck` (домен, имя хостера, внешний IP).
     Этот файл не коммитится: он перечислен в .gitignore.

Коды возврата: 0 — чисто (возможны предупреждения), 1 — найдены утечки.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Документационные диапазоны (RFC 5737) и служебные адреса.
ALLOWED_PREFIXES = (
    "192.0.2.",       # TEST-NET-1
    "198.51.100.",    # TEST-NET-2
    "203.0.113.",     # TEST-NET-3
    "127.",           # loopback
    "0.0.0.0",
    "255.255.255.",
    "224.0.0.",
)

PRIVATE_PREFIXES = ("10.", "192.168.", "169.254.") + tuple(
    f"172.{octet}." for octet in range(16, 32)
)

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# Расширения, которые вообще не имеет смысла читать как текст.
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zst", ".gz", ".img"}


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout


def staged_files() -> list[str]:
    out = git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    return [line for line in out.splitlines() if line]


def tracked_files() -> list[str]:
    return [line for line in git("ls-files").splitlines() if line]


def file_text(path: str, staged: bool) -> str | None:
    if Path(path).suffix.lower() in BINARY_SUFFIXES:
        return None
    try:
        if staged:
            return git("show", f":{path}")
        return (REPO / path).read_text(encoding="utf-8")
    except (subprocess.CalledProcessError, UnicodeDecodeError, FileNotFoundError):
        return None


def load_allowed_ips() -> set[str]:
    path = REPO / "tools" / "allowed-ips.txt"
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def load_personal_patterns() -> list[re.Pattern[str]]:
    """Личный список запрещённых строк. Файл .leakcheck не коммитится."""
    path = REPO / ".leakcheck"
    if not path.exists():
        return []
    patterns = []
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(re.compile(line, re.IGNORECASE))
        except re.error as exc:
            print(f".leakcheck:{lineno}: некорректное регулярное выражение: {exc}")
    return patterns


def check(paths: list[str], staged: bool) -> int:
    allowed_ips = load_allowed_ips()
    personal = load_personal_patterns()
    errors = 0
    warnings = 0

    for path in paths:
        text = file_text(path, staged)
        if text is None:
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            for ip in IPV4_RE.findall(line):
                if ip in allowed_ips or ip.startswith(ALLOWED_PREFIXES):
                    continue
                if ip.startswith(PRIVATE_PREFIXES):
                    print(
                        f"ПРЕДУПРЕЖДЕНИЕ {path}:{lineno}: приватный адрес {ip} — "
                        f"лучше заменить на 192.0.2.x"
                    )
                    warnings += 1
                    continue
                print(
                    f"ОШИБКА {path}:{lineno}: публичный адрес {ip} — "
                    f"замени на документационный диапазон или добавь "
                    f"в tools/allowed-ips.txt"
                )
                errors += 1

            for pattern in personal:
                if pattern.search(line):
                    print(
                        f"ОШИБКА {path}:{lineno}: совпадение с личным списком "
                        f".leakcheck (шаблон: {pattern.pattern})"
                    )
                    errors += 1

    if not personal:
        print(
            "Заметка: файл .leakcheck не найден — проверка на домен, хостера "
            "и внешний IP не выполнялась (см. tools/README.md)."
        )

    print(f"Проверено файлов: {len(paths)}; ошибок: {errors}, предупреждений: {warnings}")
    return 1 if errors else 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--staged"
    if mode == "--staged":
        return check(staged_files(), staged=True)
    if mode == "--all":
        return check(tracked_files(), staged=False)
    print(f"Использование: {sys.argv[0]} [--staged|--all]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
