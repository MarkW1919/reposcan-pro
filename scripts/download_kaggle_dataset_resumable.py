"""Resumable Kaggle dataset zip downloader.

The Kaggle CLI's `datasets download` command does not retry on partial
IncompleteRead failures, which is a problem for the 12 GB VMMRdb dataset on
unreliable networks. This script uses HTTP Range requests with exponential
backoff to resume from the last received byte until the full zip is captured.

Authenticates with the credentials in ~/.kaggle/kaggle.json (HTTP Basic Auth).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request


KAGGLE_API_BASE = "https://www.kaggle.com/api/v1"
USER_AGENT = "RepoScanProKaggleDownloader/1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resumable Kaggle dataset downloader.")
    parser.add_argument("--dataset", required=True, help="owner/slug, e.g. prabashwara/vmmrdb-dataset")
    parser.add_argument("--output-path", required=True, help="Local zip path (will resume if partial)")
    parser.add_argument("--credentials", default=str(Path.home() / ".kaggle" / "kaggle.json"))
    parser.add_argument("--max-retries", type=int, default=20)
    parser.add_argument("--initial-backoff", type=float, default=4.0)
    parser.add_argument("--max-backoff", type=float, default=120.0)
    parser.add_argument("--chunk-size", type=int, default=1024 * 1024)
    return parser.parse_args()


def _load_credentials(path: Path) -> tuple[str, str]:
    payload: dict[str, Any] = json.loads(path.read_text())
    return payload["username"], payload["key"]


def _build_request(url: str, *, username: str, key: str, start_byte: int) -> urllib.request.Request:
    request = urllib.request.Request(url)
    request.add_header("User-Agent", USER_AGENT)
    auth = (
        f"{username}:{key}".encode("utf-8")
    )
    import base64
    encoded = base64.b64encode(auth).decode("ascii")
    request.add_header("Authorization", f"Basic {encoded}")
    if start_byte > 0:
        request.add_header("Range", f"bytes={start_byte}-")
    return request


def _read_total_size_from_headers(headers: Any, start_byte: int) -> int | None:
    content_range = headers.get("Content-Range")
    if content_range and "/" in content_range:
        total_part = content_range.rsplit("/", 1)[-1].strip()
        if total_part.isdigit():
            return int(total_part)
    content_length = headers.get("Content-Length")
    if content_length and content_length.isdigit():
        cl = int(content_length)
        return start_byte + cl
    return None


def main() -> int:
    args = parse_args()
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    username, key = _load_credentials(Path(args.credentials))

    download_url = f"{KAGGLE_API_BASE}/datasets/download/{args.dataset}"
    backoff = args.initial_backoff
    attempts = 0
    total_size: int | None = None

    while attempts < args.max_retries:
        start_byte = output_path.stat().st_size if output_path.exists() else 0
        if total_size is not None and start_byte >= total_size:
            print(f"OK: already complete ({start_byte} bytes)")
            return 0

        request = _build_request(
            download_url, username=username, key=key, start_byte=start_byte
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status_code = getattr(response, "status", response.getcode())
                if start_byte > 0 and status_code != 206:
                    print(
                        f"Server did not honor Range resume (HTTP {status_code}); restarting download",
                        file=sys.stderr,
                    )
                    output_path.unlink(missing_ok=True)
                    total_size = None
                    backoff = args.initial_backoff
                    continue

                if total_size is None:
                    total_size = _read_total_size_from_headers(response.headers, start_byte)
                    if total_size:
                        print(f"Total dataset size: {total_size / (1024**3):.2f} GiB")

                mode = "ab" if start_byte > 0 else "wb"
                bytes_this_session = 0
                last_print = time.time()
                with output_path.open(mode) as handle:
                    while True:
                        chunk = response.read(args.chunk_size)
                        if not chunk:
                            break
                        handle.write(chunk)
                        bytes_this_session += len(chunk)
                        now = time.time()
                        if now - last_print >= 5.0:
                            current = output_path.stat().st_size
                            if total_size:
                                pct = (current / total_size) * 100
                                print(
                                    f"  {current / (1024**3):.2f} / "
                                    f"{total_size / (1024**3):.2f} GiB ({pct:.1f}%)"
                                )
                            else:
                                print(f"  {current / (1024**3):.2f} GiB downloaded")
                            last_print = now

            current = output_path.stat().st_size
            if total_size is None or current >= total_size:
                print(f"OK: download complete ({current} bytes)")
                return 0
            print(
                f"Stream ended at {current} / {total_size} bytes — resuming",
                file=sys.stderr,
            )
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            current = output_path.stat().st_size if output_path.exists() else 0
            print(
                f"Network error after {current} bytes: {exc!r}; backing off {backoff}s",
                file=sys.stderr,
            )

        attempts += 1
        time.sleep(min(backoff, args.max_backoff))
        backoff = min(backoff * 1.5, args.max_backoff)

    print(f"FAILED: exhausted {args.max_retries} retries", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
