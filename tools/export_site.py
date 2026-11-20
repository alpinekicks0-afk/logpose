#!/usr/bin/env python3
"""Turn the home-page catalog into the JSON tools/build_pages.py reads.

The catalog lives in public/assets/data.*.js (JavaScript, not JSON). This
evaluates it, fills in the population and tab the app computes at runtime,
and writes site.json plus chars.json.

Usage: python3 tools/export_site.py <data.js> <out_dir> [index.html]
"""
import json
import os
import re
import subprocess
import sys
import tempfile

NODE = r"""
const fs = require("fs");
const vm = require("vm");
const dataPath = process.argv[2];
const indexPath = process.argv[3];
const outDir = process.argv[4];
const code = fs.readFileSync(dataPath, "utf8");
const index = fs.readFileSync(indexPath, "utf8");
const spot = index.match(/^const SPOTLIGHT = (\{.*\});$/m);
const tabs = index.match(/^const TAB_NAMES = (\{.*?\});/m);
if (!spot) throw new Error("SPOTLIGHT not found");
if (!tabs) throw new Error("TAB_NAMES not found");
const ctx = {};
vm.createContext(ctx);
vm.runInContext(code + "\nthis.SPOTLIGHT = " + spot[1] + ";\nthis.TAB_NAMES = " + tabs[1] + ";", ctx);

const TODAY = new Date().toISOString().slice(0, 10);
function played(ev){ return ev.date <= TODAY; }
function totals(c){
  let all=0, toDate=0, events=0, eventsToDate=0, ongoing=false, unknown=false;
  for (const d of (c.dist || [])){
    const s = ctx.SCHEDULES[d.schedule];
    if (!s) continue;
    if (s.storeLevel){ unknown = true; continue; }
    const n = s.events.length || s.count || 0;
    const m = s.events.length ? s.events.filter(played).length : (s.count && s.ended ? s.count : 0);
    all += n * d.perEvent; toDate += m * d.perEvent; events += n; eventsToDate += m;
    if (s.ongoing) ongoing = true;
  }
  if (c.uncountable) unknown = true;
  let packsAll=0, packsToDate=0;
  if (c.packs){
    packsAll = all; packsToDate = toDate;
    const f = (c.cardsPerPack || 1) / (c.types || 1);
    all = Math.floor(all * f); toDate = Math.floor(toDate * f);
  }
  return {all, toDate, events, eventsToDate, ongoing, unknown, packsAll, packsToDate};
}
function popKey(c){
  if (!c.dist && !c.popOverride) return null;
  if (c.popOverride){
    const m = String(c.popOverride).match(/[\d,]+/);
    if (m){ const n = parseInt(m[0].replace(/,/g, ""), 10); if (!isNaN(n)) return n; }
  }
  const t = totals(c);
  if (c.uncountable || (t.unknown && !t.events)) return null;
  return t.ongoing ? t.toDate : t.all;
}
function popText(c){
  if (c.popOverride) return c.popOverride;
  if (!c.dist) return "unpublished";
  const t = totals(c);
  const pre = c.packs ? "≈" : "";
  if (c.uncountable || (t.unknown && !t.events)) return "unpublished";
  const n = t.ongoing ? t.toDate : t.all;
  return pre + n.toLocaleString("en-US") + "+";
}
const tabOf = {};
for (const [tab, s] of Object.entries(ctx.SECTIONS)){
  if (s.dynamic) continue;
  for (const cat of s.categories){
    for (const id of (cat.cards || [])){
      if (ctx.CARDS[id] && !tabOf[id]) tabOf[id] = tab;
    }
  }
}
const cards = {};
for (const [id, c] of Object.entries(ctx.CARDS)){
  const copy = Object.assign({}, c);
  copy.tab = tabOf[id] || c.tab || "featured";
  copy.pop = popText(c);
  const pk = popKey(c);
  if (pk !== null && pk !== undefined) copy.popKey = pk;
  cards[id] = copy;
}
const MS_RANK = ["Crew Alt-Art","Oda Signature","Special Manga","Manga Leader","Manga Rare","Event Manga","Gold SSP","Silver SSP","Demon Pack SSP","Wanted SP","Special Alt-Art","SP Card","Anime 25th parallel","Chinese TR","French TR","Japanese TR","Treasure Rare"];
function msRank(c){ const i = MS_RANK.indexOf(c.place); return i < 0 ? MS_RANK.length : i; }
function pk(id){ const v = cards[id].popKey; return v === undefined ? Infinity : v; }
const chars = [];
const dyn = ctx.SECTIONS.characters;
if (dyn){
  for (const cat of dyn.categories){
    const re = new RegExp(cat.match, "i");
    const ex = cat.exclude ? new RegExp(cat.exclude, "i") : null;
    const ids = Object.keys(cards).filter(id => !id.startsWith("ms-") && re.test(cards[id].name) && !(ex && ex.test(cards[id].name)) && pk(id) !== Infinity);
    ids.sort((a, b) => pk(a) - pk(b) || cards[a].name.localeCompare(cards[b].name));
    const seen = new Set(ids);
    const rest = Object.keys(cards).filter(id => !seen.has(id) && re.test(cards[id].name) && cards[id].kind !== "sheet" && !(ex && ex.test(cards[id].name)));
    const msRest = rest.filter(id => id.startsWith("ms-"));
    const prRest = rest.filter(id => !id.startsWith("ms-"));
    msRest.sort((a, b) => msRank(cards[a]) - msRank(cards[b]) || String(cards[a].number).localeCompare(String(cards[b].number)));
    prRest.sort((a, b) => String(cards[a].place).localeCompare(String(cards[b].place)) || String(cards[a].number).localeCompare(String(cards[b].number)));
    chars.push({ name: cat.name, blurb: cat.blurb || "", ranked: ids, extra: msRest.concat(prRest) });
  }
}
const site = {
  cards, secs: ctx.SECTIONS, sch: ctx.SCHEDULES, src: ctx.SRC,
  tabNames: ctx.TAB_NAMES, spotlight: ctx.SPOTLIGHT,
};
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(outDir + "/site.json", JSON.stringify(site));
fs.writeFileSync(outDir + "/chars.json", JSON.stringify(chars));
console.log("cards", Object.keys(cards).length);
console.log("chars", chars.length);
console.log("with tab", Object.values(cards).filter(c => c.tab && c.tab !== "featured").length);
"""


def main(data_js, out_dir, index_html):
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(NODE)
        script = f.name
    try:
        subprocess.check_call(["node", script, data_js, index_html, out_dir])
    finally:
        os.unlink(script)


if __name__ == "__main__":
    data = sys.argv[1]
    out = sys.argv[2]
    index = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(data), "..", "index.html")
    main(os.path.abspath(data), os.path.abspath(out), os.path.abspath(index))
