"""Set, event and tier landing pages for Log Pose.

Pages are planned from the card catalog (number, set, prize-set, tier and the
populations already published on each card page) and written with the same
shell as the other static pages. Thin one-card events are grouped instead of
getting a URL that only repeats a card page.
"""
import html
import json
import os
import re
from collections import defaultdict
from pathlib import Path

SITE = "https://logpose.cards"

# Release dates and tier labels copied from public/index.html (MS_RELEASE, MS_TIER).
MS_RELEASE = {
    "OP-01": "December 2, 2022", "OP-02": "March 10, 2023", "OP-03": "June 30, 2023",
    "OP-04": "September 22, 2023", "OP-05": "December 8, 2023", "OP-06": "March 15, 2024",
    "OP-07": "June 28, 2024", "OP-08": "September 13, 2024", "OP-09": "December 13, 2024",
    "OP-10": "March 21, 2025", "OP-11": "June 6, 2025", "OP-12": "August 22, 2025",
    "OP-13": "November 7, 2025", "OP14-EB04": "January 16, 2026", "OP15-EB04": "April 3, 2026",
    "OP-16": "June 12, 2026", "OP-17": "August 28, 2026", "OP-18": "November 20, 2026",
    "EB-01": "May 3, 2024", "EB-02": "May 9, 2025", "EB-03": "February 20, 2026",
    "EB-05": "October 30, 2026", "PRB-01": "November 8, 2024", "PRB-02": "October 3, 2025",
}
MS_TIER = {
    "Crew Alt-Art": "Crew alternate art", "Special Manga": "Special Manga",
    "Gold SSP": "Gold SSP", "Silver SSP": "Silver SSP", "Oda Signature": "Oda Signature",
    "Manga Rare": "Manga Rare", "Manga Leader": "Manga Leader", "Event Manga": "Event Manga",
    "Special Alt-Art": "Special alternate art", "Demon Pack SSP": "Demon Pack SSP",
    "Wanted SP": "Wanted-poster SP", "SP Card": "SP Card",
    "Chinese TR": "Chinese-exclusive Treasure Rare",
    "French TR": "French-exclusive Treasure Rare",
    "Japanese TR": "Japanese-exclusive Treasure Rare",
    "Treasure Rare": "Treasure Rare", "Anime 25th parallel": "Anime 25th leader parallel",
    "Textured Finalist Pack": "Textured Finalist",
}

# Placement and rarity labels that are real tiers. Promo product names also
# land in the place field; those become event pages, not tier pages.
TIER_PLACES = {
    "Champion", "Finalist", "Top 64", "Top 32", "Top 16", "Top 8", "Top 4",
    "Top Player Pack", "Textured Finalist Pack", "Store Winner", "Serial",
    "Participation", "2nd Place", "3rd Place", "SP Card", "Manga Rare",
    "Event Manga", "Manga Leader", "Treasure Rare", "Wanted SP", "Chinese TR",
    "French TR", "Japanese TR", "Gold SSP", "Silver SSP", "Demon Pack SSP",
    "Special Manga", "Special Alt-Art", "Crew Alt-Art", "Anime 25th parallel",
    "Oda Signature",
}
TIER_MIN = 4

GROUP_LABEL = {
    "prize": "Prize card sets",
    "treasure": "Treasure Cups",
    "regionals": "Regional waves",
    "nationals": "National Finals",
    "worlds": "World Finals",
    "special": "Special tournaments",
    "store": "Store Championships and release events",
    "promo": "Promos and product releases",
}
GROUP_ORDER = ["prize", "treasure", "regionals", "nationals", "worlds", "special", "store", "promo"]
TAB_GROUP = {
    "treasure": "treasure", "regionals": "regionals", "nationals": "nationals",
    "worlds": "worlds", "special": "special", "storecs": "store", "promos": "promo",
}
FAMILY = {"OP": "Boosters", "EB": "Extra Boosters", "PRB": "Premium Boosters", "ST": "Starter decks"}
FAMILY_ORDER = ["OP", "EB", "PRB", "ST"]

# English booster titles from Bandai's product pages on en.onepiece-cardgame.com.
# OP-14 and OP-15 are sold as OP14-EB04 and OP15-EB04, so the catalog headings
# are bare codes. Used only when a heading has no subtitle of its own.
# OP-14: BOOSTER PACK -THE AZURE SEA'S SEVEN- [OP14-EB04]
# OP-15: BOOSTER PACK -ADVENTURE ON KAMI'S ISLAND- [OP15-EB04]
# OP-16: BOOSTER PACK -THE TIME OF BATTLE- [OP-16]
# OP-17: BOOSTER PACK -THE WORLD'S STRONGEST WARRIORS- [OP-17]
# OP-18: BOOSTER PACK -THE DOMINANCE OF GOD- [OP-18]
OFFICIAL_SET_NAMES = {
    "OP-14": "The Azure Sea's Seven",
    "OP-15": "Adventure on Kami's Island",
    "OP-16": "The Time of Battle",
    "OP-17": "The World's Strongest Warriors",
    "OP-18": "The Dominance of God",
}

OLD_FOOT = '<p><a href="/">Home</a> · <a href="/cards/">All cards</a> · <a href="/#citations">Citations</a></p>'
NEW_FOOT = ('<p><a href="/">Home</a> · <a href="/sets/">Sets</a> · <a href="/events/">Events</a> '
            '· <a href="/tiers/">Tiers</a> · <a href="/cards/">All cards</a> · <a href="/#citations">Citations</a></p>')
CARDS_INDEX_LINE = ('Browse the same cards by <a href="/sets/">set</a>, '
                    '<a href="/events/">event or prize set</a> and <a href="/tiers/">tier</a>.')


def esc(s):
    return html.escape(str(s or ""), quote=True)


def slugify(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(s or "")).strip("-").lower()
    return re.sub(r"-{2,}", "-", s)


def words(s):
    return len(re.sub(r"\s+", " ", s).split())


def product_code(text):
    """OP13-118 -> OP-13, PRB02-005 -> PRB-02, ST-10 -> ST-10. P-001 does not match."""
    if not text:
        return None
    m = re.match(r"^(OP|EB|ST|PRB)-?(\d+)\b", str(text).strip().upper())
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2)):02d}"


def codes_in(text):
    if not text:
        return []
    return [f"{a}-{int(b):02d}" for a, b in re.findall(r"(OP|EB|ST|PRB)-?(\d+)", str(text).upper())]


def set_url_slug(code):
    return code.replace("-", "").lower()


def pop_key(pop):
    if not pop or str(pop).strip().lower() == "unpublished":
        return (1, 10 ** 12)
    m = re.search(r"[\d,]+", str(pop))
    if not m:
        return (1, 10 ** 12)
    return (0, int(m.group(0).replace(",", "")))


def season_of(card):
    parts = [p.strip() for p in (card.get("variant") or "").split(" · ") if p.strip()]
    fs = card.get("fromSet") or ""
    if fs and fs in parts:
        return " · ".join(parts[parts.index(fs) + 1:])
    return ""


def first_sentences(text, max_words=60):
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if not sent:
            continue
        trial = " ".join(out + [sent])
        if out and words(trial) > max_words:
            break
        out.append(sent)
        if words(" ".join(out)) >= 40:
            break
    return " ".join(out)


def fit_words(parts, lo=80, hi=120):
    """Join priority-ordered sentences into a paragraph of lo..hi words."""
    chosen = []
    for part in parts:
        part = re.sub(r"\s+", " ", part or "").strip()
        if not part:
            continue
        trial = chosen + [part]
        n = words(" ".join(trial))
        if chosen and n > hi:
            continue
        chosen = trial
        if words(" ".join(chosen)) >= lo:
            # Keep going only while we stay inside the cap. Later parts are skipped
            # once we are already in range and the next one would overflow.
            pass
    text = " ".join(chosen).strip()
    if words(text) > hi:
        # Drop from the end until the core fits, but never drop the first sentence.
        while len(chosen) > 1 and words(" ".join(chosen)) > hi:
            chosen.pop()
        text = " ".join(chosen).strip()
    return text


def choose_title(candidates, used):
    suffix = " | Log Pose"
    options = []
    for core in candidates:
        core = re.sub(r"\s+", " ", core).strip(" -|")
        if not core:
            continue
        if len(core) + len(suffix) <= 60:
            options.append(core + suffix)
        elif len(core) <= 60:
            options.append(core)
        else:
            cut = core[:60]
            if " " in cut:
                cut = cut.rsplit(" ", 1)[0]
            options.append(cut)
    for title in options:
        if title not in used and 8 <= len(title) <= 60:
            used.add(title)
            return title
    base = options[0] if options else "Log Pose"
    n = 2
    while True:
        extra = f" ({n})"
        title = base[: 60 - len(extra)].rstrip() + extra
        if title not in used and len(title) <= 60:
            used.add(title)
            return title
        n += 1


def choose_desc(candidates, used):
    options = []
    for raw in candidates:
        desc = re.sub(r"\s+", " ", raw).strip()
        if len(desc) > 155:
            cut = desc[:155]
            dot = max(cut.rfind(". "), cut.rfind("."))
            if dot >= 90:
                desc = cut[: dot + 1]
            elif " " in cut:
                desc = cut.rsplit(" ", 1)[0]
        if desc and len(desc) <= 155:
            options.append(desc)
    for desc in options:
        if desc not in used:
            used.add(desc)
            return desc
    base = options[0]
    n = 2
    while True:
        extra = f" ({n})"
        desc = (base[: 155 - len(extra)].rstrip() + extra)
        if desc not in used and len(desc) <= 155:
            used.add(desc)
            return desc
        n += 1


def release_sentence(code, ms_release):
    solo = []
    combos = []
    for key, date in ms_release.items():
        codes = codes_in(key)
        if codes == [code]:
            solo.append(date)
        elif code in codes and len(codes) > 1:
            others = [c for c in codes if c != code]
            combos.append((others, date))
    if solo:
        return f"Release date on file: {solo[0]}."
    if combos:
        bits = []
        for others, date in combos:
            if others:
                bits.append(f"with {others[0]} on {date}")
            else:
                bits.append(f"on {date}")
        return f"In this log, {code} is released " + " and ".join(bits) + "."
    return ""


def names_from_sections(sections):
    """Official set subtitles from the Main Sets categories, when the heading has one."""
    out = {}
    main = sections.get("mainsets") or {}
    for cat in main.get("categories") or []:
        name = cat.get("name") or ""
        m = re.match(r"^(OP|EB|PRB)-(\d+)\s*·\s*(.+)$", name)
        if not m:
            continue
        code = f"{m.group(1)}-{int(m.group(2)):02d}"
        subtitle = re.split(r"\s+[—–-]+\s+releases\b", m.group(3), maxsplit=1)[0].strip()
        if not subtitle or "+" in subtitle or re.match(r"^(OP|EB|PRB)-\d+$", subtitle):
            continue
        out[code] = subtitle
    return out


def starter_names(cards):
    found = defaultdict(list)
    for card in cards.values():
        for m in re.finditer(r"([^\[]+?)\s*\[ST-(\d+)\]", card.get("set") or ""):
            name = m.group(1).strip(" -–—")
            if not name or name.lower() in {"starter deck", "promo", "starter deck promo"}:
                continue
            found[f"ST-{int(m.group(2)):02d}"].append(name)
    out = {}
    for code, names in found.items():
        out[code] = sorted(set(names), key=lambda n: (-names.count(n), -len(n), n))[0]
    return out


def live_ids(ids, cards, card_slug):
    out = []
    seen = set()
    for i in ids:
        if i in seen or i not in card_slug:
            continue
        if cards.get(i, {}).get("kind") == "sheet":
            continue
        seen.add(i)
        out.append(i)
    return out


def sort_ids(ids, cards):
    return sorted(ids, key=lambda i: (pop_key(cards[i].get("pop")), cards[i].get("name") or "", cards[i].get("number") or ""))


def tier_label(place, ms_tier):
    return ms_tier.get(place) or MS_TIER.get(place) or place


def _counted_sentence(n, nd, nu, low, cards):
    low_bit = f", the lowest being {card_sentence(low, cards)}" if low else ""
    if nd == 0:
        if nu == 1:
            return ("None of them has a documented print-run population. The card is unpublished, "
                    "because the printing is confirmed and no print run was published.")
        return (f"None of them has a documented print-run population. All {nu} are unpublished, "
                "because the printing is confirmed and no print run was published.")
    if nu:
        verb = "has" if nd == 1 else "have"
        return (f"{nd} of them {verb} a documented print-run population{low_bit}. "
                f"{nu} {'is' if nu == 1 else 'are'} unpublished, because the printing is confirmed and no print run was published.")
    return f"All {nd} have a documented print-run population{low_bit}."


def count_line(ids, cards):
    pops = [cards[i].get("pop") or "unpublished" for i in ids]
    documented = [p for p in pops if pop_key(p)[0] == 0]
    return len(ids), len(documented), len(ids) - len(documented)


def rarest(ids, cards):
    ranked = [i for i in ids if pop_key(cards[i].get("pop"))[0] == 0]
    if not ranked:
        return None
    return min(ranked, key=lambda i: (pop_key(cards[i].get("pop")), cards[i].get("name") or ""))


def tier_counts(ids, cards):
    counts = defaultdict(int)
    for i in ids:
        place = cards[i].get("place") or ""
        if place:
            counts[place] += 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def tab_names(ids, cards, sections):
    titles = {}
    for tab, sec in sections.items():
        titles[tab] = sec.get("title") or tab
    seen = []
    for i in ids:
        tab = cards[i].get("tab") or ""
        label = titles.get(tab) or ""
        if label and label not in seen:
            seen.append(label)
    return seen


def join_list(items):
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]


def methodology():
    return ("A population here is the copies that can be accounted for from Bandai's "
            "event and product pages. It is not a PSA or Beckett census, which only "
            "counts cards that were sent in to be graded.")


def card_sentence(i, cards):
    c = cards[i]
    place = f" ({c.get('place')})" if c.get("place") else ""
    return f"{c.get('name')} {c.get('number')}{place} at {c.get('pop')}"


class Plan:
    def __init__(self):
        self.sets = []
        self.events = []
        self.tiers = []
        self.hubs = []
        self.links = defaultdict(list)  # cid -> [(href, label)]
        self.by_path = {}


def _page(kind, group, path, h1, title, desc, intro, ids, crumbs):
    return {
        "kind": kind, "group": group, "path": path, "h1": h1, "title": title,
        "desc": desc, "intro": intro, "ids": ids, "crumbs": crumbs, "related": [],
    }


def plan(cards, card_slug, sections, prize_sets, ms_release, ms_tier, existing_titles):
    ms_release = ms_release or MS_RELEASE
    ms_tier = dict(MS_TIER)
    ms_tier.update(ms_tier or {})
    used_titles = set(existing_titles or [])
    used_descs = set()
    out = Plan()

    # ---- sets -----------------------------------------------------------
    subtitles = names_from_sections(sections)
    subtitles.update({k: v for k, v in starter_names(cards).items() if k not in subtitles})
    for code, name in OFFICIAL_SET_NAMES.items():
        if not subtitles.get(code):
            subtitles[code] = name
    members = defaultdict(list)
    for cid in card_slug:
        card = cards.get(cid) or {}
        if card.get("kind") == "sheet":
            continue
        code = product_code(card.get("number"))
        if code:
            members[code].append(cid)
        exact = codes_in(card.get("mainset"))
        if len(exact) == 1 and exact[0] != code:
            members[exact[0]].append(cid)
    for code in members:
        members[code] = sort_ids(list(dict.fromkeys(members[code])), cards)

    def set_sort_key(code):
        fam, num = code.split("-")
        return (FAMILY_ORDER.index(fam) if fam in FAMILY_ORDER else 9, int(num))

    set_by_code = {}
    for code in sorted(members, key=set_sort_key):
        ids = members[code]
        if not ids:
            continue
        name = subtitles.get(code, "")
        n, nd, nu = count_line(ids, cards)
        low = rarest(ids, cards)
        rel = release_sentence(code, ms_release)
        fam = FAMILY.get(code.split("-")[0], "set")
        h1 = f"{code} {name}".strip() if name else f"{code} prize and chase cards"
        subject = f"{code} ({name})" if name else code
        tiers = tier_counts(ids, cards)
        tier_bit = ""
        if tiers:
            shown = [f"{tier_label(p, ms_tier)} ({k})" for p, k in tiers[:4]]
            tier_bit = f"The tiers on this page are {join_list(shown)}."
        parts = [
            f"{subject} on Log Pose is every prize card, promo and chase pull tracked for that {fam[:-1].lower() if fam.endswith('s') else fam}, {n} {'card' if n == 1 else 'cards'} in all. It is not a checklist of the whole set.",
            rel,
            _counted_sentence(n, nd, nu, low, cards),
            tier_bit,
            methodology(),
            "Each card links to the page with the event-by-event working and the official sources.",
        ]
        intro = fit_words(parts)
        title = choose_title([
            f"{code} {name} prize cards".replace("  ", " ").strip(),
            f"{code} prize cards and populations",
            f"{code} chase and prize cards",
        ], used_titles)
        low_bit = f" Lowest documented is {cards[low]['name']} {cards[low]['number']} at {cards[low]['pop']}." if low else ""
        desc = choose_desc([
            f"{subject}: {n} prize, promo and chase cards on Log Pose, {nd} with a documented population.{low_bit} Print-run counts from Bandai's pages, not a PSA census.",
            f"{n} tracked {code} cards, {nd} with a documented population.{low_bit}",
        ], used_descs)
        path = f"/set/{set_url_slug(code)}/"
        page = _page("set", code.split("-")[0], path, h1, title, desc, intro, ids, [
            ("Log Pose", "/"), ("Sets", "/sets/"), (code, None),
        ])
        page["code"] = code
        page["name"] = name
        out.sets.append(page)
        set_by_code[code] = page
        out.by_path[path] = page

    # ---- events: prize sets --------------------------------------------
    prize_pages = {}
    if not prize_sets:
        grouped = defaultdict(list)
        for cid in card_slug:
            fs = (cards.get(cid) or {}).get("fromSet")
            if fs:
                grouped[fs].append(cid)
        prize_sets = [{"name": name, "members": ids, "season": "", "distributed": "", "place": "", "tab": ""}
                      for name, ids in grouped.items()]
    used_slugs = set()

    def event_slug(name):
        base = slugify(name)[:80].strip("-") or "event"
        s = base
        n = 2
        while s in used_slugs:
            s = f"{base}-{n}"
            n += 1
        used_slugs.add(s)
        return s

    for spec in prize_sets:
        ids = sort_ids(live_ids(spec.get("members") or [], cards, card_slug), cards)
        if len(ids) < 2:
            continue
        name = spec["name"]
        season = spec.get("season") or season_of(cards[ids[0]])
        distributed = spec.get("distributed") or cards[ids[0]].get("distributed") or ""
        n, nd, nu = count_line(ids, cards)
        low = rarest(ids, cards)
        pops = {cards[i].get("pop") for i in ids}
        shared = ""
        if len(pops) == 1 and pop_key(next(iter(pops)))[0] == 0:
            shared = f"The cards were awarded together as one set, so each documented population is {next(iter(pops))}."
        h1 = name
        parts = [
            f"{name} is a prize set of {n} cards tracked on Log Pose.",
            f"Season on file: {season}." if season else "",
            f"Handed out {distributed}." if distributed else "",
            shared or (f"The lowest documented population is {card_sentence(low, cards)}." if low else ""),
            f"{nd} {'has' if nd == 1 else 'have'} a documented population and {nu} {'is' if nu == 1 else 'are'} unpublished." if nu else "",
            methodology(),
            "Open a card for the event-by-event count and the official page it was counted from.",
        ]
        intro = fit_words(parts)
        path = f"/event/{event_slug(name)}/"
        title = choose_title([
            f"{name} prize cards",
            f"{name} populations",
            name,
        ], used_titles)
        desc = choose_desc([
            f"{name}: {n} cards, {nd} with a documented population."
            + (f" Season: {season}." if season else "")
            + (f" Lowest is {cards[low]['name']} at {cards[low]['pop']}." if low else "")
            + " Print runs from Bandai's event pages.",
            f"{n} cards in {name}, with the documented population of each.",
        ], used_descs)
        page = _page("event", "prize", path, h1, title, desc, intro, ids, [
            ("Log Pose", "/"), ("Events", "/events/"), (name, None),
        ])
        page["spec"] = name
        out.events.append(page)
        prize_pages[name] = page
        out.by_path[path] = page

    # ---- events: section categories ------------------------------------
    cat_pages = []  # (tab, name, page, idset)
    pending_store = defaultdict(list)  # group -> [(cat, ids)]
    pending_promo = []
    for tab, sec in sections.items():
        if tab in {"mainsets", "serials", "characters"}:
            continue
        group = TAB_GROUP.get(tab)
        if not group:
            continue
        for cat in sec.get("categories") or []:
            ids = live_ids(cat.get("cards") or [], cards, card_slug)
            if tab == "storecs" and len(ids) < 2:
                if ids:
                    pending_store[cat.get("group") or "store"].append((cat, ids))
                continue
            if tab == "promos" and len(ids) < 2:
                if ids:
                    pending_promo.append((cat, ids))
                continue
            if len(ids) < 2:
                continue
            idset = set(ids)
            # A category that is exactly one prize set is the same page.
            same = [p for p in prize_pages.values() if set(p["ids"]) == idset]
            if same:
                continue
            ids = sort_ids(ids, cards)
            name = cat["name"]
            blurb = first_sentences(cat.get("blurb") or "")
            n, nd, nu = count_line(ids, cards)
            low = rarest(ids, cards)
            h1 = name
            shown = [f"{tier_label(p, ms_tier)} ({k})" for p, k in tier_counts(ids, cards)[:3]]
            parts = [
                blurb or f"{name} lists {n} cards tracked by Log Pose.",
                f"{n} cards are on this page, {nd} with a documented population"
                + (f" and {nu} unpublished" if nu else "") + ".",
                f"The lowest documented population is {card_sentence(low, cards)}." if low else "",
                methodology(),
                (f"Tiers in this list: {join_list(shown)}." if shown else ""),
                "Each row links to the card page, where the event-by-event working and the official source are cited.",
            ]
            intro = fit_words(parts)
            path = f"/event/{event_slug(name)}/"
            title = choose_title([
                f"{name} prize cards",
                f"{name} cards",
                name,
            ], used_titles)
            desc = choose_desc([
                f"{name}: {n} cards on Log Pose, {nd} with a documented population."
                + (f" Lowest is {cards[low]['name']} {cards[low]['number']} at {cards[low]['pop']}." if low else "")
                + " Counts from Bandai's published distribution.",
                f"{n} cards from {name}, each with its documented population.",
            ], used_descs)
            page = _page("event", group, path, h1, title, desc, intro, ids, [
                ("Log Pose", "/"), ("Events", "/events/"), (name, None),
            ])
            cat_pages.append((tab, name, page, idset))
            out.by_path[path] = page

    # Drop a category page whose cards are entirely on a larger category page.
    drop = set()
    for i, (tab, name, page, idset) in enumerate(cat_pages):
        for j, (tab2, name2, page2, idset2) in enumerate(cat_pages):
            if i == j:
                continue
            if idset < idset2:
                drop.add(i)
                break
    kept_cats = []
    for i, row in enumerate(cat_pages):
        if i in drop:
            continue
        kept_cats.append(row)
        out.events.append(row[2])
    for i, (tab, name, page, idset) in enumerate(cat_pages):
        if i not in drop:
            continue
        parent = None
        for j, (tab2, name2, page2, idset2) in enumerate(cat_pages):
            if j in drop or i == j:
                continue
            if idset < idset2 and (parent is None or len(idset2) < len(parent[3])):
                parent = (tab2, name2, page2, idset2)
        if not parent:
            continue
        note = f"{name} uses these same cards, so it is covered on this page instead of repeated."
        intro = parent[2]["intro"]
        closer = "Each row links to the card page, where the event-by-event working and the official source are cited."
        if words(intro + " " + note) <= 120:
            parent[2]["intro"] = intro + " " + note
        elif closer in intro and words(intro.replace(closer, note)) <= 120:
            parent[2]["intro"] = intro.replace(closer, note)

    def containing_category(idset):
        best = None
        for tab, name, page, other in kept_cats:
            if idset <= other and (best is None or len(other) < len(best[3])):
                best = (tab, name, page, other)
        return best

    # Group the one-card store and release events.
    group_titles = {
        "Store Championships & Store Regionals": (
            "Store Championship and Store Regionals winner cards",
            "store-championship-winner-cards",
        ),
        "Anniversary & Pre-Release / Release Event winners": (
            "Pre-release and release event winner cards",
            "pre-release-and-release-event-winners",
        ),
    }
    grouped_pages = {}
    for group_name, rows in pending_store.items():
        ids = sort_ids([i for cat, ids_ in rows for i in ids_], cards)
        ids = list(dict.fromkeys(ids))
        if len(ids) < 2:
            continue
        title_name, slug = group_titles.get(group_name, (group_name, slugify(group_name)[:70]))
        if slug in used_slugs:
            slug = event_slug(title_name)
        else:
            used_slugs.add(slug)
        n, nd, nu = count_line(ids, cards)
        low = rarest(ids, cards)
        listed = join_list([cat["name"] for cat, _ in rows[:6]])
        more = len(rows) - min(6, len(rows))
        listing = listed + (f", and {more} more" if more else "")
        parts = [
            f"{title_name} gathers {n} winner cards that each come from their own store event. "
            f"Kept together, they are one page instead of {len(rows)} single-card URLs.",
            f"The events on file include {listing}.",
            f"{nd} {'has' if nd == 1 else 'have'} a documented population and {nu} {'is' if nu == 1 else 'are'} unpublished. "
            "Store events often have no published store count, which is why a winner card can sit here without a number.",
            f"The lowest documented population is {card_sentence(low, cards)}." if low else "",
            methodology(),
        ]
        intro = fit_words(parts)
        path = f"/event/{slug}/"
        h1 = title_name
        title = choose_title([
            f"{title_name}",
            "Store and release event winner cards" if "release" in title_name.lower() else title_name,
        ], used_titles)
        desc = choose_desc([
            f"{title_name}: {n} winner cards from separate events, {nd} with a documented population. "
            "Grouped so one-card events are not thin duplicate pages. Counts from Bandai's event pages.",
        ], used_descs)
        page = _page("event", "store", path, h1, title, desc, intro, ids, [
            ("Log Pose", "/"), ("Events", "/events/"), (h1, None),
        ])
        out.events.append(page)
        grouped_pages[group_name] = page
        out.by_path[path] = page

    if len(pending_promo) >= 2:
        ids = sort_ids([i for cat, ids_ in pending_promo for i in ids_], cards)
        ids = list(dict.fromkeys(ids))
        title_name = "One-off collaboration promos"
        slug = "one-off-collaboration-promos"
        if slug in used_slugs:
            slug = event_slug(title_name)
        else:
            used_slugs.add(slug)
        n, nd, nu = count_line(ids, cards)
        low = rarest(ids, cards)
        listed = join_list([cat["name"] for cat, _ in pending_promo])
        parts = [
            f"This page gathers {n} promo cards that each come from a release with only one card on Log Pose. "
            f"They share a page so neither release is a thin duplicate of its card page.",
            f"The releases are {listed}.",
            ("None of them has a documented population; the print run was not published."
             if nd == 0 else
             f"{nd} {'has' if nd == 1 else 'have'} a documented population and {nu} {'is' if nu == 1 else 'are'} unpublished."),
            f"The lowest documented population is {card_sentence(low, cards)}." if low else "",
            methodology(),
            "Each row links to the card page, where the source for that promo is cited.",
        ]
        intro = fit_words(parts)
        path = f"/event/{slug}/"
        title = choose_title([
            "One-off collaboration promo cards",
            "Collaboration promos and populations",
        ], used_titles)
        desc = choose_desc([
            f"One-off collaboration promos: {n} cards from releases with a single tracked card, "
            f"{nd} with a documented population. Grouped to avoid thin pages. Counts from the cited sources.",
        ], used_descs)
        page = _page("event", "promo", path, title_name, title, desc, intro, ids, [
            ("Log Pose", "/"), ("Events", "/events/"), (title_name, None),
        ])
        out.events.append(page)
        grouped_pages["one-off-promos"] = page
        out.by_path[path] = page

    # Parent wave on each prize-set page, and child prize sets on wave pages.
    for page in list(prize_pages.values()):
        parent = containing_category(set(page["ids"]))
        if parent:
            page["related"].append((parent[2]["path"], parent[2]["h1"]))
    for tab, name, page, idset in kept_cats:
        for prize in prize_pages.values():
            pset = set(prize["ids"])
            if pset and pset < idset:
                page["related"].append((prize["path"], prize["h1"]))

    # ---- tiers ----------------------------------------------------------
    by_place = defaultdict(list)
    for cid in card_slug:
        card = cards.get(cid) or {}
        if card.get("kind") == "sheet":
            continue
        place = card.get("place") or ""
        if place in TIER_PLACES:
            by_place[place].append(cid)
    tier_by_place = {}
    for place, ids in sorted(by_place.items(), key=lambda kv: -len(kv[1])):
        if len(ids) < TIER_MIN:
            continue
        ids = sort_ids(ids, cards)
        label = tier_label(place, ms_tier)
        n, nd, nu = count_line(ids, cards)
        low = rarest(ids, cards)
        sections_here = tab_names(ids, cards, sections)
        where = f"They are filed under {join_list(sections_here)}." if sections_here else ""
        nums = [pop_key(cards[i].get("pop"))[1] for i in ids if pop_key(cards[i].get("pop"))[0] == 0]
        span = ""
        if len(nums) >= 2:
            span = f" Documented figures run from {min(nums):,} to {max(nums):,}."
        if nd == 0:
            counted = f"None of them has a documented print-run population; all {nu} are unpublished."
        elif nu:
            counted = (f"{nd} {'has' if nd == 1 else 'have'} a documented print-run population "
                       f"and {nu} {'is' if nu == 1 else 'are'} unpublished.{span}")
        else:
            counted = f"All {nd} have a documented print-run population.{span}"
        parts = [
            f"Log Pose files {n} cards under {label}. On each card page the rarity or tier field is {place}.",
            counted,
            where,
            f"The lowest documented population is {card_sentence(low, cards)}." if low else "",
            methodology(),
            "This page lists every card with that tier, rarest first, and links to the card page for the working.",
        ]
        intro = fit_words(parts)
        h1 = f"{label} cards"
        path = f"/tier/{slugify(label) or slugify(place)}/"
        # guard slug collisions inside tiers
        base = path
        k = 2
        while path in out.by_path:
            path = f"/tier/{slugify(label)}-{k}/"
            k += 1
        title = choose_title([
            f"{label} cards and populations",
            f"{label} One Piece TCG cards",
            f"{label} cards",
        ], used_titles)
        desc = choose_desc([
            f"{label}: {n} One Piece TCG cards on Log Pose, {nd} with a documented population."
            + (f" Lowest is {cards[low]['name']} {cards[low]['number']} at {cards[low]['pop']}." if low else "")
            + " Print runs from Bandai, not a graded census.",
            f"Every {label} card tracked here, {n} in all, with its documented population.",
        ], used_descs)
        page = _page("tier", "tier", path, h1, title, desc, intro, ids, [
            ("Log Pose", "/"), ("Tiers", "/tiers/"), (label, None),
        ])
        page["place"] = place
        page["label"] = label
        out.tiers.append(page)
        tier_by_place[place] = page
        out.by_path[path] = page

    # ---- card links -----------------------------------------------------
    cat_lookup = {(tab, name): page for tab, name, page, idset in kept_cats}

    def category_pages_for(cid):
        found = []
        for tab, sec in sections.items():
            for cat in sec.get("categories") or []:
                if cid in (cat.get("cards") or []):
                    page = cat_lookup.get((tab, cat.get("name")))
                    if page and page not in found:
                        found.append(page)
        return found

    primary_tab_order = list(sections.keys())

    for cid in card_slug:
        card = cards.get(cid) or {}
        if card.get("kind") == "sheet":
            continue
        anchors = []
        seen = set()

        def add(href, label):
            if not href or href in seen:
                return
            seen.add(href)
            anchors.append((href, label))

        codes = []
        code = product_code(card.get("number"))
        if code and code in set_by_code:
            codes.append(code)
        exact = codes_in(card.get("mainset"))
        if len(exact) == 1 and exact[0] in set_by_code and exact[0] not in codes:
            codes.append(exact[0])
        for code in codes:
            add(set_by_code[code]["path"], f"{code} cards")

        fs = card.get("fromSet") or ""
        if fs in prize_pages:
            add(prize_pages[fs]["path"], prize_pages[fs]["h1"])
        cats = category_pages_for(cid)
        # Prefer the category in the card's own section, then any other.
        tab = card.get("tab") or ""
        cats.sort(key=lambda p: 0 if any(
            cid in (cat.get("cards") or []) and cat.get("name") == p["h1"]
            for cat in (sections.get(tab) or {}).get("categories") or []
        ) else 1)
        for page in cats[:1]:
            add(page["path"], page["h1"])
        if not any(h.startswith("/event/") for h, _ in anchors):
            for page in grouped_pages.values():
                if cid in page["ids"]:
                    add(page["path"], page["h1"])
                    break
        place = card.get("place") or ""
        if place in tier_by_place:
            add(tier_by_place[place]["path"], f"All {tier_by_place[place]['label']} cards")
        out.links[cid] = anchors

    # Related blocks: sets <-> events/tiers, from the cards actually listed.
    def top_codes(ids, limit=6):
        counts = defaultdict(int)
        for i in ids:
            code = product_code(cards[i].get("number"))
            if code and code in set_by_code:
                counts[code] += 1
        return [set_by_code[c] for c, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]

    def top_tiers(ids, limit=6):
        counts = defaultdict(int)
        for i in ids:
            place = cards[i].get("place") or ""
            if place in tier_by_place:
                counts[place] += 1
        return [tier_by_place[p] for p, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]

    def top_events(ids, limit=6):
        counts = defaultdict(int)
        pages = {}
        for i in ids:
            for href, label in out.links.get(i, []):
                if href.startswith("/event/"):
                    counts[href] += 1
                    pages[href] = label
        return [(href, pages[href]) for href, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]

    for page in out.sets:
        for ev_href, ev_label in top_events(page["ids"]):
            if (ev_href, ev_label) not in page["related"]:
                page["related"].append((ev_href, ev_label))
        for tier in top_tiers(page["ids"]):
            page["related"].append((tier["path"], tier["h1"]))
    for page in out.events:
        for sp in top_codes(page["ids"]):
            page["related"].append((sp["path"], sp["h1"]))
        for tier in top_tiers(page["ids"], 4):
            page["related"].append((tier["path"], tier["h1"]))
    for page in out.tiers:
        for sp in top_codes(page["ids"], 8):
            page["related"].append((sp["path"], sp["h1"]))

    # de-dupe related, drop self links
    for page in out.sets + out.events + out.tiers:
        seen = set()
        rel = []
        for href, label in page["related"]:
            if href == page["path"] or href in seen:
                continue
            seen.add(href)
            rel.append((href, label))
        page["related"] = rel[:12]

    # ---- hubs -----------------------------------------------------------
    out.hubs.append(_hub_sets(out.sets, used_titles, used_descs))
    out.hubs.append(_hub_events(out.events, used_titles, used_descs))
    out.hubs.append(_hub_tiers(out.tiers, used_titles, used_descs))
    for hub in out.hubs:
        out.by_path[hub["path"]] = hub
    return out


def _hub_sets(sets, used_titles, used_descs):
    n = len(sets)
    cards_n = len({i for p in sets for i in p["ids"]})
    fams = join_list(f"{sum(1 for p in sets if p['group']==f)} {FAMILY[f].lower()}" for f in FAMILY_ORDER)
    intro = fit_words([
        f"Every booster, extra booster, premium booster and starter deck that the cards on Log Pose are numbered in or pulled from, {n} set pages in all.",
        f"The split is {fams}. A set page lists the prize cards, promos and chase pulls tracked for that code, with the documented population where one was published.",
        "It is not a checklist of every card in the booster. A prize card keeps the number of the card it reprints, so an OP-09 number awarded at a 2025 Regional is on the OP-09 page.",
        f"Together the set pages link {cards_n} card pages.",
        methodology(),
    ])
    title = choose_title([
        "One Piece TCG sets and prize cards",
        "Set pages: prize cards and populations",
    ], used_titles)
    desc = choose_desc([
        f"{n} set pages for the ONE PIECE Card Game cards tracked on Log Pose: boosters, extra boosters, premium boosters and starter decks, each with its prize and chase cards and documented populations.",
    ], used_descs)
    page = _page("hub", "sets", "/sets/", "Sets", title, desc, intro, [], [
        ("Log Pose", "/"), ("Sets", None),
    ])
    page["children"] = sets
    return page


def _hub_events(events, used_titles, used_descs):
    n = len(events)
    by = defaultdict(int)
    for p in events:
        by[p["group"]] += 1
    bits = [f"{by[g]} {GROUP_LABEL[g].lower()}" for g in GROUP_ORDER if by[g]]
    intro = fit_words([
        f"Events and prize sets on Log Pose, {n} pages. People search by the tournament or the product a card was handed out in, and each page below is one of those.",
        f"The index is {join_list(bits)}.",
        "A prize card set is the pack Bandai awarded as one unit, such as a Regional finalist set. A wave or cup page lists every card from that run, including the individual prizes and the sets. One-card store events and one-card release events are grouped onto two pages so they are not thin copies of a single card.",
        "Booster names such as Romance Dawn stay on the set pages. A product name that is only a booster is not repeated here.",
        methodology(),
    ])
    title = choose_title([
        "One Piece TCG events and prize sets",
        "Event and prize set populations",
    ], used_titles)
    desc = choose_desc([
        f"{n} event and prize-set pages: Treasure Cups, Regionals, Finals, World Finals, special tournaments, store events and promo releases, each listing its cards and documented populations.",
    ], used_descs)
    page = _page("hub", "events", "/events/", "Events and prize sets", title, desc, intro, [], [
        ("Log Pose", "/"), ("Events", None),
    ])
    page["children"] = events
    return page


def _hub_tiers(tiers, used_titles, used_descs):
    n = len(tiers)
    top = join_list(f"{p['label']} ({len(p['ids'])})" for p in tiers[:5])
    intro = fit_words([
        f"Prize tiers and chase rarities on Log Pose, {n} pages. A tier is the rarity or placement stored on the card, such as Champion, Finalist, Top 16 or SP Card.",
        f"The largest are {top}.",
        f"Each page lists every card filed under that label, rarest first. Tiers with fewer than {TIER_MIN} cards do not get their own URL; those cards stay on their card, set and event pages.",
        "Promo product names that share the same field, such as an anniversary set, are event pages rather than tiers.",
        methodology(),
    ])
    title = choose_title([
        "One Piece TCG prize tiers and rarities",
        "Prize tiers and populations",
    ], used_titles)
    desc = choose_desc([
        f"{n} tier pages for ONE PIECE Card Game prize and chase cards, from Champion and Finalist to SP Card and Manga Rare, each with every card and its documented population.",
    ], used_descs)
    page = _page("hub", "tiers", "/tiers/", "Tiers", title, desc, intro, [], [
        ("Log Pose", "/"), ("Tiers", None),
    ])
    page["children"] = tiers
    return page


def _crumb(crumbs):
    bits = ['<nav class="crumb">']
    for i, (name, href) in enumerate(crumbs):
        if i:
            bits.append(" › ")
        if href and i < len(crumbs) - 1:
            bits.append(f'<a href="{esc(href)}">{esc(name)}</a>')
        else:
            bits.append(esc(name))
    bits.append("</nav>")
    return "".join(bits)


def _table(ids, cards, card_slug):
    rows = ['<table class="sortable"><caption>Rarest first. Choose a column heading to sort.</caption>',
            "<thead><tr><th>Card</th><th>Number</th><th>Tier</th><th class='n'>Population</th></tr></thead><tbody>"]
    for i in ids:
        c = cards[i]
        rows.append(
            "<tr>"
            f"<td><a href='/card/{esc(card_slug[i])}/'>{esc(c.get('name'))}</a></td>"
            f"<td>{esc(c.get('number'))}</td>"
            f"<td>{esc(c.get('place') or '')}</td>"
            f"<td class='n'>{esc(c.get('pop') or '')}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    rows.append(
        '<p class="note">Populations are documented print runs from Bandai\'s event and product pages, '
        'not a PSA or Beckett census. <a href="/questions/">How a count is built</a>.</p>'
    )
    return "\n".join(rows)


def _related(page):
    if not page.get("related"):
        return ""
    links = " · ".join(f'<a href="{esc(h)}">{esc(l)}</a>' for h, l in page["related"])
    return f"<h2>Related</h2><p>{links}</p>"


SORT_SCRIPT = """<script>
(function () {
  var table = document.querySelector("table.sortable");
  if (!table || !table.tHead) return;
  var ths = table.tHead.rows[0].cells;
  function val(td, idx) {
    var t = td.textContent || "";
    if (idx === 3) {
      var m = t.match(/[0-9][0-9,]*/);
      if (!m) return [1, 0];
      return [0, parseInt(m[0].replace(/,/g, ""), 10)];
    }
    return [0, t.toLowerCase()];
  }
  function hook(idx) {
    ths[idx].tabIndex = 0;
    ths[idx].style.cursor = "pointer";
    ths[idx].title = "Sort by this column";
    function sort() {
      var asc = ths[idx].getAttribute("aria-sort") !== "ascending";
      var rows = Array.prototype.slice.call(table.tBodies[0].rows);
      rows.sort(function (a, b) {
        var va = val(a.cells[idx], idx), vb = val(b.cells[idx], idx);
        if (va[0] !== vb[0]) return va[0] - vb[0];
        if (va[1] < vb[1]) return asc ? -1 : 1;
        if (va[1] > vb[1]) return asc ? 1 : -1;
        return 0;
      });
      rows.forEach(function (r) { table.tBodies[0].appendChild(r); });
      for (var j = 0; j < ths.length; j++) ths[j].removeAttribute("aria-sort");
      ths[idx].setAttribute("aria-sort", asc ? "ascending" : "descending");
    }
    ths[idx].addEventListener("click", sort);
    ths[idx].addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); }
    });
  }
  for (var i = 0; i < ths.length; i++) hook(i);
})();
</script>"""


def _jsonld(page):
    crumbs = []
    for pos, (name, href) in enumerate(page["crumbs"], 1):
        item = {"@type": "ListItem", "position": pos, "name": name}
        if href:
            item["item"] = SITE + href
        elif page["path"]:
            item["item"] = SITE + page["path"]
        crumbs.append(item)
    data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": page["h1"],
        "description": page["desc"],
        "url": SITE + page["path"],
        "isPartOf": {"@type": "WebSite", "name": "Log Pose", "url": SITE + "/"},
        "breadcrumb": {"@type": "BreadcrumbList", "itemListElement": crumbs},
    }
    if page["kind"] == "hub":
        elements = []
        for pos, child in enumerate(page.get("children") or [], 1):
            elements.append({"@type": "ListItem", "position": pos, "name": child["h1"], "url": SITE + child["path"]})
        data["mainEntity"] = {"@type": "ItemList", "numberOfItems": len(elements), "itemListElement": elements}
    else:
        elements = []
        # filled by render once slugs are applied; placeholder replaced there
        data["mainEntity"] = {"@type": "ItemList", "numberOfItems": len(page["ids"]), "itemListElement": elements}
    return data


def _body(page, cards, card_slug):
    parts = [_crumb(page["crumbs"]), f"<h1>{esc(page['h1'])}</h1>", f"<p>{esc(page['intro'])}</p>"]
    if page["kind"] == "hub":
        if page["group"] == "sets":
            for fam in FAMILY_ORDER:
                kids = [p for p in page["children"] if p["group"] == fam]
                if not kids:
                    continue
                parts.append(f"<h2>{esc(FAMILY[fam])} ({len(kids)})</h2>")
                parts.append("<ul>")
                for child in kids:
                    name = f" — {child['name']}" if child.get("name") else ""
                    parts.append(
                        f'<li><a href="{esc(child["path"])}">{esc(child["code"])}{esc(name)}</a>'
                        f' — {len(child["ids"])} {"card" if len(child["ids"]) == 1 else "cards"}</li>'
                    )
                parts.append("</ul>")
        elif page["group"] == "events":
            for group in GROUP_ORDER:
                kids = [p for p in page["children"] if p["group"] == group]
                if not kids:
                    continue
                parts.append(f"<h2>{esc(GROUP_LABEL[group])} ({len(kids)})</h2><ul>")
                for child in kids:
                    parts.append(
                        f'<li><a href="{esc(child["path"])}">{esc(child["h1"])}</a>'
                        f' — {len(child["ids"])} {"card" if len(child["ids"]) == 1 else "cards"}</li>'
                    )
                parts.append("</ul>")
        else:
            parts.append("<ul>")
            for child in page["children"]:
                parts.append(
                    f'<li><a href="{esc(child["path"])}">{esc(child["h1"])}</a>'
                    f' — {len(child["ids"])} {"card" if len(child["ids"]) == 1 else "cards"}</li>'
                )
            parts.append("</ul>")
        parts.append('<p><a class="cta" href="/cards/">Every card and its population →</a></p>')
    else:
        n, nd, _ = count_line(page["ids"], cards)
        card_word = "card" if n == 1 else "cards"
        parts.append(f'<p class="sub">{n} {card_word} · {nd} with a documented population · rarest first</p>')
        parts.append(_table(page["ids"], cards, card_slug))
        parts.append(_related(page))
    return "\n".join(parts)


def _itemlist(page, cards, card_slug):
    elements = []
    for pos, i in enumerate(page["ids"], 1):
        c = cards[i]
        elements.append({
            "@type": "ListItem", "position": pos,
            "name": f"{c.get('name')} {c.get('number')}".strip(),
            "url": f"{SITE}/card/{card_slug[i]}/",
        })
    return elements


def render(plan_obj, out_dir, cards, card_slug):
    import build_pages as bp
    urls = []
    pages = plan_obj.hubs + plan_obj.sets + plan_obj.events + plan_obj.tiers
    for page in pages:
        data = _jsonld(page)
        if page["kind"] != "hub":
            data["mainEntity"]["itemListElement"] = _itemlist(page, cards, card_slug)
        body = _body(page, cards, card_slug)
        if page["kind"] != "hub":
            body += "\n" + SORT_SCRIPT
        cover = ""
        for i in page.get("ids") or []:
            if cards[i].get("image"):
                cover = cards[i]["image"]
                break
        ogimage = (SITE + "/" + cover) if cover else SITE + "/og.png"
        extra = {}
        if cover:
            sheet = any(cards[i].get("image") == cover and cards[i].get("kind") == "sheet"
                        for i in page.get("ids") or [])
            extra["ogextra"] = bp.og_extra(page["title"], 800, 1000) if sheet else bp.og_extra(page["title"], 630, 880)
        bp.page(page["path"], out_dir,
                title=esc(page["title"]), desc=esc(page["desc"]), canon=SITE + page["path"],
                ogtitle=esc(page["title"]), ogtype="website",
                ogimage=ogimage,
                jsonld=bp.ld(data), body=body, **extra)
        pri = "0.9" if page["kind"] == "hub" else "0.8"
        freq = "weekly" if page["kind"] == "hub" else "monthly"
        urls.append((SITE + page["path"], freq, pri))
    return urls


def card_anchors(plan_obj, cid):
    return list(plan_obj.links.get(cid) or [])


def anchor_html(anchors):
    return " · ".join(f'<a href="{esc(h)}">{esc(l)}</a>' for h, l in anchors)


_MORE = re.compile(r"(<h2>More in Log Pose</h2>\s*<p>)(.*?)(</p>)", re.S)
_CATALOG_ANCHOR = re.compile(r"(?:\s*·\s*)?<a href=\"/(?:set|event|tier)/[^\"]*\">.*?</a>")


def patch_card_html(text, anchors):
    if not anchors:
        return text, False

    def repl(m):
        inner = _CATALOG_ANCHOR.sub("", m.group(2)).strip()
        extra = anchor_html(anchors)
        joiner = " · " if inner else ""
        return m.group(1) + inner + joiner + extra + m.group(3)

    new, n = _MORE.subn(repl, text, count=1)
    return new, n == 1


def patch_footer(text):
    if "/sets/" in text and "/events/" in text and "/tiers/" in text and "All cards" in text:
        return text, False
    if OLD_FOOT not in text:
        return text, False
    return text.replace(OLD_FOOT, NEW_FOOT), True


def patch_cards_index(text):
    if 'href="/sets/"' in text and "event or prize set" in text:
        return text, False
    needle = "official sources behind it.</p>"
    if needle not in text:
        return text, False
    return text.replace(needle, needle + "\n<p>" + CARDS_INDEX_LINE + "</p>", 1), True


def link_mainsets(text, plan_obj):
    by_code = {p["code"]: p["path"] for p in plan_obj.sets}

    def repl(m):
        inner = m.group(1)
        if "<a " in inner:
            return m.group(0)
        combo = re.match(r"^(OP)(\d+)-(EB)(\d+)\b", inner)
        if combo:
            a = f"OP-{int(combo.group(2)):02d}"
            b = f"EB-{int(combo.group(4)):02d}"
            linked = inner
            if a in by_code:
                linked = linked.replace(a, f'<a href="{by_code[a]}">{a}</a>', 1)
            if b in by_code:
                linked = linked.replace(b, f'<a href="{by_code[b]}">{b}</a>', 1)
            return "<h2>" + linked + "</h2>"
        single = re.match(r"^((?:OP|EB|PRB)-\d+)\b", inner)
        if single and single.group(1) in by_code:
            href = by_code[single.group(1)]
            return f'<h2><a href="{href}">{inner}</a></h2>'
        return m.group(0)

    new = re.sub(r"<h2>(.*?)</h2>", repl, text)
    note = '<p>Each set also has its own page of the prize, promo and chase cards tracked for it. <a href="/sets/">All sets</a>.</p>'
    if note not in new and "<h1>Main Sets</h1>" in new:
        new = new.replace("<h1>Main Sets</h1>", "<h1>Main Sets</h1>\n" + note, 1)
    return new, new != text


def existing_titles(out_dir):
    found = set()
    for path in Path(out_dir).rglob("index.html"):
        rel = str(path.relative_to(out_dir)).replace("\\", "/")
        if rel.startswith(("set/", "event/", "tier/", "sets/", "events/", "tiers/")):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"<title>(.*?)</title>", text)
        if m:
            found.add(html.unescape(m.group(1)))
    return found


def load_card_files(out_dir):
    """Map card id -> slug and the population printed on the card page."""
    out = {}
    root = Path(out_dir) / "card"
    for path in root.glob("*/index.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'href="/#([^"]+)"', text)
        if not m or "/" not in m.group(1):
            continue
        cid = m.group(1).split("/", 1)[1]
        pop_m = re.search(r'class="pop">([^<]*)', text)
        pop = html.unescape(pop_m.group(1)).strip() if pop_m else ""
        out[cid] = {"slug": path.parent.name, "pop": pop}
    return out


def validate(plan_obj):
    problems = []
    titles = []
    descs = []
    for page in plan_obj.hubs + plan_obj.sets + plan_obj.events + plan_obj.tiers:
        titles.append(page["title"])
        descs.append(page["desc"])
        if not (1 <= len(page["title"]) <= 60):
            problems.append(f"title length {len(page['title'])}: {page['title']}")
        if not (1 <= len(page["desc"]) <= 155):
            problems.append(f"desc length {len(page['desc'])}: {page['desc']}")
        if "…" in page["title"] or "…" in page["desc"] or "..." in page["title"]:
            problems.append(f"ellipsis: {page['path']}")
        n = words(page["intro"])
        if page["kind"] != "hub" and not (80 <= n <= 120):
            problems.append(f"intro {n} words: {page['path']}")
        if page["kind"] == "hub" and n < 70:
            problems.append(f"hub intro {n} words: {page['path']}")
        if not page["h1"]:
            problems.append(f"missing h1: {page['path']}")
    if len(titles) != len(set(titles)):
        seen = set()
        for t in titles:
            if t in seen:
                problems.append(f"duplicate title: {t}")
            seen.add(t)
    if len(descs) != len(set(descs)):
        seen = set()
        for d in descs:
            if d in seen:
                problems.append(f"duplicate desc: {d}")
            seen.add(d)
    return problems


def check_links(out_dir):
    broken = []
    href_re = re.compile(r'href="([^"]+)"')
    root = Path(out_dir)
    for path in root.rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for href in href_re.findall(text):
            if href.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            if href.startswith("#") or href.startswith("/#"):
                continue
            bare = href.split("#", 1)[0].split("?", 1)[0]
            if not bare.startswith("/"):
                continue
            if bare == "/":
                ok = (root / "index.html").is_file()
            elif bare.endswith("/"):
                ok = (root / bare.strip("/") / "index.html").is_file()
            else:
                ok = (root / bare.lstrip("/")).is_file()
            if not ok:
                broken.append((str(path.relative_to(root)), href))
    return broken


def counts(plan_obj):
    ev = defaultdict(int)
    for page in plan_obj.events:
        ev[page["group"]] += 1
    fam = defaultdict(int)
    for page in plan_obj.sets:
        fam[page["group"]] += 1
    return {
        "sets": len(plan_obj.sets),
        "set_families": dict(fam),
        "events": len(plan_obj.events),
        "event_groups": dict(ev),
        "tiers": len(plan_obj.tiers),
        "hubs": len(plan_obj.hubs),
    }


def apply_catalog(catalog_path, out_dir):
    data = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    cards = data["cards"]
    files = load_card_files(out_dir)
    card_slug = {}
    missing = []
    for cid, card in cards.items():
        if card.get("kind") == "sheet":
            continue
        info = files.get(cid)
        if not info:
            missing.append(cid)
            continue
        card_slug[cid] = info["slug"]
        if info["pop"]:
            card["pop"] = info["pop"]
    built = plan(
        cards, card_slug, data.get("sections") or {}, data.get("sets") or [],
        data.get("msRelease") or MS_RELEASE, data.get("msTier") or MS_TIER,
        existing_titles(out_dir),
    )
    problems = validate(built)
    urls = render(built, out_dir, cards, card_slug)

    patched = missed = 0
    root = Path(out_dir)
    for cid, slug in card_slug.items():
        path = root / "card" / slug / "index.html"
        text = path.read_text(encoding="utf-8")
        new, ok = patch_card_html(text, card_anchors(built, cid))
        if not ok and card_anchors(built, cid):
            missed += 1
        elif new != text:
            path.write_text(new, encoding="utf-8")
            patched += 1

    foot = 0
    for path in root.rglob("index.html"):
        text = path.read_text(encoding="utf-8")
        new, changed = patch_footer(text)
        if changed:
            path.write_text(new, encoding="utf-8")
            foot += 1

    cards_index = root / "cards" / "index.html"
    if cards_index.is_file():
        text = cards_index.read_text(encoding="utf-8")
        new, changed = patch_cards_index(text)
        if changed:
            cards_index.write_text(new, encoding="utf-8")

    mainsets = root / "s" / "main-sets" / "index.html"
    if mainsets.is_file():
        text = mainsets.read_text(encoding="utf-8")
        new, changed = link_mainsets(text, built)
        if changed:
            mainsets.write_text(new, encoding="utf-8")

    sitemap = root / "sitemap.xml"
    added = append_sitemap(sitemap, urls)
    broken = check_links(out_dir)
    report = counts(built)
    report.update({
        "card_links_patched": patched,
        "card_links_missed": missed,
        "footers_patched": foot,
        "sitemap_added": added,
        "missing_card_files": missing,
        "problems": problems,
        "broken_links": broken[:30],
        "broken_count": len(broken),
        "patterns": {
            "sets": "/set/{code}/  e.g. /set/op13/ /set/eb02/ /set/prb02/ /set/st01/",
            "events": "/event/{slug}/",
            "tiers": "/tier/{slug}/",
            "hubs": "/sets/  /events/  /tiers/",
        },
    })
    return built, report


def append_sitemap(path, urls):
    """Add missing URLs, and give every entry a <lastmod>, matching build_pages.py."""
    import datetime
    lm = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    text = Path(path).read_text(encoding="utf-8")
    if "<<<<<<<" in text or ">>>>>>>" in text:
        raise SystemExit("sitemap still has conflict markers")

    def stamp(match):
        block = match.group(0)
        if "<lastmod>" in block:
            return block
        return block.replace("<changefreq>", f"<lastmod>{lm}</lastmod><changefreq>", 1)

    stamped = re.sub(r"<url>.*?</url>", stamp, text, flags=re.S)
    have = set(re.findall(r"<loc>([^<]+)</loc>", stamped))
    lines = []
    for loc, freq, pri in urls:
        if loc in have:
            continue
        lines.append(
            f"  <url><loc>{loc}</loc><lastmod>{lm}</lastmod>"
            f"<changefreq>{freq}</changefreq><priority>{pri}</priority></url>"
        )
    if lines:
        if "</urlset>" not in stamped:
            raise SystemExit("sitemap has no urlset close tag")
        stamped = stamped.replace("</urlset>", "\n".join(lines) + "\n</urlset>", 1)
    if not stamped.endswith("\n"):
        stamped += "\n"
    changed = stamped != text
    if changed:
        Path(path).write_text(stamped, encoding="utf-8")
    return len(lines)


def plan_from_site(cards, sections, card_slug, existing=None):
    """Used by a full build_pages run, when the catalog JSON is already in memory."""
    prize = []
    grouped = defaultdict(list)
    for cid, card in cards.items():
        if cid not in card_slug or card.get("kind") == "sheet":
            continue
        fs = card.get("fromSet")
        if fs:
            grouped[fs].append(cid)
    for name, ids in grouped.items():
        sample = cards[ids[0]]
        prize.append({
            "name": name, "members": ids, "season": season_of(sample),
            "distributed": sample.get("distributed") or "", "place": sample.get("place") or "",
        })
    return plan(cards, card_slug, sections, prize, MS_RELEASE, MS_TIER, existing or [])
