#!/usr/bin/env python3
"""Create or update the open GitHub issue for a failed nightly platform pulse."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def build_issue(log_text: str, pulse_date: str, ytdlp_version: str) -> tuple[str, str]:
    title = f"Platform nabzı başarısız: {pulse_date}"
    lines = log_text.splitlines()
    failures = [line for line in lines if re.search(r"\b(FAILED|ERROR)\b", line)]
    failed_tests = failures[-30:] or ["Pytest çıktısında başarısız test satırı bulunamadı."]
    log_summary = lines[-30:] or ["pytest günlük çıktısı boş."]
    body = "\n".join(
        [
            "## Başarısız testler",
            "```text",
            *failed_tests,
            "```",
            "",
            "## Log özeti",
            "```text",
            *log_summary,
            "```",
            "",
            f"**yt-dlp sürümü:** `{ytdlp_version}`",
        ]
    )
    return title, body


def gh(args: list[str]) -> str:
    result = subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-file", type=Path, default=Path("pulse.log"))
    parser.add_argument("--date", help="UTC issue date in YYYY-MM-DD format")
    parser.add_argument("--dry-run", action="store_true", help="print the issue without calling gh")
    args = parser.parse_args()

    log_text = args.log_file.read_text(encoding="utf-8", errors="replace") if args.log_file.exists() else ""
    try:
        import yt_dlp

        ytdlp_version = yt_dlp.version.__version__
    except (ImportError, AttributeError):
        ytdlp_version = "unavailable"
    pulse_date = args.date or dt.datetime.now(dt.timezone.utc).date().isoformat()
    title, body = build_issue(log_text, pulse_date, ytdlp_version)

    if args.dry_run:
        print(json.dumps({"title": title, "body": body}, ensure_ascii=True, indent=2))
        return 0

    repository = os.environ.get("GITHUB_REPOSITORY")
    if not repository:
        parser.error("GITHUB_REPOSITORY is required outside --dry-run")
    open_issues = json.loads(
        gh(["issue", "list", "--repo", repository, "--state", "open", "--limit", "1000", "--json", "number,title"])
    )
    existing = next((item for item in open_issues if item.get("title") == title), None)
    if existing:
        gh(["issue", "comment", str(existing["number"]), "--repo", repository, "--body", body])
        print(f"Updated issue #{existing['number']}: {title}")
    else:
        gh(["issue", "create", "--repo", repository, "--title", title, "--body", body])
        print(f"Created issue: {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
