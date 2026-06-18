#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request


METADATA_RE = re.compile(r"<!--\s*autoclick-job-metadata\s+(?P<payload>\{.*?\})\s*-->", re.IGNORECASE | re.DOTALL)
DATA_JOB_ID_RE = re.compile(r'data-autoclick-job-id="(?P<job_id>\d{15,})"', re.IGNORECASE)
FILENAME_JOB_ID_RE = re.compile(r"(?P<job_id>\d{15,})")
JOB_TITLE_RE = re.compile(r'<h3\b[^>]*data-test="job-title"[^>]*>(.*?)</h3>', re.IGNORECASE | re.DOTALL)
H1_RE = re.compile(r"<h1\b[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
ANCHOR_HREF_RE = re.compile(r'<a\b[^>]*href="(?P<href>[^"]*?/jobs/[^"]*?~\d+[^"]*)"', re.IGNORECASE)
POSTED_ON_RE = re.compile(r'data-test="posted-on"[^>]*>\s*(.*?)\s*</span>', re.IGNORECASE | re.DOTALL)
CLIENT_COUNTRY_RE = re.compile(r'<small\b[^>]*data-test="client-country"[^>]*>(.*?)</small>', re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
DATE_FOLDER_RE = re.compile(r"^\d{8}$")


def clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", TAG_RE.sub(" ", html.unescape(value or ""))).strip()


def normalize_url(value: str) -> str:
    url = html.unescape(value or "").strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://www.upwork.com" + url
    return url


def extract_metadata(document: str) -> dict[str, object]:
    match = METADATA_RE.search(document)
    if match is None:
        return {}
    try:
        payload = json.loads(html.unescape(match.group("payload")))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def extract_first(pattern: re.Pattern[str], document: str, group: str | int = 1) -> str:
    match = pattern.search(document)
    if match is None:
        return ""
    return clean_text(match.group(group))


def extract_job_payload(path: Path) -> dict[str, object]:
    document = path.read_text(encoding="utf-8", errors="replace")
    metadata = extract_metadata(document)

    job_id = str(metadata.get("job_id") or "")
    if not job_id:
        match = DATA_JOB_ID_RE.search(document) or FILENAME_JOB_ID_RE.search(path.stem)
        if match is not None:
            job_id = match.group("job_id")

    title = extract_first(JOB_TITLE_RE, document) or extract_first(H1_RE, document)
    url_match = ANCHOR_HREF_RE.search(document)
    job_url = normalize_url(url_match.group("href")) if url_match is not None else ""

    path_parts = path.parts
    source_date = ""
    source_bucket = ""
    source_relative_path = path.name
    for index, part in enumerate(path_parts):
        if DATE_FOLDER_RE.fullmatch(part):
            source_date = part
            source_bucket = path_parts[index + 1] if index + 1 < len(path_parts) - 1 else ""
            source_relative_path = str(Path(*path_parts[index:]))
            break

    return {
        "job_id": job_id,
        "job_file": path.name,
        "job_title": title,
        "job_url": job_url,
        "posted": extract_first(POSTED_ON_RE, document),
        "country": extract_first(CLIENT_COUNTRY_RE, document),
        "job_html": document,
        "source": "historical-import",
        "raw_payload": {
            "source_path": str(path),
            "source_relative_path": source_relative_path,
            "source_date": source_date,
            "source_bucket": source_bucket,
            "file_size": path.stat().st_size,
            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "metadata": metadata,
        },
    }


def post_json(url: str, payload: dict[str, object], timeout: float) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        response_body = response.read().decode("utf-8")
        return json.loads(response_body) if response_body else {}


def iter_html_files(paths: list[Path], pattern: str) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob(pattern))
        else:
            raise FileNotFoundError(path)
    return sorted({item.resolve() for item in files if item.suffix.lower() in {".html", ".htm"}})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import historical job HTML files into the classifier /jobs endpoint.")
    parser.add_argument("paths", nargs="+", type=Path, help="HTML file or directory to scan recursively.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8765/jobs", help="Classifier /jobs URL.")
    parser.add_argument("--pattern", default="*.html", help="Recursive glob pattern when a path is a directory.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum files to import; 0 means no limit.")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    files = iter_html_files(args.paths, args.pattern)
    if args.limit > 0:
        files = files[: args.limit]

    imported = 0
    failed = 0
    for index, path in enumerate(files, start=1):
        try:
            payload = extract_job_payload(path)
            if args.dry_run:
                print(f"[{index}/{len(files)}] dry-run {path} job_id={payload['job_id']!r} title={payload['job_title']!r}")
            else:
                result = post_json(args.endpoint, payload, args.timeout)
                print(f"[{index}/{len(files)}] imported {path} result={result}")
            imported += 1
        except (OSError, error.URLError, json.JSONDecodeError) as exc:
            failed += 1
            print(f"[{index}/{len(files)}] FAILED {path}: {exc}")

    print(json.dumps({"matched_files": len(files), "imported": imported, "failed": failed, "endpoint": args.endpoint}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
