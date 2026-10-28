#!/usr/bin/env python3
"""Generate crawlable pages for Log Pose.

The site itself is a single page: every card lives behind a `#` fragment, and a
search engine treats everything after `#` as the same URL. So 853 cards of
original research are invisible as search results. This writes a real page per
card and per section — each with its own title, description, canonical URL,
structured data and readable content — and links them together so they can be
crawled. Every page links back into the live app.

Usage:  python3 tools/build_pages.py <site.json> <public_dir>
"""
import html
import json
import os
import re
import sys

SITE = "https://logpose.cards"
NAME = "Log Pose"

TAB_SLUG = {
    "treasure": "treasure-cup", "regionals": "regionals", "nationals": "national-finals",
    "worlds": "world-finals", "storecs": "store-championship", "special": "special-tournaments",
    "mainsets": "main-sets", "serials": "serialized", "promos": "iconic-promos",
}

def esc(s):
    return html.escape(str(s or ""), quote=True)

def slug(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(s or "")).strip("-").lower()
    return re.sub(r"-{2,}", "-", s)

def clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canon}">
<meta name="theme-color" content="#0b1f33">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:type" content="{ogtype}">
<meta property="og:site_name" content="Log Pose">
<meta property="og:url" content="{canon}">
<meta property="og:title" content="{ogtitle}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{ogimage}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{ogtitle}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{ogimage}">
{jsonld}
<style>
:root{{--sea:#0b1f33;--gold:#d9a33a;--parchment:#efe3c6;--parchment2:#e4d4ad;--ink:#241a10;--rule:rgba(36,26,16,.18)}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--parchment);color:var(--ink);
 font:17px/1.65 Georgia,"Iowan Old Style","Times New Roman",serif;-webkit-text-size-adjust:100%}}
header{{background:var(--sea);color:var(--parchment);padding:14px 20px}}
header a{{color:var(--parchment);text-decoration:none;font-weight:700;letter-spacing:.04em}}
header .g{{color:var(--gold)}}
main{{max-width:760px;margin:0 auto;padding:28px 20px 72px}}
nav.crumb{{font-size:14px;margin-bottom:18px;color:#6b5a42}}
nav.crumb a{{color:#8a6f3f}}
h1{{font-size:30px;line-height:1.2;margin:.2em 0 .1em}}
h2{{font-size:21px;margin:1.9em 0 .5em;border-bottom:1px solid var(--rule);padding-bottom:.25em}}
.sub{{color:#6b5a42;margin:.2em 0 1.2em;font-size:16px}}
.hero{{display:flex;gap:22px;align-items:flex-start;flex-wrap:wrap}}
.hero img{{width:220px;max-width:46vw;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.25)}}
.pop{{display:inline-block;background:var(--sea);color:var(--gold);font:700 25px/1 ui-monospace,Menlo,monospace;
 padding:12px 18px;border-radius:10px;margin:.4em 0}}
.pop small{{display:block;color:var(--parchment2);font:600 11px/1.5 system-ui,sans-serif;
 letter-spacing:.09em;text-transform:uppercase;margin-top:6px}}
dl{{display:grid;grid-template-columns:minmax(120px,170px) 1fr;gap:6px 18px;margin:1.1em 0}}
dt{{font:600 12px/1.6 system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#6b5a42}}
dd{{margin:0}}
table{{width:100%;border-collapse:collapse;font-size:15px;margin:.6em 0}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--rule);vertical-align:top}}
th{{font:600 12px/1.5 system-ui,sans-serif;letter-spacing:.07em;text-transform:uppercase;color:#6b5a42}}
td.n{{text-align:right;font-family:ui-monospace,Menlo,monospace;white-space:nowrap}}
ul{{padding-left:1.1em}} li{{margin:.3em 0}}
a{{color:#8a6f3f}}
.cta{{display:inline-block;background:var(--sea);color:var(--parchment);text-decoration:none;
 padding:12px 22px;border-radius:999px;font:700 14px/1 system-ui,sans-serif;letter-spacing:.07em;
 text-transform:uppercase;margin:1.4em 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px;margin:1em 0;padding:0;list-style:none}}
.grid a{{text-decoration:none;color:inherit;display:block}}
.grid img{{width:100%;border-radius:6px;display:block;background:rgba(0,0,0,.06)}}
.grid b{{display:block;font:600 14px/1.35 system-ui,sans-serif;margin-top:6px}}
.grid span{{display:block;font:500 12px/1.4 system-ui,sans-serif;color:#6b5a42}}
.note{{background:rgba(217,163,58,.14);border-left:3px solid var(--gold);padding:10px 14px;margin:.8em 0;font-size:15px}}
footer{{border-top:1px solid var(--rule);margin-top:48px;padding-top:18px;font-size:14px;color:#6b5a42}}
@media (max-width:520px){{dl{{grid-template-columns:1fr;gap:2px 0}} dd{{margin-bottom:.7em}} h1{{font-size:25px}}}}
</style>
</head>
<body>
<header><a href="/">Log <span class="g">Pose</span></a></header>
<main>
{body}
<footer>
<p><strong>Log Pose</strong> is an unofficial fan project. Not affiliated with, endorsed by or connected to
Bandai, Shueisha, Toei Animation or Eiichiro Oda. All card images and artwork belong to their respective owners.
Population figures are our own research from the official sources cited on each page.</p>
<p><a href="/">Home</a> · <a href="/cards/">All cards</a> · <a href="/#citations">Citations</a></p>
</footer>
</main>
</body>
</html>
"""


def page(path, out_dir, **kw):
    kw.setdefault("ogtype", "article")
    kw.setdefault("ogimage", SITE + "/og.png")
    kw.setdefault("jsonld", "")
    d = os.path.join(out_dir, path.strip("/"))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(SHELL.format(**kw))


def ld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + "</script>"


def main(site_json, out_dir):
    data = json.load(open(site_json, encoding="utf-8"))
    cards, secs, sch, src = data["cards"], data["secs"], data["sch"], data["src"]
    tabnames, spotlight = data["tabNames"], data.get("spotlight", {})

    # Character groupings are needed while writing card pages, so load first.
    chars_path = os.path.join(os.path.dirname(site_json), "chars.json")
    chars = json.load(open(chars_path, encoding="utf-8")) if os.path.exists(chars_path) else []
    char_slug = {ch["name"]: slug(ch["name"])[:70] for ch in chars}
    char_of = {}
    for ch in chars:
        for i in ch["ranked"] + ch["extra"]:
            char_of.setdefault(i, ch["name"])

    # ---- card pages -----------------------------------------------------
    urls = []
    card_slug = {}
    taken = {}
    # Readable URLs: name + card number, disambiguated by the placement tier and
    # then by a counter only when two cards would otherwise collide.
    for cid, c in sorted(cards.items()):
        if c.get("kind") == "sheet":
            continue
        base = slug(f"{c['name']}-{c['number']}")[:70]
        s = base
        if s in taken:
            s = slug(f"{base}-{c.get('place','')}")[:90] or base
        if s in taken:
            n = 2
            while f"{base}-{n}" in taken:
                n += 1
            s = f"{base}-{n}"
        taken[s] = cid
        card_slug[cid] = s

    for cid, c in cards.items():
        if cid not in card_slug:
            continue
        s = card_slug[cid]
        canon = f"{SITE}/card/{s}/"
        tab = c.get("tab") or "featured"
        tabname = tabnames.get(tab, "the log")

        title_bits = [c["name"], c["number"]]
        if c.get("place"):
            title_bits.append(c["place"])
        h1 = f"{c['name']} · {c['number']}"
        title = f"{c['name']} {c['number']} — {c.get('place','')} population | Log Pose".replace("  ", " ")

        popline = c.get("pop") or "unpublished"
        desc_src = c.get("variant") or c.get("placement") or ""
        desc = clip(
            f"{c['name']} {c['number']}"
            + (f" ({c['place']})" if c.get("place") else "")
            + f" — documented population {popline}. "
            + desc_src,
            300,
        )

        body = [f'<nav class="crumb"><a href="/">Log Pose</a> › <a href="/s/{TAB_SLUG.get(tab, slug(tab))}/">{esc(tabname)}</a> › {esc(c["number"])}</nav>']
        body.append('<div class="hero">')
        if c.get("image"):
            body.append(f'<img src="/{esc(c["image"])}" alt="{esc(c["name"])} {esc(c["number"])}" width="220" loading="eager">')
        body.append("<div>")
        body.append(f"<h1>{esc(h1)}</h1>")
        if c.get("place"):
            body.append(f'<p class="sub">{esc(c["place"])}{" · " + esc(c["language"]) if c.get("language") else ""}</p>')
        label = "Documented population" if c.get("popKey") else "Print run"
        body.append(f'<div class="pop">{esc(popline)}<small>{esc(label)}</small></div>')
        body.append("</div></div>")

        if spotlight.get(cid, {}).get("lore"):
            body.append(f"<p>{esc(spotlight[cid]['lore'])}</p>")
        elif c.get("variant"):
            body.append(f"<p>{esc(c['variant'])}</p>")

        body.append("<h2>Card details</h2><dl>")
        for k, v in [
            ("Card number", c.get("number")), ("Set", c.get("set")),
            ("Rarity / tier", c.get("place")), ("Language", c.get("language")),
            ("Distributed", c.get("distributed")), ("How to get it", c.get("placement")),
        ]:
            if v:
                body.append(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>")
        body.append("</dl>")

        if c.get("dist"):
            rows = []
            for d in c["dist"]:
                s_ = sch.get(d["schedule"]) or {}
                rows.append(
                    "<tr><td>{}</td><td>{}</td><td class='n'>{}</td></tr>".format(
                        esc(s_.get("season", d["schedule"])),
                        esc(d.get("placement") or s_.get("label", "")),
                        esc(d.get("perEvent", "")),
                    )
                )
            if rows:
                body.append("<h2>Where the copies come from</h2>")
                body.append("<table><thead><tr><th>Season</th><th>Placement</th><th>Per event</th></tr></thead><tbody>")
                body.extend(rows)
                body.append("</tbody></table>")

        if c.get("gaps"):
            body.append("<h2>What the number can&rsquo;t account for</h2>")
            for g in c["gaps"]:
                body.append(f'<div class="note"><strong>{esc(g["title"])}</strong><br>{esc(clip(g["text"], 420))}</div>')

        links = [src[k] for k in c.get("sources", []) if k in src]
        if links:
            body.append("<h2>Sources</h2><ul>")
            for s_ in links:
                body.append(f'<li><a href="{esc(s_["url"])}" rel="nofollow noopener" target="_blank">{esc(s_["title"])}</a></li>')
            body.append("</ul>")

        body.append(f'<p><a class="cta" href="/#{esc(tab)}/{esc(cid)}">Open in the full dex →</a></p>')

        # Onward links: the character's own page, and a few siblings from the
        # same section. Without these each card page is a dead end for a
        # crawler and carries none of its neighbours' weight.
        rel = []
        who = char_of.get(cid)
        if who and who in char_slug:
            rel.append(f'<a href="/character/{char_slug[who]}/">All {esc(who)} cards</a>')
        rel.append(f'<a href="/s/{TAB_SLUG.get(tab, slug(tab))}/">All {esc(tabname)} cards</a>')
        sibs = [i for i in (secs.get(tab, {}).get("categories") and
                [x for c_ in secs[tab]["categories"] for x in c_["cards"]] or [])
                if i in card_slug and i != cid][:6]
        if rel or sibs:
            body.append("<h2>More in Log Pose</h2>")
            body.append("<p>" + " · ".join(rel) + "</p>")
            if sibs:
                body.append('<ul class="grid">')
                for i in sibs:
                    c2 = cards[i]
                    im = f'<img src="/{esc(c2["image"])}" alt="" loading="lazy">' if c2.get("image") else ""
                    body.append(f'<li><a href="/card/{card_slug[i]}/">{im}<b>{esc(c2["name"])}</b>'
                                f'<span>{esc(c2["number"])} · {esc(c2.get("pop") or "")}</span></a></li>')
                body.append("</ul>")

        jl = ld({
            "@context": "https://schema.org", "@type": "ItemPage",
            "name": f"{c['name']} {c['number']}", "description": desc, "url": canon,
            "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE + "/"},
            "breadcrumb": {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": NAME, "item": SITE + "/"},
                {"@type": "ListItem", "position": 2, "name": tabname, "item": f"{SITE}/s/{TAB_SLUG.get(tab, slug(tab))}/"},
                {"@type": "ListItem", "position": 3, "name": f"{c['name']} {c['number']}", "item": canon},
            ]},
        })
        page(f"/card/{s}/", out_dir, title=esc(title), desc=esc(desc), canon=canon,
             ogtitle=esc(f"{c['name']} {c['number']} — {popline}"),
             ogimage=(SITE + "/" + c["image"]) if c.get("image") else SITE + "/og.png",
             jsonld=jl, body="\n".join(body))
        urls.append((canon, "monthly", "0.7"))

    # ---- section pages --------------------------------------------------
    for tab, s in secs.items():
        if s.get("dynamic"):
            continue
        sl = TAB_SLUG.get(tab, slug(tab))
        canon = f"{SITE}/s/{sl}/"
        ids = [i for c in s["categories"] for i in c["cards"] if i in card_slug]
        body = [f'<nav class="crumb"><a href="/">Log Pose</a> › {esc(s["title"])}</nav>',
                f'<h1>{esc(s["title"])}</h1>',
                f'<p class="sub">{esc(clip(s["blurb"], 400))}</p>',
                f'<p><a class="cta" href="/#{esc(tab)}">Browse {esc(s["title"])} in the dex →</a></p>']
        for cat in s["categories"]:
            live = [i for i in cat["cards"] if i in card_slug]
            if not live:
                continue
            body.append(f"<h2>{esc(cat['name'])}</h2>")
            if cat.get("blurb"):
                body.append(f"<p>{esc(clip(cat['blurb'], 320))}</p>")
            body.append('<ul class="grid">')
            for i in live:
                c = cards[i]
                img = f'<img src="/{esc(c["image"])}" alt="" loading="lazy">' if c.get("image") else ""
                body.append(
                    f'<li><a href="/card/{card_slug[i]}/">{img}'
                    f'<b>{esc(c["name"])}</b><span>{esc(c["number"])} · {esc(c.get("pop") or "")}</span></a></li>'
                )
            body.append("</ul>")
        jl = ld({"@context": "https://schema.org", "@type": "CollectionPage",
                 "name": s["title"], "description": clip(s["blurb"], 300), "url": canon,
                 "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE + "/"}})
        page(f"/s/{sl}/", out_dir, title=esc(f"{s['title']} — populations and prize cards | Log Pose"),
             desc=esc(clip(s["blurb"], 300)), canon=canon, ogtitle=esc(s["title"]),
             jsonld=jl, body="\n".join(body))
        urls.append((canon, "weekly", "0.8"))

    # ---- character pages ------------------------------------------------
    if chars:
        for ch in chars:
            ranked = [i for i in ch["ranked"] if i in card_slug]
            extra = [i for i in ch["extra"] if i in card_slug]
            if not ranked and not extra:
                continue
            sl = char_slug[ch["name"]]
            canon = f"{SITE}/character/{sl}/"
            total = len(ranked) + len(extra)
            rarest = cards[ranked[0]] if ranked else None
            desc = clip(
                f"Every {ch['name']} card tracked by Log Pose — {total} in total"
                + (f", rarest first, starting with the {rarest['number']} {rarest.get('place','')} at {rarest.get('pop','')}" if rarest else "")
                + ". Championship prize cards with documented populations, plus main-set hits and promos.", 300)
            body = [f'<nav class="crumb"><a href="/">Log Pose</a> › <a href="/characters/">Characters</a> › {esc(ch["name"])}</nav>',
                    f'<h1>{esc(ch["name"])}</h1>',
                    f'<p class="sub">{esc(clip(ch.get("blurb") or ch["name"] + " cards on Log Pose, rarest first.", 300))}</p>']
            def grid(ids):
                out = ['<ul class="grid">']
                for i in ids:
                    c = cards[i]
                    img = f'<img src="/{esc(c["image"])}" alt="" loading="lazy">' if c.get("image") else ""
                    out.append(f'<li><a href="/card/{card_slug[i]}/">{img}<b>{esc(c["number"])}</b>'
                               f'<span>{esc(c.get("place") or "")} · {esc(c.get("pop") or "")}</span></a></li>')
                out.append("</ul>")
                return out
            if ranked:
                body.append(f"<h2>Championship cards, rarest first ({len(ranked)})</h2>")
                body.extend(grid(ranked))
            if extra:
                body.append(f"<h2>Main sets and iconic promos ({len(extra)})</h2>")
                body.append("<p>Booster pulls and handed-out promos. Bandai publishes no count for these.</p>")
                body.extend(grid(extra))
            body.append(f'<p><a class="cta" href="/#characters">Open the Character Index →</a></p>')
            jl = ld({"@context": "https://schema.org", "@type": "CollectionPage",
                     "name": f"{ch['name']} — every card", "description": desc, "url": canon,
                     "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE + "/"}})
            cover = next((cards[i]["image"] for i in ranked + extra if cards[i].get("image")), "")
            page(f"/character/{sl}/", out_dir,
                 title=esc(f"{ch['name']} — every card and population | Log Pose"),
                 desc=esc(desc), canon=canon, ogtitle=esc(f"{ch['name']} — every card"),
                 ogimage=(SITE + "/" + cover) if cover else SITE + "/og.png",
                 jsonld=jl, body="\n".join(body))
            urls.append((canon, "weekly", "0.8"))

        # index of characters
        body = ['<nav class="crumb"><a href="/">Log Pose</a> › Characters</nav>',
                "<h1>Every character in Log Pose</h1>",
                f'<p class="sub">All {len(char_slug)} characters with cards on the site. Each page lists that '
                "character's championship cards rarest first, then their main-set hits and promos.</p>",
                '<ul class="grid">']
        for ch in chars:
            ids = [i for i in ch["ranked"] + ch["extra"] if i in card_slug]
            if not ids:
                continue
            cover = next((cards[i]["image"] for i in ids if cards[i].get("image")), "")
            img = f'<img src="/{esc(cover)}" alt="" loading="lazy">' if cover else ""
            body.append(f'<li><a href="/character/{char_slug[ch["name"]]}/">{img}'
                        f'<b>{esc(ch["name"])}</b><span>{len(ids)} cards</span></a></li>')
        body.append("</ul>")
        page("/characters/", out_dir,
             title="Every ONE PIECE Card Game character and their cards | Log Pose",
             desc=esc("Browse every character with cards on Log Pose — championship prize cards with documented "
                      "populations, main-set hits and promos, grouped by character and ranked rarest first."),
             canon=SITE + "/characters/", ogtitle="Every character in Log Pose",
             jsonld=ld({"@context": "https://schema.org", "@type": "CollectionPage",
                        "name": "Every character in Log Pose", "url": SITE + "/characters/"}),
             body="\n".join(body))
        urls.append((SITE + "/characters/", "weekly", "0.9"))

    # ---- index of every card -------------------------------------------
    by_tab = {}
    for cid, s in card_slug.items():
        by_tab.setdefault(cards[cid].get("tab") or "other", []).append(cid)
    body = ['<nav class="crumb"><a href="/">Log Pose</a> › All cards</nav>',
            "<h1>Every card in Log Pose</h1>",
            f'<p class="sub">All {len(card_slug)} cards on the site, with their documented population. '
            'Each links to its own page with the event-by-event count and the official sources behind it.</p>']
    for tab in sorted(by_tab, key=lambda t: tabnames.get(t, t)):
        ids = sorted(by_tab[tab], key=lambda i: (cards[i]["name"], cards[i]["number"]))
        body.append(f'<h2>{esc(tabnames.get(tab, tab))} <span style="font:500 14px system-ui">({len(ids)})</span></h2><ul>')
        for i in ids:
            c = cards[i]
            body.append(f'<li><a href="/card/{card_slug[i]}/">{esc(c["name"])} · {esc(c["number"])}</a>'
                        f' — {esc(c.get("place") or "")} · {esc(c.get("pop") or "")}</li>')
        body.append("</ul>")
    page("/cards/", out_dir,
         title="Every ONE PIECE Card Game prize card and population | Log Pose",
         desc=esc(f"An index of all {len(card_slug)} cards tracked by Log Pose — championship prize cards, "
                  "serialised chase cards, main-set hits and iconic promos, each with its documented population."),
         canon=SITE + "/cards/", ogtitle="Every card in Log Pose",
         jsonld=ld({"@context": "https://schema.org", "@type": "CollectionPage",
                    "name": "Every card in Log Pose", "url": SITE + "/cards/"}),
         body="\n".join(body))
    urls.append((SITE + "/cards/", "weekly", "0.9"))

    # ---- sitemap --------------------------------------------------------
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
           f"  <url><loc>{SITE}/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>"]
    for u, freq, pri in urls:
        out.append(f"  <url><loc>{u}</loc><changefreq>{freq}</changefreq><priority>{pri}</priority></url>")
    out.append("</urlset>")
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    print(f"card pages : {len(card_slug)}")
    print(f"sections   : {sum(1 for t, s in secs.items() if not s.get('dynamic'))}")
    print(f"sitemap    : {len(urls) + 1} urls")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
