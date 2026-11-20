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
import hashlib
import html
import json
import os
import re
import shutil
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


def clip_words(s, n):
    """Cut on a clause or word boundary, with no ellipsis, staying within n."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(s) <= n:
        return s
    window = s[:n]
    for sep in (". ", "! ", "? ", ": ", "; "):
        idx = window.rfind(sep)
        if idx >= 70:
            return window[:idx].rstrip(" ,;:—-") + "."
    idx = window.rfind(", ")
    if idx >= 90:
        return window[:idx].rstrip(" ,;:—-") + "."
    sp = window.rfind(" ")
    cut = window[:sp] if sp >= 40 else window
    if cut.count("(") > cut.count(")"):
        cut = cut[:cut.rfind("(")]
    return cut.rstrip(" ,;:—-(") + "."


def meta_blurb(text, limit=155):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    m = re.match(r"^(.+?[.!?])(?:\s|$)", text)
    if m and 40 <= len(m.group(1)) <= limit:
        return m.group(1)
    return clip_words(text, limit)


_TITLE_SUFFIX = " | Log Pose"


def _looks_numbered(word):
    return bool(re.search(r"\d", word or ""))


def shrink_to(text, limit):
    """Shorten on a word boundary, keeping a card-number token when there is one."""
    text = re.sub(r"\s+", " ", str(text or "")).strip(" -—")
    if len(text) <= limit:
        return text
    words = text.split()
    numbered = [w for w in words if _looks_numbered(w)]
    num = numbered[0] if numbered else ""
    others = [w for w in words if w != num]
    kept = []
    for w in others:
        trial = " ".join(kept + [w] + ([num] if num else []))
        if len(trial) <= limit:
            kept.append(w)
        else:
            break
    out = " ".join(kept + ([num] if num else [])).strip()
    if out and len(out) <= limit:
        return out
    cut = text[:limit]
    sp = cut.rfind(" ")
    if sp >= int(limit * 0.5):
        cut = cut[:sp]
    return cut.rstrip(" -—|,")


def fit_title(core, limit=60):
    """Title of at most `limit` characters. The card name and number stay; the set is what shrinks."""
    core = re.sub(r"\s+", " ", str(core or "")).strip(" -—")
    if not core:
        core = NAME
    branded = NAME.lower() in core.lower()

    def finish(text):
        text = re.sub(r"\s+", " ", text).strip(" -—")
        if not branded and len(text) + len(_TITLE_SUFFIX) <= limit:
            return text + _TITLE_SUFFIX
        if len(text) <= limit:
            return text
        return shrink_to(text, limit)

    if " — " not in core:
        return finish(core)
    head, tail = core.split(" — ", 1)
    words = tail.split()
    while True:
        trial = f"{head} — {' '.join(words)}".strip(" —") if words else head
        trial = trial.rstrip(" ,;:—-")
        if not branded and len(trial) + len(_TITLE_SUFFIX) <= limit:
            return trial + _TITLE_SUFFIX
        if len(trial) <= limit:
            return trial
        if not words:
            return finish(head)
        words.pop()


def compress_set(s):
    s = str(s or "")
    reps = (
        ("PREMIUM BOOSTER -ONE PIECE CARD THE BEST- Storage Box Set", "The Best storage box"),
        ("PREMIUM BOOSTER -ONE PIECE CARD THE BEST vol.2-", "The Best vol.2"),
        ("Premium Card Collection", "PCC"),
        ("Offline Regional", "Offline"),
        ("Online Regional", "Online"),
        ("Finalist Card Set", "Finalist"),
        ("Champion Card Set", "Champion"),
        ("Winner Card Set", "Winner"),
        ("Top Players Pack", "Top Player Pack"),
        ("Storage Box Set premium foil", "storage box foil"),
        ("Championship ", "CS "),
        (" Season ", " S"),
    )
    for a, b in reps:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip(" -·")


def set_short(c):
    """Short set label that distinguishes printings of the same card."""
    raw = c.get("fromSet") or c.get("set") or ""
    raw = re.sub(r"\s*\(\d+\s+cards, awarded as one set\)", "", raw).strip()
    parens = [p.strip() for p in re.findall(r"\(([^)]*)\)", raw) if not re.search(r"\d+\s+cards", p)]
    base = compress_set(re.sub(r"\([^)]*\)", " ", raw))
    place = (c.get("place") or "").strip()
    if place:
        base = re.sub(rf"\b{re.escape(place)}\b", " ", base, count=1, flags=re.I)
    base = re.sub(r"\s+", " ", base).strip(" -·,")
    extra = compress_set(parens[-1]) if parens else ""
    extra = re.sub(r"\bpromo\b", "", extra, flags=re.I)
    extra = re.sub(r"\s+", " ", extra).strip(" -·,")
    if extra and extra.lower() not in base.lower():
        # A long product name plus a parenthetical note truncates the note,
        # which is usually the part that tells the printings apart.
        short = extra if len(base) > 28 else f"{base} {extra}".strip()
    else:
        short = base
    if not short:
        short = compress_set(c.get("variant") or place or c.get("tab") or "")
    return re.sub(r"\s+", " ", short).strip(" -·")


def card_titles(cards, ids):
    shorts = {cid: set_short(cards[cid]) for cid in ids}
    groups = {}
    for cid in ids:
        c = cards[cid]
        key = (c.get("name"), c.get("number"), c.get("place") or "", shorts[cid])
        groups.setdefault(key, []).append(cid)
    for members in groups.values():
        if len(members) < 2:
            continue
        for cid in members:
            extra = cards[cid].get("distributed") or cid
            shorts[cid] = f"{shorts[cid]} {extra}".strip()
    clash = {}
    for cid in ids:
        c = cards[cid]
        clash.setdefault((c.get("name"), c.get("number"), c.get("place") or "", shorts[cid]), []).append(cid)

    def token_for(cid, members):
        mine = slug(cid).split("-")
        others = [slug(o).split("-") for o in members if o != cid]
        for i, part in enumerate(mine):
            if part.isdigit():
                continue
            if any(i >= len(o) or o[i] != part for o in others):
                return part
        return slug(cid)[-8:]

    tokens = {}
    for members in clash.values():
        if len(members) < 2:
            continue
        for cid in members:
            tokens[cid] = token_for(cid, members)
    titles = {}
    used = {}
    for cid in ids:
        c = cards[cid]
        place = (c.get("place") or "").strip()
        short = shorts[cid]
        token = tokens.get(cid, "")
        # Identical printings only differ by a bit of the card id. Put that bit
        # in the title instead of the long tier, which would otherwise hide it.
        if token:
            head = " ".join(x for x in (c.get("name"), c.get("number"), token) if x)
        else:
            head = " ".join(x for x in (c.get("name"), c.get("number"), place) if x)
        options = []
        for extra in (short, f"{short} {c.get('language') or ''}".strip(), f"{short} {token}".strip(), token):
            extra = re.sub(r"\s+", " ", extra).strip()
            if extra and extra.lower() not in head.lower():
                options.append(f"{head} — {extra}")
            else:
                options.append(head)
        t = None
        for core in options:
            cand = fit_title(core)
            number_ok = c.get("number") and c["number"].lower() in cand.lower()
            token_ok = not token or token.lower() in cand.lower()
            if cand not in used and number_ok and token_ok:
                t = cand
                break
        if t is None:
            t = fit_title(f"{head} — {slug(cid)[-18:]}")
            n = 2
            while t in used:
                t = shrink_to(f"{c.get('number')} {slug(cid)[-12:]} {n}", 60)
                n += 1
        used[t] = cid
        titles[cid] = t
    return titles, shorts


def card_descriptions(cards, ids, shorts):
    descs = {}
    used = {}
    for cid in ids:
        c = cards[cid]
        place = (c.get("place") or "").strip()
        who = f"{c['name']} {c['number']}" + (f" ({place})" if place else "")
        pop = c.get("pop") or "unpublished"
        short = shorts.get(cid) or ""
        words = short.split()
        d = None
        while True:
            setbit = (" from " + " ".join(words)) if words else ""
            cand = re.sub(r"\s+", " ", f"{who}{setbit}: documented population {pop}.").strip()
            if len(cand) <= 155 and cand.count("(") == cand.count(")"):
                d = cand
                break
            if not words:
                d = clip_words(f"{c['number']} ({place}): documented population {pop}." if place else f"{c['number']}: documented population {pop}.", 155)
                break
            words.pop()
        if d in used:
            token = slug(cid).split("-")[-1]
            d = clip_words(f"{who} ({token}): documented population {pop}.", 155)
            n = 2
            while d in used:
                d = clip_words(f"{c['number']} {token} {n}: documented population {pop}.", 155)
                n += 1
        used[d] = cid
        descs[cid] = d
    return descs


def card_img(c, eager=False):
    if not c.get("image"):
        return ""
    sheet = c.get("kind") == "sheet"
    if eager:
        w, h = (220, 275) if sheet else (220, 307)
        loading = 'loading="eager" fetchpriority="high"'
    else:
        w, h = (140, 175) if sheet else (140, 195)
        loading = 'loading="lazy"'
    alt = f"{c.get('name','')} {c.get('number','')}".strip()
    if c.get("place"):
        alt += f" {c['place']}"
    cls = ' class="sheet"' if sheet else ""
    return (f'<img{cls} src="/{esc(c["image"])}" alt="{esc(alt)}" width="{w}" height="{h}" '
            f'decoding="async" {loading}>')


def og_extra(alt, width, height):
    return (f'<meta property="og:image:width" content="{width}">\n'
            f'<meta property="og:image:height" content="{height}">\n'
            f'<meta property="og:image:alt" content="{esc(alt)}">')


def load_existing_slugs(out_dir):
    """Map card id to the slug already published, from each page's dex link."""
    found = {}
    root = os.path.join(out_dir, "card")
    if not os.path.isdir(root):
        return found
    for name in os.listdir(root):
        path = os.path.join(root, name, "index.html")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m = re.search(r'class="cta" href="/#[^"]+/([^"]+)"', text)
        if m:
            found[m.group(1)] = name
    return found


def is_counter_slug(old, base):
    return bool(old and base and re.fullmatch(re.escape(base) + r"-[2-9]\d*", old))


def describe_slug(cid, c, base, taken):
    place = slug(c.get("place") or "")
    code = slug(set_short(c))[:42]
    parts = [base]
    if place and place not in base.split("-"):
        parts.append(place)
    if code and code not in "-".join(parts):
        parts.append(code)
    s = slug("-".join(parts))[:90].strip("-") or base
    if s in taken or is_counter_slug(s, base):
        s = slug(f"{base}-{place}-{cid}")[:90].strip("-")
    n = 2
    orig = s
    while s in taken or is_counter_slug(s, base):
        s = f"{orig[:82].rstrip('-')}-{n}"
        n += 1
    return s


def redirect_targets(out_dir):
    """Slugs that are only the destination of a rename, so they can still move."""
    targets = set()
    path = os.path.join(out_dir, "_redirects")
    if not os.path.isfile(path):
        return targets
    for line in open(path, encoding="utf-8"):
        parts = line.split()
        if len(parts) >= 3 and parts[-1] == "301" and parts[1].startswith("/card/"):
            targets.add(parts[1].strip("/").split("/")[-1])
    return targets


def assign_slugs(cards, out_dir):
    """Keep every descriptive URL. Replace only bare -2/-3 counter suffixes.

    A slug that is itself the target of a rename can still be rewritten, so a
    clearer set label replaces a truncated one and the 301 follows it.
    """
    existing = load_existing_slugs(out_dir)
    movable = redirect_targets(out_dir)
    card_slug = {}
    taken = {}
    redirects = []  # (old, new)
    pending = []
    for cid, c in cards.items():
        if c.get("kind") == "sheet":
            continue
        base = slug(f"{c['name']}-{c['number']}")[:70] or slug(cid)[:70]
        old = existing.get(cid)
        if old and old not in movable and not is_counter_slug(old, base) and old not in taken:
            card_slug[cid] = old
            taken[old] = cid
        else:
            pending.append((cid, base, old))
    for cid, base, old in pending:
        s = describe_slug(cid, cards[cid], base, taken)
        taken[s] = cid
        card_slug[cid] = s
        if old and old != s:
            redirects.append((old, s))
    return card_slug, redirects


def related_groups(cid, cards, char_of, card_slug, limit=6):
    c = cards[cid]
    def live(i):
        return i in card_slug and i != cid and cards[i].get("kind") != "sheet"
    same_num = [i for i in cards if live(i) and cards[i].get("number") == c.get("number")]
    who = char_of.get(cid)
    same_char = [i for i in cards if live(i) and who and char_of.get(i) == who and i not in same_num]
    set_name = c.get("fromSet") or ""
    # A product-line "set" such as "Paramount War [OP-02] promo" is shared by
    # unrelated prizes. Prize-set names (fromSet) are the real grouping.
    same_set = []
    if set_name:
        same_set = [i for i in cards if live(i) and cards[i].get("fromSet") == set_name
                    and i not in same_num and i not in same_char]
    def rank(i):
        k = cards[i].get("popKey")
        return (k is None, k if isinstance(k, (int, float)) else 10**12, cards[i].get("name") or "")
    same_num.sort(key=rank)
    same_char.sort(key=rank)
    same_set.sort(key=rank)
    groups = []
    if same_num:
        groups.append((f"Other prints of {c.get('number')}", same_num[:limit]))
    if who and same_char:
        groups.append((f"More {who} cards", same_char[:limit]))
    if same_set:
        groups.append(("Same set", same_set[:limit]))
    return groups


def sync_data_asset(out_dir):
    """Keep the catalog filename equal to a hash of its bytes."""
    assets = os.path.join(out_dir, "assets")
    if not os.path.isdir(assets):
        return
    files = [f for f in os.listdir(assets) if re.fullmatch(r"data\.[0-9a-f]+\.js", f)]
    if len(files) != 1:
        return
    path = os.path.join(assets, files[0])
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()[:10]
    new_name = f"data.{digest}.js"
    if files[0] != new_name:
        os.replace(path, os.path.join(assets, new_name))
    index = os.path.join(out_dir, "index.html")
    if not os.path.isfile(index):
        return
    text = open(index, encoding="utf-8").read()
    updated = re.sub(r"/assets/data\.[0-9a-f]+\.js", f"/assets/{new_name}", text)
    if updated != text:
        with open(index, "w", encoding="utf-8") as f:
            f.write(updated)


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
{ogextra}
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
h3{{font-size:17px;margin:1.3em 0 .35em}}
.sub{{color:#6b5a42;margin:.2em 0 1.2em;font-size:16px}}
.hero{{display:flex;gap:22px;align-items:flex-start;flex-wrap:wrap}}
.hero img{{width:220px;max-width:46vw;height:auto;aspect-ratio:63/88;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.25)}}
.hero img.sheet{{aspect-ratio:4/5}}
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
.grid img{{width:100%;height:auto;aspect-ratio:63/88;border-radius:6px;display:block;background:rgba(0,0,0,.06)}}
.grid img.sheet{{aspect-ratio:4/5}}
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
<p><a href="/">Home</a> · <a href="/sets/">Sets</a> · <a href="/events/">Events</a> · <a href="/tiers/">Tiers</a> · <a href="/cards/">All cards</a> · <a href="/characters/">Characters</a> · <a href="/rarest/">Rarest</a> · <a href="/about/">About</a> · <a href="/methodology/">Methodology</a></p>
</footer>
</main>
</body>
</html>
"""


def page(path, out_dir, **kw):
    kw.setdefault("ogtype", "article")
    kw.setdefault("ogimage", SITE + "/og.png")
    kw.setdefault("jsonld", "")
    kw.setdefault("ogextra", og_extra(
        "Log Pose — a collector's guide for the ONE PIECE Trading Card Game", 1200, 630))
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
    # Keep descriptive URLs. Only the bare numeric suffixes (-2, -3, …) move
    # to a set-based slug; those old paths are 301'd at the end.
    card_slug, redirects = assign_slugs(cards, out_dir)
    page_ids = list(card_slug)
    titles, shorts = card_titles(cards, page_ids)
    descs = card_descriptions(cards, page_ids, shorts)

    import landings
    landing_plan = landings.plan_from_site(
        cards, secs, card_slug,
        set(landings.existing_titles(out_dir)) | set(titles.values()),
    )

    for cid, c in cards.items():
        if cid not in card_slug:
            continue
        s = card_slug[cid]
        canon = f"{SITE}/card/{s}/"
        tab = c.get("tab") or "featured"
        tabname = tabnames.get(tab, "the log")

        h1 = f"{c['name']} · {c['number']}"
        title = titles[cid]
        popline = c.get("pop") or "unpublished"
        desc = descs[cid]

        body = [f'<nav class="crumb"><a href="/">Log Pose</a> › <a href="/s/{TAB_SLUG.get(tab, slug(tab))}/">{esc(tabname)}</a> › {esc(c["number"])}</nav>']
        body.append('<div class="hero">')
        hero = card_img(c, eager=True)
        if hero:
            body.append(hero)
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

        # Related cards are per card: other printings, the same character,
        # then the same prize set. Not the first six cards of the section.
        rel = []
        who = char_of.get(cid)
        if who and who in char_slug:
            rel.append(f'<a href="/character/{char_slug[who]}/">All {esc(who)} cards</a>')
        rel.append(f'<a href="/s/{TAB_SLUG.get(tab, slug(tab))}/">All {esc(tabname)} cards</a>')
        for href, label in landing_plan.links.get(cid, []):
            rel.append(f'<a href="{esc(href)}">{esc(label)}</a>')
        groups = related_groups(cid, cards, char_of, card_slug)
        if rel or groups:
            body.append("<h2>Related cards</h2>")
            if rel:
                body.append("<p>" + " · ".join(rel) + "</p>")
            for label, sibs in groups:
                body.append(f"<h3>{esc(label)}</h3>")
                body.append('<ul class="grid">')
                for i in sibs:
                    c2 = cards[i]
                    body.append(f'<li><a href="/card/{card_slug[i]}/">{card_img(c2)}<b>{esc(c2["name"])}</b>'
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
        img_alt = f"{c['name']} {c['number']}" + (f" {c['place']}" if c.get("place") else "") + " card"
        if c.get("image"):
            ogimage = SITE + "/" + c["image"]
            extra = og_extra(img_alt, 800, 1000) if c.get("kind") == "sheet" else og_extra(img_alt, 630, 880)
        else:
            ogimage = SITE + "/og.png"
            extra = None
        page(f"/card/{s}/", out_dir, title=esc(title), desc=esc(desc), canon=canon,
             ogtitle=esc(title), ogimage=ogimage,
             **({"ogextra": extra} if extra else {}),
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
                img = card_img(c)
                body.append(
                    f'<li><a href="/card/{card_slug[i]}/">{img}'
                    f'<b>{esc(c["name"])}</b><span>{esc(c["number"])} · {esc(c.get("pop") or "")}</span></a></li>'
                )
            body.append("</ul>")
        sec_title = fit_title(f"{s['title']} prize cards")
        sec_desc = meta_blurb(s.get("blurb") or s["title"])
        jl = ld({"@context": "https://schema.org", "@type": "CollectionPage",
                 "name": s["title"], "description": sec_desc, "url": canon,
                 "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE + "/"}})
        page(f"/s/{sl}/", out_dir, title=esc(sec_title),
             desc=esc(sec_desc), canon=canon, ogtitle=esc(sec_title),
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
            if rarest:
                desc = (f"{ch['name']}: {total} cards on Log Pose, rarest first. "
                        f"Scarcest is {rarest['number']}"
                        + (f" ({rarest.get('place')})" if rarest.get("place") else "")
                        + f" at {rarest.get('pop') or 'unpublished'}.")
            else:
                desc = f"{ch['name']}: {total} cards on Log Pose, main-set hits and promos with no published print run."
            desc = clip_words(desc, 155)
            body = [f'<nav class="crumb"><a href="/">Log Pose</a> › <a href="/characters/">Characters</a> › {esc(ch["name"])}</nav>',
                    f'<h1>{esc(ch["name"])}</h1>',
                    f'<p class="sub">{esc(clip(ch.get("blurb") or ch["name"] + " cards on Log Pose, rarest first.", 300))}</p>']
            def grid(ids):
                out = ['<ul class="grid">']
                for i in ids:
                    c = cards[i]
                    img = card_img(c)
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
            ch_title = fit_title(f"{ch['name']} cards")
            page(f"/character/{sl}/", out_dir,
                 title=esc(ch_title),
                 desc=esc(desc), canon=canon, ogtitle=esc(ch_title),
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
            img = (f'<img src="/{esc(cover)}" alt="{esc(ch["name"])}" width="140" height="195" '
                   f'loading="lazy" decoding="async">') if cover else ""
            body.append(f'<li><a href="/character/{char_slug[ch["name"]]}/">{img}'
                        f'<b>{esc(ch["name"])}</b><span>{len(ids)} cards</span></a></li>')
        body.append("</ul>")
        chars_title = fit_title("One Piece TCG characters")
        chars_desc = "Every character with cards on Log Pose. Prize cards are ranked rarest first, then main-set hits and promos."
        page("/characters/", out_dir,
             title=esc(chars_title),
             desc=esc(chars_desc),
             canon=SITE + "/characters/", ogtitle=esc(chars_title),
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
            'Each links to its own page with the event-by-event count and the official sources behind it.</p>',
            '<p>Browse the same cards by <a href="/sets/">set</a>, '
            '<a href="/events/">event or prize set</a> and <a href="/tiers/">tier</a>.</p>']
    for tab in sorted(by_tab, key=lambda t: tabnames.get(t, t)):
        ids = sorted(by_tab[tab], key=lambda i: (cards[i]["name"], cards[i]["number"]))
        body.append(f'<h2>{esc(tabnames.get(tab, tab))} <span style="font:500 14px system-ui">({len(ids)})</span></h2><ul>')
        for i in ids:
            c = cards[i]
            body.append(f'<li><a href="/card/{card_slug[i]}/">{esc(c["name"])} · {esc(c["number"])}</a>'
                        f' — {esc(c.get("place") or "")} · {esc(c.get("pop") or "")}</li>')
        body.append("</ul>")
    cards_title = fit_title("Every One Piece TCG prize card")
    cards_desc = clip_words(
        f"All {len(card_slug)} One Piece TCG cards on Log Pose, each with its documented population.", 155)
    page("/cards/", out_dir,
         title=esc(cards_title),
         desc=esc(cards_desc),
         canon=SITE + "/cards/", ogtitle=esc(cards_title),
         jsonld=ld({"@context": "https://schema.org", "@type": "CollectionPage",
                    "name": "Every card in Log Pose", "url": SITE + "/cards/"}),
         body="\n".join(body))
    urls.append((SITE + "/cards/", "weekly", "0.9"))

    # ---- rarest cards ranking -------------------------------------------
    # The most linkable page on the site: a single ranked list is the thing
    # people cite and argue with, which is what earns inbound links.
    ranked = sorted(
        [i for i in card_slug if cards[i].get("popKey")],
        key=lambda i: (cards[i]["popKey"], cards[i]["name"]))
    if ranked:
        body = ['<nav class="crumb"><a href="/">Log Pose</a> › Rarest cards</nav>',
                "<h1>The rarest ONE PIECE Card Game cards, by documented population</h1>",
                '<p class="sub">Every card on Log Pose that has a documented population, ranked from fewest '
                'copies to most. Counts come from Bandai&rsquo;s own event and product pages; each card links to '
                'the working behind its number. Cards with no published print run are listed separately at '
                '<a href="/cards/">every card</a>.</p>',
                "<table><thead><tr><th>#</th><th>Card</th><th>Number</th><th>Tier</th><th class='n'>Population</th></tr></thead><tbody>"]
        for n, i in enumerate(ranked, 1):
            c = cards[i]
            body.append(
                f"<tr><td class='n'>{n}</td>"
                f"<td><a href='/card/{card_slug[i]}/'>{esc(c['name'])}</a></td>"
                f"<td>{esc(c['number'])}</td><td>{esc(c.get('place') or '')}</td>"
                f"<td class='n'>{esc(c.get('pop') or '')}</td></tr>")
        body.append("</tbody></table>")
        body.append('<p><a class="cta" href="/#featured">Browse the chase cards →</a></p>')
        rare_title = fit_title("Rarest One Piece TCG cards")
        rare_desc = clip_words(
            f"{len(ranked)} One Piece TCG cards ranked by documented population, rarest first, "
            "counted from Bandai's event pages.", 155)
        page("/rarest/", out_dir,
             title=esc(rare_title),
             desc=esc(rare_desc),
             canon=SITE + "/rarest/", ogtitle=esc(rare_title),
             jsonld=ld({"@context": "https://schema.org", "@type": "Dataset",
                        "name": "ONE PIECE Card Game card populations",
                        "description": rare_desc,
                        "url": SITE + "/rarest/", "creator": {"@type": "Organization", "name": NAME, "url": SITE + "/"},
                        "isAccessibleForFree": True, "license": SITE + "/methodology/"}),
             body="\n".join(body))
        urls.append((SITE + "/rarest/", "weekly", "0.9"))

    # ---- questions page --------------------------------------------------
    qa = []
    if ranked:
        top = cards[ranked[0]]
        qa.append(("What is the rarest ONE PIECE Card Game card?",
                   f"By documented population the scarcest card tracked here is the {top['name']} {top['number']} "
                   f"({top.get('place','')}), at {top.get('pop','')}. Several World Final and Coliseum trophy cards "
                   "are one-of-one, awarded to a single champion and never sold."))
    pt = next((cards[i] for i in card_slug if cards[i]["number"] == "P-033"), None)
    if pt:
        qa.append(("How many textured finalist Luffy cards exist?",
                   f"The P-033 Monkey.D.Luffy from the Championship 2023 Event Pack Finalist Ver. sits at "
                   f"{pt.get('pop','')}. Only Top 32 finishers at the 2023 Finals received the pack, and it held "
                   "eleven textured cards, so the count is packs awarded divided across the card types."))
    qa += [
        ("What does a population count mean on Log Pose?",
         "It is the number of copies that can be accounted for from Bandai's published event and product pages: "
         "events run, multiplied by the copies awarded at each placement. A plus sign means the figure is a floor "
         "— copies exist that cannot be counted, usually from store-run events whose host list Bandai never "
         "published."),
        ("Are these numbers the same as PSA or Beckett population reports?",
         "No. Graded population reports count cards submitted for grading, and the same card can be counted twice "
         "if it is cracked and resubmitted. These figures count copies awarded at source, which is a different "
         "measure and usually a much smaller number."),
        ("What is a serial-numbered One Piece card?",
         "A card printed with its own number on the face, such as 047/700. Bandai has used them for Regionals, "
         "Treasure Cup and World Final prizes. Because the run size is printed on the card itself, these are the "
         "only ONE PIECE cards with a population that is certain rather than reconstructed."),
        ("Which One Piece cards are one-of-one?",
         "The World Final champion trophies from the 25-26 season onward are serial-numbered 1/1, as are the "
         "Flame-Flame Fruit Coliseum regional champion trophies. Each exists in a single copy for its region or "
         "placement."),
    ]
    body = ['<nav class="crumb"><a href="/">Log Pose</a> › Questions</nav>',
            "<h1>Questions about One Piece TCG card populations</h1>",
            '<p class="sub">How the counts on this site are built, and the questions collectors ask most. '
            'Every figure links to the card page that shows its working.</p>']
    for q, a in qa:
        body.append(f"<h2>{esc(q)}</h2><p>{esc(a)}</p>")
    body.append('<p>The counting rules are written out on the <a href="/methodology/">methodology</a> page.</p>')
    body.append('<p><a class="cta" href="/cards/">See every card and its population →</a></p>')
    q_title = fit_title("One Piece TCG population questions")
    q_desc = "What a Log Pose population count means, how it differs from PSA and Beckett, and which cards are one of one."
    page("/questions/", out_dir,
         title=esc(q_title),
         desc=esc(q_desc),
         canon=SITE + "/questions/", ogtitle=esc(q_title),
         jsonld=ld({"@context": "https://schema.org", "@type": "FAQPage",
                    "mainEntity": [{"@type": "Question", "name": q,
                                    "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}),
         body="\n".join(body))
    urls.append((SITE + "/questions/", "monthly", "0.8"))

    urls.extend(landings.render(landing_plan, out_dir, cards, card_slug))
    mainsets_path = os.path.join(out_dir, "s", "main-sets", "index.html")
    if os.path.isfile(mainsets_path):
        with open(mainsets_path, encoding="utf-8") as f:
            mainsets_html = f.read()
        mainsets_html, _changed = landings.link_mainsets(mainsets_html, landing_plan)
        with open(mainsets_path, "w", encoding="utf-8") as f:
            f.write(mainsets_html)
    report = landings.counts(landing_plan)
    print(f"sets       : {report['sets']} {report['set_families']}")
    print(f"events     : {report['events']} {report['event_groups']}")
    print(f"tiers      : {report['tiers']}")

    # ---- about and methodology (static copies of the home-app essays) ----
    about_title = fit_title("About Log Pose, an unofficial fan site")
    about_desc = "Log Pose is an unofficial One Piece TCG fan site for prize-card populations, grail chases and the sources behind every count."
    about_body = """
<nav class="crumb"><a href="/">Log Pose</a> › About</nav>
<h1>About Log Pose</h1>
<p class="sub">An unofficial fan reference for ONE PIECE Card Game prize cards.</p>
<p>Hey guys, after a lot of community demand and support for the previous pop report, we made this website to help people keep live track of the pop counts of prize cards easy and smooth, and not be overwhelmed or lost when it comes to learning about them since many people don't know where to look or how to check them. And other than just prize cards we want to make this a place where grail hunters and newcomers can easily find grails, so we also included the grail chases of every set and the iconic promo cards.</p>
<p>We tallied all the prize cards from every Regional, Nationals, World Championship and Treasure Cup below, including all the side events where some additional ones were given out like the side events during Regionals and Nationals, and have cited all the official sources of distribution for each card on the card's page and under the Citations tab.</p>
<p>Even though we tallied all the official distributions, there are some cards that got leaked, as with any TCG. Magic has leaked Alpha Black Lotus cards, Pokémon has a bunch of World Championship and even Illustrator cards that have been leaked, and so does Yu-Gi-Oh. It's part of every TCG, and even though it sucks it doesn't mean the cards themselves aren't valuable — look at the other TCGs for example. The leaks are real cards, made in case one gets damaged or lost, which make their way to the market.</p>
<p>Bandai has been getting better with time by arresting employees who were behind the leaks. The pop counts on grading sites like Beckett and PSA aren't correct either, since many of these cards have been re-submitted to try and get a higher grade — and even if only a few people do it, when the pops are this low it can cause a big hindrance in their report. Some have also been mislabeled by Beckett and PSA (non-textured event cards as a textured finalist), so you can't trust the grading pop reports either. The Kaido Nationals winner, for example, has been resubmitted over 20 times to try and get a black label, just from people we know.</p>
<p>Some cards have a few leaks while others do not, so as a general rule of thumb, assume the true pop accounting for leaks is 20–25%, or 10–15 cards, higher than the official pop mentioned below.</p>
<p>That's all — have fun hunting, collect the grails you love, and find your One Piece!</p>
<p>How a count is built, and why it is not a PSA population, is on the <a href="/methodology/">methodology</a> page.</p>
<h2>The founders</h2>
<p>Log Pose is kept by two collectors. Alpine (<a href="https://www.instagram.com/alpine.cards/" rel="noopener">@alpine.cards</a>) and Davy (<a href="https://www.instagram.com/davy_d_xebec_/" rel="noopener">@davy_d_xebec_</a>).</p>
<h2>Disclaimer</h2>
<p><strong>Unofficial fan project.</strong> One Piece TCG Log Pose is an independent, non-commercial fan site. It is not affiliated with, endorsed by, sponsored by, or in any way officially connected to Bandai Co., Ltd., Bandai Namco, Shueisha, Toei Animation, Eiichiro Oda, or any of their subsidiaries or affiliates.</p>
<p>ONE PIECE and the ONE PIECE CARD GAME, including all card names, card images, logos, characters and artwork, are the property of their respective owners. All such material appears here for identification, commentary and reference under fair use. No ownership is claimed over any of it. Population figures are our own research, compiled from the official event and product pages cited throughout the site.</p>
<p>Nothing here is financial or investment advice. Population counts are best-effort estimates from published sources and may be incomplete or wrong; do not treat them as a guarantee of scarcity or value when buying, selling or grading a card. If you are a rights holder and want something removed, get in touch through either Instagram account above and we will take it down.</p>
""".strip()
    page("/about/", out_dir, title=esc(about_title), desc=esc(about_desc),
         canon=SITE + "/about/", ogtitle=esc(about_title), ogtype="website",
         jsonld=ld({"@context": "https://schema.org", "@type": "AboutPage",
                    "name": "About Log Pose", "description": about_desc,
                    "url": SITE + "/about/",
                    "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE + "/"}}),
         body=about_body)
    urls.append((SITE + "/about/", "monthly", "0.6"))

    method_title = fit_title("How Log Pose counts populations")
    method_desc = "Population counts come from Bandai's official event pages: events times copies awarded at each placement. A plus sign means the figure is a floor."
    method_body = """
<nav class="crumb"><a href="/">Log Pose</a> › Methodology</nav>
<h1>How Log Pose counts a population</h1>
<p class="sub">Documented print-run supply, counted from Bandai's own pages. Not a graded-population census and not a price.</p>
<p>Population counts come only from pages on en.onepiece-cardgame.com, the official English site run by Bandai. Secondary sources (news summaries of Bandai's announcements) are listed for context and never used as the sole basis for a number. Each card page carries its own numbered source list; the bracketed numbers in its event table and notes point to that list. Card images are Bandai's official prize images, used with their SAMPLE watermark intact, and remain © Eiichiro Oda / Shueisha / Bandai.</p>
<h2>The working</h2>
<ol>
<li>Open the official event page for every event series that lists the card (or its prize set) as a prize, and record the placement and copies per player.</li>
<li>Count every tournament on the official schedule for that series. Copies per event equal the number of players who reach that placement (Top 64 means 64, Top 16 means 16, Champion means 1).</li>
<li>Multiply, subtotal by region and by series, and add the series together.</li>
<li>Check every other official page from the same and later seasons — side-event prize walls, Finals, Store Championship — for the same card. List what adds copies without a number, and what was checked and ruled out.</li>
</ol>
<h2>What the number means</h2>
<p>It is the number of copies that can be accounted for from Bandai's published event and product pages: events run, multiplied by the copies awarded at each placement. A plus sign means the figure is a floor — copies exist that cannot be counted, usually from store-run events whose host list Bandai never published. Where Bandai does not publish a number, the page says unpublished instead of guessing.</p>
<p>Pack cards are an expected value: packs handed out, times cards per pack, divided by the number of card types in the pack. Those figures are marked with an approximation sign.</p>
<h2>Not a PSA or Beckett population</h2>
<p>Graded population reports count cards submitted for grading, and the same card can be counted twice if it is cracked and resubmitted. These figures count copies awarded at source, which is a different measure and usually a much smaller number. Grading companies have also mislabeled some prints (a non-textured event card filed as a textured finalist), so a graded pop is not a check on the count here.</p>
<p>Leaks happen, as they do in every trading card game: extra copies made in case one is damaged, which later reach the market. As a rule of thumb, assume the true pop accounting for leaks is about 20–25 percent, or 10–15 cards, higher than the official figure. That adjustment is not added into the number on the card, because it cannot be sourced.</p>
<p>Who keeps the site, and the disclaimer that goes with an unofficial fan project, is on the <a href="/about/">about</a> page.</p>
""".strip()
    page("/methodology/", out_dir, title=esc(method_title), desc=esc(method_desc),
         canon=SITE + "/methodology/", ogtitle=esc(method_title), ogtype="article",
         jsonld=ld({"@context": "https://schema.org", "@type": "WebPage",
                    "name": "How Log Pose counts populations", "description": method_desc,
                    "url": SITE + "/methodology/",
                    "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE + "/"}}),
         body=method_body)
    urls.append((SITE + "/methodology/", "monthly", "0.6"))

    # ---- redirects for renamed card URLs --------------------------------
    # Previous 301s are kept, so a later rebuild still serves the old paths
    # after their directories have been removed.
    live = set(card_slug.values())
    pairs = {}  # source path -> destination path, both with the spelling we emit

    def add_redirect(src, dest):
        src = "/" + src.strip("/")
        dest = "/" + dest.strip("/") + "/"
        if src.rstrip("/") == dest.rstrip("/"):
            return
        pairs[src] = dest
        if not src.endswith("/"):
            pairs[src + "/"] = dest

    prev = os.path.join(out_dir, "_redirects")
    kept_other = []
    if os.path.isfile(prev):
        for line in open(prev, encoding="utf-8"):
            parts = line.split()
            if len(parts) >= 3 and parts[-1] in ("301", "302") and parts[0].startswith("/card/") and parts[1].startswith("/card/"):
                add_redirect(parts[0], parts[1])
            elif line.strip() and not line.startswith("# Former card"):
                kept_other.append(line.rstrip("\n"))
    moved = []
    for old, new in redirects:
        if not old or old == new or old in live:
            continue
        moved.append((old, new))
        add_redirect(f"/card/{old}", f"/card/{new}")
        old_dir = os.path.join(out_dir, "card", old)
        if os.path.isdir(old_dir):
            shutil.rmtree(old_dir)
    # Collapse A → B → C into A → C so a rebuilt slug does not strand the first URL.
    def final_dest(dest, seen=None):
        seen = seen or set()
        while dest in pairs and dest not in seen:
            seen.add(dest)
            dest = pairs[dest]
        return dest
    resolved = {}
    for src, dest in pairs.items():
        dest = final_dest(dest)
        src_slug = src.strip("/").split("/")[-1]
        dest_slug = dest.strip("/").split("/")[-1]
        if src.rstrip("/") == dest.rstrip("/"):
            continue
        if dest_slug in live and src_slug not in live:
            resolved[src] = dest if dest.endswith("/") else dest + "/"
    redir_lines = []
    if kept_other:
        redir_lines.extend(kept_other)
        redir_lines.append("")
    redir_lines.append("# Former card URLs. Numeric -2/-3 suffixes now use the set name.")
    for src in sorted(resolved):
        redir_lines.append(f"{src} {resolved[src]} 301")
    with open(prev, "w", encoding="utf-8") as f:
        f.write("\n".join(redir_lines) + "\n")

    os.makedirs(os.path.join(out_dir, "assets"), exist_ok=True)
    with open(os.path.join(out_dir, "assets", "card-slugs.js"), "w", encoding="utf-8") as f:
        f.write("var CARD_SLUGS = " + json.dumps(card_slug, ensure_ascii=False, separators=(",", ":")) + ";\n")
    sync_data_asset(out_dir)

    # ---- sitemap --------------------------------------------------------
    # Google ignores <changefreq> and <priority> but does read <lastmod>, and
    # uses it to decide what to recrawl. Stamp every URL with the build date.
    import datetime
    lm = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
           f"  <url><loc>{SITE}/</loc><lastmod>{lm}</lastmod>"
           f"<changefreq>weekly</changefreq><priority>1.0</priority></url>"]
    for u, freq, pri in urls:
        out.append(f"  <url><loc>{u}</loc><lastmod>{lm}</lastmod>"
                   f"<changefreq>{freq}</changefreq><priority>{pri}</priority></url>")
    out.append("</urlset>")
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    print(f"card pages : {len(card_slug)}")
    print(f"redirects  : {len(moved)}")
    print(f"sections   : {sum(1 for t, s in secs.items() if not s.get('dynamic'))}")
    print(f"sitemap    : {len(urls) + 1} urls")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--catalog":
        import json as _json
        import landings
        _built, _report = landings.apply_catalog(sys.argv[2], sys.argv[3])
        print(_json.dumps({k: v for k, v in _report.items() if k != "broken_links"}, indent=2))
        if _report["problems"] or _report["broken_count"] or _report["missing_card_files"] or _report["card_links_missed"]:
            print("broken sample:", _report["broken_links"][:15])
            raise SystemExit(1)
    else:
        main(sys.argv[1], sys.argv[2])
