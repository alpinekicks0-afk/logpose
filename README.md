# Log Pose

A collector's guide for the ONE PIECE Trading Card Game — documented populations
for every championship prize card, the top hits of every main set, and the
iconic promos, each sourced to Bandai's own event pages.

Live at **https://logpose.cards**

## How it works

A static site. No build step, no dependencies, no server.

- `index.html` — the entire site: markup, styles, data and logic in one file
- `img/` — every card scan and page image
- `404.html` — a copy of the page, so mistyped URLs land on the site
- `_headers` — Cloudflare caching rules
- `robots.txt`, `sitemap.xml` — search engine basics
- `favicon.svg`, `apple-touch-icon.png`, `og.png` — icons and social preview

## Deploying

Connected to Cloudflare Pages. Pushing to `main` deploys automatically.

## Unofficial fan project

Not affiliated with, endorsed by, or connected to Bandai, Shueisha, Toei
Animation or Eiichiro Oda. All card images and artwork belong to their
respective owners. See the About / Disclaimer page on the site.
