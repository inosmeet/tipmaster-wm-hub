#!/usr/bin/env python3
"""
build.py - generates a static German "WM 2026" hub page for tipmaster.net
from TipMaster's OWN guide sitemaps (de/ratgeber, en/guide, en-us/guide).

Why this exists:
  tipmaster.de/world-cup/ currently 301 -> 308 -> 308 redirects onto the
  English "Daily" page, which is served with x-robots-tag: noindex. The ~55
  World-Cup-2026 articles that DO exist are scattered across three language
  sections, are still written in the future tense, and the German ones were
  last modified on 2026-07-05, two weeks before the final. This page gives
  that content a crawlable home, states the result, and points to what's next.

Usage:
  python3 build.py             # fetch sitemaps + pages, write index.html and data/wm-hub.json
  python3 build.py --offline   # re-render index.html from data/wm-hub.json (no network)
Env:
  SITE_URL   canonical URL of the generated page (used for canonical + hreflang de)
"""
import html
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_URL = os.environ.get("SITE_URL", "https://example.github.io/tipmaster-wm-hub/")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 tipmaster-wm-hub-build/1.0"

SITEMAPS = {
    "de": "https://tipmaster.net/de/ratgeber/sitemap.xml",
    "en": "https://tipmaster.net/en/guide/sitemap.xml",
    "en-us": "https://tipmaster.net/en-us/guide/sitemap.xml",
}

# What counts as a World-Cup-2026 article
WC_PATTERN = re.compile(r"(wm-2026|wm-tippspiel|world-cup|weltmeister|fantamondiale)", re.I)
# Deliberately excluded from a German-market hub: prediction-market referral pages.
# Kalshi/Polymarket are not licensed in Germany and GlueStV restricts betting advertising;
# TipMaster's own DE copy says "Tippen heisst Prognose, nicht Geldeinsatz".
EXCLUDE = re.compile(r"(kalshi|polymarket|prediction-markets|referral|invite-code)", re.I)

# Order matters: first match wins.
SECTIONS = [
    ("finale", "Finale", r"wm-2026-finale-tippen|world-cup-2026-final-pick"),
    ("halbfinale", "Halbfinale", r"halbfinale|semifinal"),
    ("viertelfinale", "Viertelfinale", r"viertelfinale|quarterfinal"),
    ("achtelfinale", "Achtelfinale", r"achtelfinale|round-of-16"),
    ("sechzehntelfinale", "Sechzehntelfinale (Runde der 32)", r"sechzehntelfinale|round-of-32"),
    ("turnierbaum", "Turnierbaum, Spielplan & Bracket", r"turnierbaum|bracket|spielplan|schedule|pool"),
    ("vergleiche", "Andere WM-Spiele im Vergleich", r"kicktipp|comunio|kickbase|kicker|fantamondiale|best-|football-manager|videospiele|video-games|fantasy-manager"),
    ("tippspiel", "Tippspiel, Prognosen & Strategie", r"tippspiel|tippen|prediction|tipps"),
    ("hintergrund", "Regeln & Hintergrund", r"regeln|rules|host-cities|collectibles|panini"),
]
LANG_LABEL = {"de": "DE", "en": "EN", "en-us": "US"}
LANG_ORDER = {"de": 0, "en": 1, "en-us": 2}

FINAL = {
    "date": "2026-07-19",
    "date_de": "19. Juli 2026",
    "venue": "MetLife Stadium, New Jersey",
    "home": "Spanien",
    "away": "Argentinien",
    "score": "1:0 n.V.",
    "scorer": "Ferran Torres (106.)",
    "source": "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/final",
}
NEXT = {
    "name": "FIFA Frauen-WM 2027",
    "host": "Brasilien",
    "start": "2027-06-24",
    "start_de": "24. Juni 2027",
    "end_de": "25. Juli 2027",
    "venue": "Maracanã, Rio de Janeiro",
    "source": "https://www.fifa.com/en/tournaments/womens/womensworldcup/brazil-2027",
}


def get(url, timeout=15):
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def slug_title(url):
    slug = url.rstrip("/").split("/")[-1]
    return slug.replace("-", " ").capitalize()


def parse_sitemap(lang, xml):
    items = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>(.*?)</loc>", block)
        if not loc:
            continue
        lastmod = re.search(r"<lastmod>(.*?)</lastmod>", block)
        items.append({"url": html.unescape(loc.group(1)).strip(), "lang": lang,
                      "lastmod": lastmod.group(1) if lastmod else None})
    return items


def classify(url):
    for key, label, pattern in SECTIONS:
        if re.search(pattern, url, re.I):
            return key
    return "hintergrund"


def enrich(item):
    """Fetch the article once to get its real title, description and dates."""
    try:
        page = get(item["url"])
        m = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
        title = html.unescape(m.group(1)).strip() if m else ""
        title = re.sub(r"\s*[|–—-]\s*Tip[Mm]aster.*$", "", title).strip()
        dm = re.search(r'"dateModified":"([^"]+)"', page)
        dp = re.search(r'"datePublished":"([^"]+)"', page)
        desc = re.search(r'<meta name="description" content="([^"]*)"', page)
        item.update({
            "title": title or slug_title(item["url"]),
            "description": html.unescape(desc.group(1)) if desc else "",
            "date_modified": dm.group(1) if dm else item.get("lastmod"),
            "date_published": dp.group(1) if dp else None,
            "fetched": True,
        })
    except Exception as exc:  # keep going: a broken article must not break the hub
        item.update({"title": slug_title(item["url"]), "description": "",
                     "date_modified": item.get("lastmod"), "date_published": None,
                     "fetched": False, "error": str(exc)[:100]})
    return item


def collect():
    scanned, wc, excluded = [], [], []
    for lang, sm in SITEMAPS.items():
        try:
            xml = get(sm)
        except Exception as exc:
            print(f"[warn] sitemap {sm} failed: {exc}", file=sys.stderr)
            continue
        items = parse_sitemap(lang, xml)
        scanned.extend(items)
        for it in items:
            if not WC_PATTERN.search(it["url"]):
                continue
            (excluded if EXCLUDE.search(it["url"]) else wc).append(it)
    with ThreadPoolExecutor(max_workers=8) as ex:
        wc = list(ex.map(enrich, wc))
    for it in wc:
        it["section"] = classify(it["url"])
    wc.sort(key=lambda i: (LANG_ORDER.get(i["lang"], 9), i["title"].lower()))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_sitemaps": SITEMAPS,
        "stats": {
            "urls_scanned": len(scanned),
            "world_cup_articles": len(wc),
            "excluded_referral_pages": len(excluded),
            "fetched_ok": sum(1 for i in wc if i.get("fetched")),
            "newest_de_modification": max((i["date_modified"] or "" for i in wc if i["lang"] == "de"), default=None),
        },
        "final": FINAL,
        "next_tournament": NEXT,
        "sections": [{"key": k, "label": l} for k, l, _ in SECTIONS],
        "articles": wc,
        "excluded": [{"url": i["url"], "lang": i["lang"]} for i in excluded],
    }


def fmt_date(iso):
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d.%m.%Y")
    except ValueError:
        return iso[:10]


def render(data):
    e = html.escape
    sections_html = []
    for sec in data["sections"]:
        items = [a for a in data["articles"] if a["section"] == sec["key"]]
        if not items:
            continue
        lis = []
        for a in items:
            stale = ' <span class="stale" title="Artikel stammt aus der Turnierzeit">Archiv</span>'
            lis.append(
                f'<li><a href="{e(a["url"])}" rel="noopener">{e(a["title"])}</a>'
                f' <span class="badge">{LANG_LABEL.get(a["lang"], a["lang"])}</span>'
                f' <time datetime="{e(a.get("date_modified") or "")}">Stand {fmt_date(a.get("date_modified"))}</time>{stale}</li>'
            )
        sections_html.append(
            f'<section class="group" id="{sec["key"]}"><h3>{e(sec["label"])} <small>{len(items)}</small></h3><ul>{"".join(lis)}</ul></section>'
        )
    st = data["stats"]
    f, n = data["final"], data["next_tournament"]
    tpl = open(os.path.join(ROOT, "template.html"), encoding="utf-8").read()
    out = (tpl
           .replace("{{SITE_URL}}", e(SITE_URL))
           .replace("{{GENERATED}}", e(data["generated_at"]))
           .replace("{{GENERATED_DE}}", e(fmt_date(data["generated_at"])))
           .replace("{{SECTIONS}}", "".join(sections_html))
           .replace("{{N_SCANNED}}", str(st["urls_scanned"]))
           .replace("{{N_WC}}", str(st["world_cup_articles"]))
           .replace("{{N_EXCLUDED}}", str(st["excluded_referral_pages"]))
           .replace("{{NEWEST_DE}}", e(fmt_date(st["newest_de_modification"])))
           .replace("{{F_HOME}}", e(f["home"])).replace("{{F_AWAY}}", e(f["away"]))
           .replace("{{F_SCORE}}", e(f["score"])).replace("{{F_SCORER}}", e(f["scorer"]))
           .replace("{{F_DATE}}", e(f["date"])).replace("{{F_DATE_DE}}", e(f["date_de"]))
           .replace("{{F_VENUE}}", e(f["venue"])).replace("{{F_SOURCE}}", e(f["source"]))
           .replace("{{N_NAME}}", e(n["name"])).replace("{{N_HOST}}", e(n["host"]))
           .replace("{{N_START}}", e(n["start"])).replace("{{N_START_DE}}", e(n["start_de"]))
           .replace("{{N_END_DE}}", e(n["end_de"])).replace("{{N_VENUE}}", e(n["venue"]))
           .replace("{{N_SOURCE}}", e(n["source"])))
    return out


def main():
    data_path = os.path.join(ROOT, "data", "wm-hub.json")
    if "--offline" in sys.argv:
        data = json.load(open(data_path, encoding="utf-8"))
    else:
        data = collect()
        os.makedirs(os.path.dirname(data_path), exist_ok=True)
        json.dump(data, open(data_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    out = render(data)
    open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8").write(out)
    s = data["stats"]
    print(f"ok: {s['world_cup_articles']} WM-Artikel aus {s['urls_scanned']} Sitemap-URLs "
          f"({s['excluded_referral_pages']} Referral-Seiten ausgeschlossen, {s['fetched_ok']} Seiten gelesen) -> index.html")


if __name__ == "__main__":
    main()
