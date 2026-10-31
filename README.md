# Snowscout

Snowfall rankings and alerts for Pyrenees ski resorts (Catalonia, Andorra, French Pyrenees),
built for a Pebble Time 2.

- `backend/snowscout.py` runs once a day on GitHub Actions (06:23 UTC, with backup slots at
  07:53 and 09:23 that skip if the morning run happened; GitHub drops some scheduled runs).
  It pulls hourly snowfall from five
  Open-Meteo models (ECMWF IFS, ICON, Météo-France, GFS, UKMO) at each resort's mid-mountain
  altitude, takes the model median, and publishes `data.json` to GitHub Pages.
- When the median forecast reaches ≥20 cm in 24 h or ≥40 cm in 72 h, it sends one Telegram
  message per storm (thresholds in `backend/config.json`).
- `history/YYYY-MM-DD.json` on the `gh-pages` branch keeps the per-model numbers for later
  model checks.
- `backend/reports.py` adds each resort's official snow report (open/closed, lifts and slopes
  open, per difficulty colour where the source has it, opening date) and `backend/avalanche.py`
  the day's avalanche danger. Both are best-effort: a failing source is logged and skipped.

## data.json

```
{ "v": 1, "t": <unix time>, "d0": <unix local midnight of day 0>, "avd": <avalanche bulletin day>,
  "m": [models],
  "r": [ { "id", "n", "reg", "alt", "drv",
           "f48",            fallen in the last 48 h (cm)
           "c72", "lo", "hi" forecast next 72 h: median and model range (cm)
           "m24",            biggest 24 h total within the next 72 h (cm)
           "d": [7],         daily totals, today first (cm)
           "sd",             modelled snow depth (cm)
           "tmin", "fl",     min temp next 24 h (°C), freezing level now (m)
           "cam",            webcam still URL or null (fetched by the phone, never re-hosted)
           "av",             avalanche danger 1-5 for the resort's region(s), 0 = no snow, null = no bulletin
           "rep": { "src", "open", "date",
                    "lifts", "slopes", "km": [open, total],
                    "col": { "g"|"b"|"r"|"k": [open, total] },   green/blue/red/black slopes
                    "depth": [base, top], "new" (cm, 24 h), "opens" (YYYY-MM-DD) } } ] }
```

## Local use

```
python backend/snowscout.py --out site --dry-run
python -m unittest discover backend
```

Telegram: put `TELEGRAM_BOT_TOKEN=` and `TELEGRAM_CHAT_ID=` in `backend/.env` locally, and the
same two names as repository secrets for Actions. `--telegram-chat-id` lists the chats that
have messaged the bot; `--telegram-test` sends a test message. To test the Actions side:
`gh workflow run update.yml -f telegram_test=true`.

On Windows, Telegram calls can fail with `CERTIFICATE_VERIFY_FAILED` because Telegram sends the
GoDaddy Root G2 certificate, which the local Windows store may not have fetched yet. Point Python
at a full CA bundle, e.g. Git's: `SSL_CERT_FILE="C:/Program Files/Git/mingw64/etc/ssl/certs/ca-bundle.crt"`.

## Watch app (`watch/`)

Pebble Time 2 (`emery`) watchapp. The phone side (`src/pkjs`) fetches `data.json`, packs it into
one 66-byte-per-resort blob and sends it to the watch, which caches it in persistent storage.

- **Boards**: Next 72 h · Fresh 48 h · Snow depth · Open slopes. Select on the header row (or a
  long press anywhere) switches board. Open slopes lists open resorts by slopes open with
  open/total per colour, then closed resorts by opening day.
- **Detail**: Select on a resort shows 7-day snowfall bars, the 72 h model range, depth,
  min temperature and freezing level, an avalanche danger badge (European colours) and a cam
  tag; Up/Down step through the board.
- **Settings** (gear in the Pebble phone app, built with Clay): first board, favourites (pinned
  on top), hidden resorts.

Build and install from WSL (setup: `tools/wsl_*.sh`):

```
cd watch && pebble build
pebble install build/watch.pbw --adb                 # phone on USB
pebble install build/watch.pbw --emulator emery --vnc
```

## Watchface (`watchface/`)

Time and date over a 7-day strip of the biggest daily snowfall at any resort (today
highlighted), the 72 h leader, and the first day with 10 cm or more somewhere. The phone side
sends a small summary when the face starts and every 2 hours; the bottom line turns into a
red "data N h old" warning when the backend data is more than 30 h old (one missed day).

```
cd watchface && pebble build && pebble install build/watchface.pbw --adb
```

## Data

Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Resort areas and
altitudes from [OpenSkiMap](https://openskimap.org/) / © OpenStreetMap contributors (ODbL),
via `tools/build_resorts.py`. Drive times from the OSRM demo server.

Avalanche danger: the [EAWS](https://www.avalanches.org/) combined ratings
(static.avalanche.report), from the services that issue the bulletins: Institut Cartogràfic i
Geològic de Catalunya (ICGC, also queried directly), Centre de Lauegi d'Aran, Servei Meteorològic
Nacional d'Andorra and Météo-France. Region polygons: EAWS micro-regions (CC0). The bulletin day
is in `data.json` as `avd`.

Snow reports: FGC (pirineu365.cat), the resorts' Lumiplan bulletins, Grandvalira Resorts,
Altiservice, France Montagnes and OnTheSnow (opening dates, 24 h snow, and slopes per level for
resorts without an official per-colour source). Personal, non-commercial use; one request per
source per day.
