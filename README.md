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

## Data

Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0). Resort areas and
altitudes from [OpenSkiMap](https://openskimap.org/) / © OpenStreetMap contributors (ODbL),
via `tools/build_resorts.py`. Drive times from the OSRM demo server.
