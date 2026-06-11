# Gofile batch downloader

Two-step bulk download for public Gofile folders.

🤖 Vibe coded but works fine ✔️


**Deps:** `python3`, `playwright` (`pip install playwright && playwright install chromium`), `wget`

## 1. Export links

```bash
python3 gofile_export_links.py "https://gofile.io/d/FOLDER_ID"
```

Writes `gofile_FOLDER_ID_urls.txt` and `gofile_FOLDER_ID_urls.json` (URLs, names, sizes).

Use `--headed` if the page does not load headless.

## 2. Download

Get `accountToken` from browser cookies (F12 → site storage → cookies for the file host domain). Do not save it in files tracked by git.

```bash
export GOFILE_TOKEN='...'
./gofile_download.sh gofile_FOLDER_ID_urls.json ./output
```

If you hit HTTP 429 often:

```bash
export GOFILE_WAIT=15
export GOFILE_429_WAIT=180
```

Completed files are skipped on re-run. Partial files resume via `wget -c`.

## Notes

- Raw `wget -i` on the URL list will fail without the session cookie (redirects to HTML, not files).
- Token via environment variable only; avoid writing it to disk or shell history.
