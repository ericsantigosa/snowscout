# Snowscout

Snowfall rankings and alerts for Pyrenees ski resorts (Catalonia, Andorra, French Pyrenees),
built for a Pebble Time 2.

- `backend/snowscout.py` runs every 2 h on GitHub Actions. It pulls hourly snowfall from five
  Open-Meteo models (ECMWF IFS, ICON, Météo-France, GFS, UKMO) at each resort's mid-mountain
  altitude, takes the model median, and publishes `data.json` to GitHub Pages.
- When the median forecast reaches ≥20 cm in 24 h or ≥40 cm in 72 h, it sends one Telegram
  message per storm (thresholds in `backend/config.json`).
- `history/YYYY-MM-DD.json` on the `gh-pages` branch keeps the per-model numbers for later
  model checks.

## data.json

```
{ "v": 1, "t": <unix time>, "d0": <unix local midnight of day 0>, "m": [models],
  "r": [ { "id", "n", "reg", "alt", "drv",
           "f48",            fallen in the last 48 h (cm)
           "c72", "lo", "hi" forecast next 72 h: median and model range (cm)
           "m24",            biggest 24 h total within the next 72 h (cm)
           "d": [7],         daily totals, today first (cm)
           "sd",             modelled snow depth (cm)
           "tmin", "fl",     min temp next 24 h (°C), freezing level now (m)
           "cam" } ] }
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
one 50-byte-per-resort blob and sends it to the watch, which caches it in persistent storage.

- **Boards**: Next 72 h · Fresh 48 h · Snow depth. Select on the header row (or a long press
  anywhere) switches board.
- **Detail**: Select on a resort shows 7-day snowfall bars, the 72 h model range, depth,
  min temperature and freezing level; Up/Down step through the board.
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
sends a small summary when the face starts and every 30 minutes; the bottom line turns into a
red "data N h old" warning when the backend data is more than 6 h old.

```
cd watchface && pebble build && pebble install build/watchface.pbw --adb
```

## Data

Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Resort areas and
altitudes from [OpenSkiMap](https://openskimap.org/) / © OpenStreetMap contributors (ODbL),
via `tools/build_resorts.py`. Drive times from the OSRM demo server.
