#!/usr/bin/env python3
"""
Export direct download URLs from a Gofile folder page via Playwright.

Usage:
  python3 gofile_export_links.py "https://gofile.io/d/FOLDER_ID"
  python3 gofile_export_links.py "https://gofile.io/d/FOLDER_ID" -o urls.txt --headed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

EXTRACT_JS = """
() => {
  const main = appdata?.fileManager?.mainContent;
  if (!main?.data?.children) {
    return { ok: false, error: 'appdata not ready — wait for the file list to load' };
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

INJECT_JS = """
(data) => {
  const boxId = 'dta-gofile-links';
  let box = document.getElementById(boxId);
  if (!box) {
    box = document.createElement('div');
    box.id = boxId;
    box.style.cssText = 'padding:12px;margin:8px 0;background:#1f2937;border:2px solid #3b82f6;';
    (document.querySelector('#filemanager_itemslist') || document.body).prepend(box);
  }
  box.innerHTML = '<b style="color:#93c5fd">DownThemAll links (' + data.files.length + ')</b><br>';
  for (const f of data.files) {
    const a = document.createElement('a');
    a.href = f.url;
    a.textContent = f.name;
    a.download = f.name;
    a.style.display = 'block';
    a.style.color = '#dbeafe';
    box.appendChild(a);
  }
  return data.files.length;
}
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export Gofile download URLs via Playwright")
    p.add_argument("url", help="https://gofile.io/d/...")
    p.add_argument("-o", "--output", help="Output .txt (default: gofile_<id>_urls.txt)")
    p.add_argument("--headed", action="store_true", help="Show browser window")
    p.add_argument("--browser", choices=["chromium", "firefox"], default="chromium")
    p.add_argument(
        "--inject",
        action="store_true",
        help="Inject <a href> links into page (for DownThemAll in that window)",
    )
    p.add_argument("--wait", type=int, default=60, help="Seconds to wait for file list")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    folder_id = args.url.rstrip("/").split("/")[-1]
    out = Path(args.output or f"gofile_{folder_id}_urls.txt")

    with sync_playwright() as p:
        launcher = p.chromium if args.browser == "chromium" else p.firefox
        browser = launcher.launch(headless=not args.headed)
        page = browser.new_page()
        print(f"Loading {args.url} ...")
        page.goto(args.url, wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_selector("#filemanager_itemslist [data-item-id]", timeout=args.wait * 1000)
        except Exception:
            print("Timed out waiting for file list. Try --headed to see what loaded.")
            page.screenshot(path=str(out.with_suffix(".png")))
            print(f"Screenshot: {out.with_suffix('.png')}")
            browser.close()
            return 1

        page.wait_for_timeout(2000)
        result = page.evaluate(EXTRACT_JS)
        if not result.get("ok"):
            print("Extract failed:", result.get("error"))
            browser.close()
            return 1

        files = result["files"]
        print(f"Folder: {result.get('folder')} | files: {len(files)}")
        if result.get("metadata"):
            print("Metadata:", json.dumps(result["metadata"]))

        lines = []
        for f in files:
            lines.append(f["url"])
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {len(lines)} URL(s) -> {out.resolve()}")

        manifest = out.with_suffix(".json")
        manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Wrote manifest -> {manifest.resolve()}")

        if args.inject:
            n = page.evaluate(INJECT_JS, result)
            print(f"Injected {n} links into page (look for blue 'DownThemAll links' box)")
            if args.headed:
                print("Browser left open — use DownThemAll here, then close manually.")
                try:
                    page.wait_for_timeout(3600_000)
                except KeyboardInterrupt:
                    pass
            else:
                page.screenshot(path=str(out.with_suffix(".injected.png")))
                print(f"Inject screenshot: {out.with_suffix('.injected.png')}")

        if not (args.inject and args.headed):
            browser.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
