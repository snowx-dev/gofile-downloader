#!/usr/bin/env bash
# Download files listed in a gofile_*_urls.json manifest (wget + session cookie).
#
# Usage:
#   export GOFILE_TOKEN='...'
#   ./gofile_download.sh manifest.json [output_dir]
#
# Env: GOFILE_WAIT (default 8), GOFILE_429_WAIT (default 120), GOFILE_MAX_429 (default 5)

set -euo pipefail

MANIFEST="${1:?manifest json path required}"
OUTDIR="${2:-.}"
WAIT="${GOFILE_WAIT:-8}"
WAIT_429="${GOFILE_429_WAIT:-120}"
MAX_429="${GOFILE_MAX_429:-5}"
TOKEN="${GOFILE_TOKEN:-}"

if [[ -z "$TOKEN" ]]; then
  echo "Set GOFILE_TOKEN (browser cookie: accountToken for the file host domain)" >&2
  exit 1
fi

if [[ ! -f "$MANIFEST" ]]; then
  echo "Manifest not found: $MANIFEST" >&2
  exit 1
fi

mkdir -p "$OUTDIR"

python3 - "$MANIFEST" "$OUTDIR" "$WAIT" "$WAIT_429" "$MAX_429" "$TOKEN" <<'PY'
import json
import subprocess
import sys
import time
from pathlib import Path

manifest, outdir, wait_s, wait_429_s, max_429_s, token = sys.argv[1:7]
wait = float(wait_s)
wait_429 = float(wait_429_s)
max_429 = int(max_429_s)
out = Path(outdir)
data = json.loads(Path(manifest).read_text())
files = data.get("files") or []
total = len(files)
ok = skip = fail = 0


def wget_file(url: str, dest: Path) -> tuple[bool, bool]:
    """Returns (success, was_429)."""
    cmd = [
        "wget",
        "-c",
        "--tries=1",
        "--waitretry=5",
        "--timeout=60",
        "--read-timeout=300",
        f"--header=Cookie: accountToken={token}",
        "-O",
        str(dest),
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    combined = (proc.stdout or "") + (proc.stderr or "")
    is_429 = "429" in combined or "Too Many Requests" in combined
    return proc.returncode == 0 and not is_429, is_429


for i, item in enumerate(files, 1):
    name = item["name"]
    url = item["url"]
    expected = int(item.get("size") or 0)
    dest = out / name

    if dest.exists() and expected and dest.stat().st_size == expected:
        print(f"[{i}/{total}] skip complete: {name}")
        skip += 1
        continue

    print(f"[{i}/{total}] downloading: {name}")
    success = False
    for attempt in range(1, max_429 + 2):
        success, got_429 = wget_file(url, dest)
        if success:
            break
        if got_429 and attempt <= max_429:
            print(f"  429 rate limited — sleeping {wait_429:.0f}s (retry {attempt}/{max_429})")
            time.sleep(wait_429)
            continue
        break

    if success:
        size = dest.stat().st_size if dest.exists() else 0
        if expected and size != expected:
            print(f"  WARN size mismatch: got {size}, expected {expected}")
        ok += 1
    else:
        print(f"  FAILED: {name}")
        fail += 1

    if i < total:
        print(f"  waiting {wait:.0f}s before next file ...")
        time.sleep(wait)

print(f"Done: {ok} downloaded, {skip} skipped, {fail} failed, {total} total")
sys.exit(1 if fail else 0)
PY
