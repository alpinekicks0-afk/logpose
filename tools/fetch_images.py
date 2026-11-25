#!/usr/bin/env python3
"""Download official card scans listed in a manifest into incoming/.

Run by .github/workflows/fetch-images.yml. The workspace the site is edited in
cannot reach Bandai's servers, so the scans are fetched on a GitHub runner and
committed as reduced masters; they are then resized to the site's conventions
and moved under public/img/ by hand, and incoming/ is emptied again.

Manifest: one "<url> <name>" pair per line, blank lines and # comments ignored.
Only Bandai's own card-game hosts are accepted.

Usage: python3 tools/fetch_images.py tools/image-manifest.txt incoming
"""
import io
import os
import sys
import urllib.parse
import urllib.request

from PIL import Image

ALLOWED_HOSTS = {
    "en.onepiece-cardgame.com",
    "fr.onepiece-cardgame.com",
    "www.onepiece-cardgame.com",
    "asia-en.onepiece-cardgame.com",
}
MAX_SIDE = 1200
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
}


def main():
    manifest, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    ok = failed = skipped = 0
    for raw in open(manifest, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        url, name = line.split()[:2]
        host = urllib.parse.urlsplit(url).hostname or ""
        if host not in ALLOWED_HOSTS or not url.startswith("https://"):
            print(f"REFUSED (host not allowed): {url}")
            failed += 1
            continue
        if not all(ch.isalnum() or ch in "-_." for ch in name) or name.startswith("."):
            print(f"REFUSED (bad name): {name}")
            failed += 1
            continue
        dest = os.path.join(out_dir, name + ".webp")
        if os.path.exists(dest):
            skipped += 1
            continue
        try:
            req = urllib.request.Request(url, headers={**HEADERS, "Referer": f"https://{host}/"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = resp.read()
            im = Image.open(io.BytesIO(data))
            im.load()
            src_size = im.size
            if max(im.size) > MAX_SIDE:
                im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            im.save(dest, "WEBP", quality=92, method=6)
            print(f"ok   {name:<28} {src_size[0]}x{src_size[1]} {len(data)//1024}KB -> {os.path.getsize(dest)//1024}KB")
            ok += 1
        except Exception as exc:  # report and carry on: one bad URL must not sink the batch
            print(f"FAIL {name:<28} {url} :: {exc}")
            failed += 1
    print(f"\n{ok} fetched, {skipped} already present, {failed} failed")


if __name__ == "__main__":
    main()
