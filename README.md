# Log Pose

A collector's guide for the ONE PIECE Trading Card Game — documented populations
for every championship prize card, the top hits of every main set, and the
iconic promos, each sourced to Bandai's own event pages.

Live at **https://logpose.cards**

## How it works

A static site. No build step, no dependencies, no server.

- `public/index.html` — the entire site: markup, styles, data and logic in one file
- `public/img/` — every card scan and page image
- `public/404.html` — a copy of the page, so mistyped URLs land on the site
- `public/_headers` — Cloudflare caching rules
- `public/robots.txt`, `public/sitemap.xml` — search engine basics
- `public/favicon.svg`, `public/apple-touch-icon.png`, `public/og.png` — icons and social preview

## Deploying

Connected to Cloudflare. Pushing to `main` deploys automatically.

The site lives in `public/` and `wrangler.jsonc` points there. Keeping it out
of the repo root is deliberate: Cloudflare caps a single asset at 25 MiB, and
publishing from the root would try to upload `.git` along with the site.

## Unofficial fan project

Not affiliated with, endorsed by, or connected to Bandai, Shueisha, Toei
Animation or Eiichiro Oda. All card images and artwork belong to their
respective owners. See the About / Disclaimer page on the site.
