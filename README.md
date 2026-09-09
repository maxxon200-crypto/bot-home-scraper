# Casa Watch Italia

A readable Python bot that monitors **homes for sale in Milan up to €10 million**, saves price history, and ranks promising listings. It reads real public Case24 listing pages. **No API key, AI subscription, paid scraping service, or cloud account.**

## Start here — one small success

Install Python **3.11 or newer** from [python.org](https://www.python.org/downloads/), then download this repository or clone it:

```powershell
git clone https://github.com/maxxon200-crypto/bot-home-scraper.git
cd bot-home-scraper
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m casa_watch --serve
```

Open **http://127.0.0.1:8765** in your browser. This is the running app with filter onboarding and a Milan map. Choose filters, click **Choose area**, draw a circle (centre, then edge) or a boundary (points, then Finish), and click **Show homes**. Filters and the selected area stay in this browser after a reload.

Opening `reports/index.html` directly still shows saved homes, but the live map needs the running local app. Its **Open live map** link takes you there. Unknown room/bathroom values are omitted, and descriptions are reduced to structured facts or an excerpt of at most 110 characters.

On Linux/macOS, replace the last three commands with:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m casa_watch --serve
```

## Monitor for hours

```powershell
# Keep checking for eight hours:
.\.venv\Scripts\python.exe -m casa_watch --hours 8

# Or keep checking until you press Ctrl+C:
.\.venv\Scripts\python.exe -m casa_watch
```

Leave the computer awake, connected to the internet, and the terminal running. No background service is installed. Closing the terminal stops the bot. It saves progress automatically, so the same command resumes the catalogue scan and price history after a restart. Do not run two copies with the same data directory; a lock prevents that.

The default interval is **10 minutes after each cycle finishes**. This is polling: the program checks for changes repeatedly. The running app checks for new saved results every ten seconds without reloading the page or clearing your filters. New matches and price changes also appear in `data/monitor.log`.

## Why did the first report only contain 50 homes?

That was the collection after two small runs, not a 50-home limit. The scanner gradually visits the source catalogue. Click **Collect more homes** in the running app to request a bounded 40-page collection, or run:

```powershell
.\.venv\Scripts\python.exe -m casa_watch --once --catalog-pages 40 --detail-pages 35
```

Do not run this command alongside another collector using the same database. Small completed categories are skipped while larger categories still have unvisited pages. The UI displays 12 cards at a time with an explicit total and **Show more**; all matches remain searchable.

Map coordinates come from complete advertised addresses matched locally to Milan's official civic-address index. There is no paid geocoding API. Unmatched or ambiguous addresses stay off the map and are excluded when an area is selected. These are inferred advert-address matches, not surveyed property locations. See [THIRD_PARTY.md](THIRD_PARTY.md) for provenance, licensing and limitations.

## Change filters

Edit `config.toml`, save, and restart the bot. Prices are **total purchase asking prices in euros**, never monthly rents.

```toml
[search]
city = "Milano"
max_price = 10000000
min_sqm = 60
min_bedrooms = 2
```

Keep the other existing settings. This example means “Milan, at most €10 million, at least 60 m² and two **bedrooms**.” Bedrooms are not the same as Italian *locali*, which can include a living room.

Available filters:

| Setting | What it does |
| --- | --- |
| `min_price`, `max_price` | Total advertised purchase price |
| `min_sqm`, `max_sqm` | Advertised floor area |
| `min_bedrooms`, `min_bathrooms` | Minimum structured counts |
| `max_price_per_sqm` | Maximum asking €/m²; 0 disables |
| `property_types` | `apartment`, `penthouse`, `house`, `rustic` |
| `include_any` | At least one phrase appears, e.g. `["isola", "porta romana"]` |
| `require_all` | Every phrase appears, e.g. `["terrazzo", "ascensore"]` |
| `exclude_any` | Reject matching phrases, e.g. `["da ristrutturare"]` |
| `energy_classes` | Allowed published labels, e.g. `["A4", "A3", "B"]` |
| `furnished_only` | Published furnished field must say yes |
| `garden_only` | Published garden field must indicate a garden; shared gardens count |
| `exclude_auctions` | Reject detected auction language |
| `exclude_partial_ownership` | Reject detected ownership-rights language |
| `only_price_drops` | Only homes whose latest observed price change was a reduction |

Empty lists disable phrase/energy restrictions. The initial configuration includes auctions and partial ownership because the requested search is broad; those adverts get warning labels and lower ranking. Keyword detection can miss them, especially before full details arrive. A starting bid is not a fixed purchase price.

Unknown values fail an active filter that needs them. Homes with no asking price cannot be verified against your budget and are not shown as matches. Detail checks are queued, so strict filters can initially hide homes that will qualify later.

Phrase filters match advert text, **not verified amenities**. For example, “senza ascensore” still contains “ascensore”. Pair required phrases with exclusions when useful and read the advert. The map supports circles and custom boundaries. Travel-time search is not implemented.

Your first exercise: change only `min_sqm` from `0` to `60`, run one check, and see how the match count changes. That setting is just a minimum-size rule. You do not need to understand the whole bot to change it.

## How the ranking works

1. Keep recently observed homes and apply your filters.
2. For each home, find other observed homes in the same city and property type, with floor area within ±25% of its size. The user’s budget does not restrict this comparison pool.
3. If at least **five peers** exist, calculate their median asking €/m². The median is the middle value, which is less affected by one very expensive advert than an average.
4. Calculate `100 × (1 − this home's €/m² ÷ peer median)`. Add that signal, capped between −50 and +50, to the score.
5. Add the latest observed percentage price reduction, capped at 30. Subtract 40 for detected auction or ownership-rights language.

Example: a home at €3,000/m² against an observed peer median of €4,000/m² is 25% below that sample median. With no other changes, its signal is 25.

**This is a discovery aid, not a market valuation or guaranteed deal.** Peers can be in different neighbourhoods and conditions. Asking prices are not completed sale prices. Duplicate IDs are merged; identical peer price/size/text signatures are collapsed, but the same property advertised by different agents can still appear more than once. The score is not a percentage probability. Every result includes the source link, timestamps, evidence, and warnings.

## Coverage and running costs

- The shipped adapter supports **Case24 only**. It does not claim to cover every home in Milan or aggregate Idealista/Immobiliare.it.
- Each cycle reads the city’s latest listing page and two catalogue pages. It rotates through apartments, penthouses, independent houses, terraced houses, and rustic homes, persisting the next page across restarts.
- Up to 12 detail pages are checked per cycle. Oldest attempted items are served first; failed details wait at least an hour before being retried.
- Default minimum gap: two seconds per HTTP request. Default daily ceiling: **2,000 requests**, including robots.txt and failed requests, persisted on disk. The daily limit resets at midnight UTC. It can halt collection before the end of a busy day. Change `max_requests_per_day` or lower `detail_pages_per_cycle` to suit your needs.
- HTTP 401/403/429 starts a persisted cooldown of at least an hour; `Retry-After` is honoured when longer. Failed cycles use increasing delays. Timeouts are bounded. The bot does not bypass CAPTCHAs, access controls, or robots exclusions.
- A broad catalogue takes hours or days to explore. Latest listings can appear between checks and disappear before being seen. Old listings are revisited gradually. No complete-coverage or instantaneous-alert guarantee.
- Observations older than 72 hours are hidden by default. “Last observed” means seen by this bot; it is not a publication date or a guarantee of availability. Disappearance from one page does not mean sold.
- Zero paid API usage in this code. You still supply electricity, internet access, and a running computer. Optional hosting would have its own cost.

The [Case24 Milan page](https://www.case24.it/immobili/lombardia/milano/milano/), [robots.txt](https://www.case24.it/robots.txt), and [source terms](https://www.case24.it/termini_utilizzo.php) were inspected during development on 2026-09-09. Robots rules are rechecked during operation; they are not a licence to republish listings. The MIT licence below covers **our code**, not third-party advert text, images, or databases. Generated reports, logs, and saved adverts stay out of Git. No photos or agent contact lists are collected separately.

[Idealista’s official API](https://developers.idealista.com/access-request) requires requesting access. Its approval and pricing are not assumed free; this project does not need it.

## Understand the code

The flow is **fetch → parse → save → filter → rank → report**.

| File | Responsibility |
| --- | --- |
| `config.toml` | Your editable settings |
| `casa_watch/cli.py` | Read commands, lock the database, start/stop |
| `casa_watch/config.py` | Reject invalid settings and typos |
| `casa_watch/source.py` | HTTP requests and all Case24 HTML parsing |
| `casa_watch/models.py` | One home's fields and Italian number parsing |
| `casa_watch/storage.py` | SQLite history, request budget, scan progress |
| `casa_watch/ranking.py` | Filters and the visible scoring formula |
| `casa_watch/monitor.py` | Repeat checks and produce local alerts |
| `casa_watch/report.py` | Escaped HTML report and JSON export |
| `casa_watch/web/` | Onboarding, concise cards, and map drawing |
| `casa_watch/locations.py` | Offline matching to civic street addresses |
| `casa_watch/server.py` | Local app and bounded collection requests |
| `tests/test_core.py` | Small automated examples that check important behaviour |

SQLite is a database stored in one local file, `data/homes.sqlite3`. Its `homes` table stores the latest observation per source ID; `prices` records each distinct observed price; `state` keeps scan positions, budgets, and notification history. No database server is needed.

The exported `reports/homes.json` contains matched homes, rank explanations, and source status. Technical status remains in the export/logs rather than verbose page panels. Do not restore user-removed copy when changing the generator; see [AGENTS.md](AGENTS.md).

## Find a bug in 10 minutes

1. Stop the monitor with Ctrl+C.
2. Run `python -m unittest discover -s tests -v` using your virtual environment's Python.
3. Open `data/monitor.log`. Find the most recent `ERROR` and its file/line.
4. If the site layout changed, inspect `source.py` — the two parsing functions are `parse_search` and `parse_detail`. A missing layout raises an error rather than silently claiming zero listings.
5. Make one change, rerun the tests, then run `--once`.

No live network is used in automated tests. Their HTML is synthetic; there are no fabricated listings mixed into live output. GitHub Actions runs the tests on Windows and Linux with Python 3.11 and 3.12. The workflow tests code; it is not a hosted scraper.

Do not commit your `data/`, `reports/`, personal configurations, or credentials. `.gitignore` excludes them. For a private setup, copy `config.toml` to `config.local.toml` and pass `--config config.local.toml`. Paths inside the file resolve relative to that file.

## Contributing

Use a small branch and a focused change. Add synthetic fixtures when fixing parser bugs, include a useful test, and explain how you checked it. See [CONTRIBUTING.md](CONTRIBUTING.md). MIT licensed.
