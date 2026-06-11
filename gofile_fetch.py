#!/usr/bin/env python3
"""
Fetch a Gofile folder: Playwright session -> file list + cookie -> wget downloads.

Usage:
  python3 gofile_fetch.py "https://gofile.io/d/FOLDER_ID" -d ./output
  python3 gofile_fetch.py "https://gofile.io/d/FOLDER_ID" --list-only
  python3 gofile_fetch.py "https://gofile.io/d/FOLDER_ID" --limit 1 -d ./output
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

EXTRACT_JS = """
() => {
  const main = appdata?.fileManager?.mainContent;
  if (!main?.data?.children) {
    return { ok: false, error: 'file list not loaded' };
  }
  const files = [];
  for (const item of Object.values(main.data.children)) {
    if (item.type !== 'file') continue;
    let link = item.link;
    if (link === 'overloaded') link = item.directLink;
    if (!link) continue;
    files.push({ name: item.name, url: link, size: item.size || 0 });
  }
  return {
    ok: true,
    folder: main.data.name,
    metadata: main.metadata || null,
    files,
  };
}
"""


@dataclass
class RemoteFile:
    name: str
    url: str
    size: int


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch files from a Gofile folder")
    p.add_argument("url", help="https://gofile.io/d/...")
    p.add_argument("-d", "--dir", default=".", help="Output directory")
    p.add_argument("--list-only", action="store_true", help="List files, do not download")
    p.add_argument("--limit", type=int, help="Download at most N files")
    p.add_argument("--headed", action="store_true", help="Show browser window")
    p.add_argument("--browser", choices=["chromium", "firefox"], default="chromium")
    p.add_argument("--wait", type=int, default=60, help="Seconds to wait for file list")
    p.add_argument("--pause", type=float, default=8.0, help="Seconds between downloads")
    p.add_argument("--pause-429", type=float, default=120.0, help="Sleep after HTTP 429")
    p.add_argument("--max-429", type=int, default=5, help="429 retries per file")
    p.add_argument(
        "--save-manifest",
        metavar="PATH",
        help="Write manifest JSON (default: gofile_<id>.json in output dir)",
    )
    return p.parse_args()


def folder_id(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    if not path.startswith("/d/") or path.count("/") < 2:
        raise SystemExit(f"Invalid folder URL: {url}")
    return path.split("/")[-1]


def get_token(cookies: list[dict]) -> str:
    for c in cookies:
        if c.get("name") == "accountToken":
            return c["value"]
    raise SystemExit("No accountToken in browser session")


def scrape(url: str, headed: bool, browser_name: str, wait_s: int) -> tuple[str, list[RemoteFile], dict]:
    with sync_playwright() as p:
        launcher = p.chromium if browser_name == "chromium" else p.firefox
        browser = launcher.launch(headless=not headed)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        print(f"Loading {url} ...")
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_selector("#filemanager_itemslist [data-item-id]", timeout=wait_s * 1000)
        except Exception:
            shot = Path(f"gofile_error_{folder_id(url)}.png")
            page.screenshot(path=str(shot))
            browser.close()
            raise SystemExit(f"Timed out waiting for file list (screenshot: {shot})")

        page.wait_for_timeout(2000)
        result = page.evaluate(EXTRACT_JS)
        cookies = context.cookies()
        browser.close()

    if not result.get("ok"):
        raise SystemExit(f"Extract failed: {result.get('error')}")

    token = get_token(cookies)
    files = [RemoteFile(f["name"], f["url"], int(f.get("size") or 0)) for f in result["files"]]
    meta = {"folder": result.get("folder"), "metadata": result.get("metadata"), "files": result["files"]}
    return token, files, meta


def wget_file(url: str, dest: Path, token: str) -> tuple[bool, bool]:
    cmd = [
        "wget", "-c", "--tries=1", "--timeout=60", "--read-timeout=300",
        f"--header=Cookie: accountToken={token}",
        "-O", str(dest), url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    is_429 = "429" in out or "Too Many Requests" in out
    return proc.returncode == 0 and not is_429, is_429


def download_files(
    files: list[RemoteFile],
    outdir: Path,
    token: str,
    pause: float,
    pause_429: float,
    max_429: int,
) -> tuple[int, int, int]:
    outdir.mkdir(parents=True, exist_ok=True)
    total = len(files)
    ok = skip = fail = 0

    for i, item in enumerate(files, 1):
        dest = outdir / item.name
        if dest.exists() and item.size and dest.stat().st_size == item.size:
            print(f"[{i}/{total}] skip: {item.name}")
            skip += 1
            continue

        print(f"[{i}/{total}] {item.name}")
        success = False
        for attempt in range(1, max_429 + 2):
            success, got_429 = wget_file(item.url, dest, token)
            if success:
                break
            if got_429 and attempt <= max_429:
                print(f"  429 — sleep {pause_429:.0f}s ({attempt}/{max_429})")
                time.sleep(pause_429)
                continue
            break

        if success:
            size = dest.stat().st_size if dest.exists() else 0
            if item.size and size != item.size:
                print(f"  WARN size {size} != expected {item.size}")
            ok += 1
        else:
            print(f"  FAILED")
            fail += 1

        if i < total and pause > 0:
            time.sleep(pause)

    return ok, skip, fail


def main() -> int:
    args = parse_args()
    fid = folder_id(args.url)
    outdir = Path(args.dir).expanduser().resolve()

    token, files, meta = scrape(args.url, args.headed, args.browser, args.wait)
    total_bytes = sum(f.size for f in files)
    print(f"Folder {fid}: {len(files)} file(s), ~{total_bytes / (1024**3):.1f} GB, session ok")

    manifest_path = Path(args.save_manifest) if args.save_manifest else outdir / f"gofile_{fid}.json"
    if args.save_manifest or not args.list_only:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(f"Manifest: {manifest_path}")

    if args.list_only:
        for f in files:
            print(f"{f.size:>12}  {f.name}")
        return 0

    if args.limit:
        files = files[: args.limit]

    ok, skip, fail = download_files(
        files, outdir, token, args.pause, args.pause_429, args.max_429
    )
    print(f"Done: {ok} ok, {skip} skipped, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
