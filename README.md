# Gofile batch downloader

🤖 Vibe coded  
✔️ Battle tested

Single script: browser session → file list + cookie → downloads.

**Deps:** `python3`, `playwright` (`pip install playwright && playwright install chromium`), `wget`

```bash
python3 gofile_fetch.py "https://gofile.io/d/FOLDER_ID" -d ./output
```

**If 429s:** add `--pause 15 --pause-429 180`

**Options:** `--limit N`, `--headed`, `--save-manifest path.json`

Session cookie is obtained automatically with playwright. Completed files are skipped; partial files resume.
