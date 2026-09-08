# TipMaster WM-2026 Hub (Prototyp)

**English summary.** A static, crawlable German landing page for the 2026 World Cup on tipmaster.net, generated from TipMaster's own guide sitemaps. `build.py` reads the three sitemaps (151 URLs), keeps the 52 World Cup articles, drops 4 Kalshi/Polymarket referral pages (not licensed in Germany), fetches each article's real title and dates, groups them by knockout round and renders `index.html` plus a reusable `data/wm-hub.json`. The page states the final result, labels the tournament-time articles as archive, and points to what's next (Bundesliga tipping, the next Daily cup run, Women's World Cup 2027). A nightly GitHub Action rebuilds it. The page is German because the product card names the German-speaking market as primary and tipmaster.net defaults to `/de`. Built inside a 45-minute assessment; German copy should get a native-speaker pass before shipping.

**Live:** https://inosmeet.github.io/tipmaster-wm-hub/

## Warum genau das

- `tipmaster.de/world-cup/` leitet heute 301 → 308 → 308 auf `/daily/en/football-fantasy-manager` weiter – eine Seite mit `x-robots-tag: noindex`. Der „World-Cup-Hub“ aus der Produktkarte ist damit für Suchmaschinen und Menschen unsichtbar.
- Die WM 2026 ist seit dem 19. Juli vorbei (Spanien 1:0 Argentinien n.V.). Die 52 vorhandenen WM-Artikel in `/de/ratgeber`, `/en/guide` und `/en-us/guide` stehen noch im Futur; die deutschen wurden zuletzt am 23.06. inhaltlich und am 05.07. in der Sitemap angefasst.
- Zielmarkt ist Deutschland: Wett-Tipps mit Buchmacher-Links kollidieren mit dem GlüStV, und TipMasters eigene Texte sagen „Tippen heißt Prognose, nicht Geldeinsatz“. Deshalb: Ergebnis, Archiv, nächstes Turnier – **keine Wettanbieter-Links**.

## Was `build.py` macht

1. Liest die drei Guide-Sitemaps (151 URLs beim ersten Lauf).
2. Filtert WM-2026-Artikel (52) und schließt Kalshi/Polymarket-Referral-Seiten bewusst aus (4) – in Deutschland nicht lizenziert.
3. Holt pro Artikel Titel, Description und `dateModified`/`datePublished` aus dem JSON-LD der Seite (8 parallele Requests, ~3 s gesamt). Fällt ein Artikel aus, bricht der Build nicht ab.
4. Ordnet nach K.-o.-Runde bzw. Thema, rendert `index.html` aus `template.html` und schreibt `data/wm-hub.json` als wiederverwendbaren Datensatz (z. B. für eine spätere Next.js-Route).

## Entscheidungen

- **Statisch + Generator** statt Next.js-Route: braucht keinen Zugriff aufs Produkt-Repo, ist cachebar und lässt sich per Cron neu bauen (`.github/workflows/rebuild.yml`, täglich).
- **Nichts erfinden:** Titel und Daten kommen von den Seiten selbst. Nur Finalergebnis und Frauen-WM-Termine sind Konstanten – mit FIFA-Quelle verlinkt.
- `canonical` zeigt auf diese Seite, `hreflang` auf die bestehenden EN/US-Hubs. Das „Archiv“-Badge markiert Turnierzeit-Artikel ehrlich als solche, statt sie zu verstecken.
- „Was jetzt?“ statt Sackgasse: Classic (Bundesliga läuft), Daily (nächster Cup-Run) und Countdown zur Frauen-WM 2027 (24.06.–25.07.2027, Brasilien).
- Stdlib-only Python, kein Framework, eine HTML-Datei, hell/dunkel per `prefers-color-scheme`, mobil zuerst.

## Lokal bauen

```bash
SITE_URL=https://example.org/wm/ python3 build.py   # live von tipmaster.net
python3 build.py --offline                          # nur neu rendern aus data/wm-hub.json
```

## Mit mehr als 45 Minuten

- Redirect fixen: `/world-cup` (und `/de/world-cup`) → diese Seite, per Next.js `redirects()` oder Cloudflare-Regel; Daily-Seite bleibt `noindex`.
- Stale-Content-Monitor: dasselbe Sitemap-Crawling über alle Netzwerk-Properties, Alarm bei Fixture-Widgets oder Artikeln älter als X Tage (die Partner-Portale zeigen aktuell „05.07.2026“).
- Ergebnisse aller 104 WM-Spiele einspeisen und die Runden-Artikel mit „So kam es“-Boxen nachrüsten.
- de/en/en-us aus demselben JSON rendern.
