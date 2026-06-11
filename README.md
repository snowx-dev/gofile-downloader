# Gofile batch downloader

🤖 Vibe coded but works fine ✔️

Single script: browser session → file list + cookie → downloads.

**Deps:** `python3`, `playwright` (`pip install playwright && playwright install chromium`), `wget`

```bash
# preview
python3 gofile_fetch.py "https://gofile.io/d/FOLDER_ID" --list-only

# download
python3 gofile_fetch.py "https://gofile.io/d/FOLDER_ID" -d ./output
```

**429-prone:** add `--pause 15 --pause-429 180`

**Options:** `--limit N`, `--headed`, `--save-manifest path.json`

Session cookie is obtained automatically (no manual token export). Completed files are skipped; partial files resume.
