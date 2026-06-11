from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*[\"']?([^\"'\s#]{12,})[\"']?"
        ),
    ),
)

ALLOWLIST_VALUE_PATTERNS = (
    re.compile(r"(?i)^(?:changeme|example|placeholder|dummy|test|local|none|null)$"),
    re.compile(r"(?i).*demo-token$"),
    re.compile(r"(?i).*_KEY$"),
    re.compile(r"(?i).*_TOKEN$"),
    re.compile(r"(?i).*_PASSWORD$"),
    re.compile(r"(?i)^reposcan_local$"),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    pattern: str
    excerpt: str


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tracked_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [repo_root / line.strip() for line in result.stdout.splitlines() if line.strip()]


def _is_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:4096]
    except OSError:
        return True
    return b"\0" in chunk


def _redact(value: str) -> str:
    stripped = value.strip()
    if len(stripped) <= 8:
        return "<redacted>"
    return f"{stripped[:4]}...{stripped[-4:]}"


def _allowed_value(value: str) -> bool:
    cleaned = value.strip().strip("\"'")
    if any(character in cleaned for character in ("(", ")", ",")):
        return True
    if cleaned.startswith(("self.", "config.", "deployment.", "args.", "os.")):
        return True
    return any(pattern.match(cleaned) for pattern in ALLOWLIST_VALUE_PATTERNS)


def scan_file(repo_root: Path, path: Path) -> list[Finding]:
    if not path.exists() or _is_binary(path):
        return []

    relative = path.relative_to(repo_root).as_posix()
    findings: list[Finding] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return findings

    for line_number, line in enumerate(lines, start=1):
        for pattern_name, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(1) if pattern_name == "assigned_secret" and match.groups() else match.group(0)
                if _allowed_value(value):
                    continue
                findings.append(
                    Finding(
                        path=relative,
                        line=line_number,
                        pattern=pattern_name,
                        excerpt=line.replace(value, _redact(value)).strip(),
                    )
                )
    return findings


def run_secret_scan(repo_root: Path) -> dict[str, object]:
    findings: list[Finding] = []
    for path in _tracked_files(repo_root):
        findings.extend(scan_file(repo_root, path))
    return {
        "generated_at_utc": _utcnow(),
        "repo_root": str(repo_root),
        "scanned_files": len(_tracked_files(repo_root)),
        "finding_count": len(findings),
        "passed": not findings,
        "findings": [finding.__dict__ for finding in findings],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan tracked RepoScan files for committed secrets.")
    parser.add_argument("--output-root", default="artifacts/ops", help="Directory for the secret scan artifact.")
    parser.add_argument("--run-id", default=None, help="Optional run id. Defaults to secret_scan_<UTC timestamp>.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    args = parse_args()
    report = run_secret_scan(repo_root)
    run_id = args.run_id or "secret_scan_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = repo_root / output_root
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "secret_scan.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Secret scan: {run_id}")
        print(f"Output: {report_path}")
        print(f"Scanned files: {report['scanned_files']}")
        print(f"Findings: {report['finding_count']}")
        print(f"Result: {'PASS' if report['passed'] else 'FAIL'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
