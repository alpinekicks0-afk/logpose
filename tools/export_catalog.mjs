// Reads the data block in public/index.html and writes the catalog
// tools/build_pages.py uses for set, event and tier pages.
// Usage: node tools/export_catalog.mjs <index.html> <out.json>
import fs from "fs";

const [srcPath, outPath] = process.argv.slice(2);
const html = fs.readFileSync(srcPath, "utf8");
const start = html.indexOf("const SRC = {");
const end = html.indexOf("const $ = ");
if (start < 0 || end < 0) throw new Error("could not find the data block in " + srcPath);

const release = html.slice(html.indexOf("const MS_RELEASE = "), html.indexOf("function popText"));
const tier = html.slice(html.indexOf("const MS_TIER = "), html.indexOf("const MS_RELEASE = "));
if (!release.startsWith("const MS_RELEASE") || !tier.startsWith("const MS_TIER")) {
  throw new Error("could not find MS_RELEASE / MS_TIER");
}

const src = html.slice(start, end) + `
const TODAY = new Date().toISOString().slice(0,10);
function played(ev){ return ev.date <= TODAY; }
function totals(c){
  let all=0, toDate=0, events=0, eventsToDate=0, ongoing=false, unknown=false, perEventUnknown=0;
  for (const d of (c.dist||[])) {
    const s = SCHEDULES[d.schedule];
    if (!s) { unknown = true; continue; }
    if (s.storeLevel) { unknown = true; perEventUnknown += d.perEvent; continue; }
    const n = s.events.length || s.count || 0;
    const m = s.events.length ? s.events.filter(played).length : (s.count && s.ended ? s.count : 0);
    all += n * d.perEvent; toDate += m * d.perEvent; events += n; eventsToDate += m;
    if (s.ongoing) ongoing = true;
  }
  if (c.uncountable) unknown = true;
  if (c.packs) {
    const f = (c.cardsPerPack || 1) / (c.types || 1);
    all = Math.floor(all * f); toDate = Math.floor(toDate * f);
  }
  return {all, toDate, events, ongoing, unknown};
}
function popText(c) {
  if (c.popOverride) return c.popOverride;
  const t = totals(c);
  const pre = c.packs ? "≈" : "";
  if (c.uncountable || (t.unknown && !t.events)) return "unpublished";
  return t.ongoing ? pre + t.toDate.toLocaleString("en-US") + "+" : pre + t.all.toLocaleString("en-US") + "+";
}
${tier}
${release}
const tabOf = {};
for (const [tab, sec] of Object.entries(SECTIONS)) {
  if (sec.dynamic) continue;
  for (const cat of sec.categories || []) {
    for (const id of cat.cards || []) if (!tabOf[id]) tabOf[id] = tab;
  }
}
const cards = {};
for (const [id, c] of Object.entries(CARDS)) {
  cards[id] = {
    name: c.name, number: c.number, place: c.place || "", set: c.set || "",
    fromSet: c.fromSet || "", mainset: c.mainset || "", kind: c.kind || "",
    variant: c.variant || "", distributed: c.distributed || "", language: c.language || "",
    image: c.image || "", pop: popText(c), tab: tabOf[id] || ""
  };
}
const sets = SETS.map(s => ({
  id: s.id, name: s.name, tab: s.tab, place: s.place || "", season: s.season || "",
  distributed: s.distributed || "",
  members: s.members.map(m => s.id + "-" + m.number.toLowerCase())
}));
const sections = {};
for (const [tab, sec] of Object.entries(SECTIONS)) {
  if (sec.dynamic) continue;
  sections[tab] = {
    title: sec.title, blurb: sec.blurb || "",
    categories: (sec.categories || []).map(cat => ({
      name: cat.name, group: cat.group || "", blurb: cat.blurb || "",
      cards: (cat.cards || []).filter(id => CARDS[id])
    }))
  };
}
return {cards, sets, sections, msRelease: MS_RELEASE, msTier: MS_TIER};
`;

const data = new Function(src)();
fs.writeFileSync(outPath, JSON.stringify(data));
console.log("cards", Object.keys(data.cards).length, "sets", data.sets.length, "sections", Object.keys(data.sections).length);
