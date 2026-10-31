"""Snowscout backend.

Fetches hourly snowfall for every resort in resorts.json from several Open-Meteo models,
writes a compact data.json for the Pebble app plus a daily per-model archive, and sends a
Telegram alert when the model median crosses the thresholds in config.json.

  python backend/snowscout.py --out site             # normal run (CI)
  python backend/snowscout.py --out tmp --dry-run    # print the alert instead of sending it
  python backend/snowscout.py --telegram-chat-id     # list chats that have messaged the bot
  python backend/snowscout.py --telegram-test        # send a test message

Telegram credentials come from TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (or backend/.env locally).
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.open-meteo.com/v1/forecast"
HOURLY = ["snowfall", "snow_depth", "temperature_2m", "freezing_level_height"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default


def save_json(path, obj, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        if compact:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, fh, ensure_ascii=False, indent=1)


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def http_json(url, data=None, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "snowscout/0.1"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == tries - 1:
                raise
            print(f"retrying after HTTP {exc.code}", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == tries - 1:
                raise
            print(f"retrying after {exc}", file=sys.stderr)
        time.sleep(5 * (attempt + 1))


def fetch_forecast(resorts, models):
    q = {
        "latitude": ",".join(str(r["lat"]) for r in resorts),
        "longitude": ",".join(str(r["lon"]) for r in resorts),
        "elevation": ",".join(str(r["alt"]) for r in resorts),
        "hourly": ",".join(HOURLY),
        "models": ",".join(models),
        "past_days": 2,
        "forecast_days": 7,
        "timezone": "Europe/Madrid",
        "timeformat": "unixtime",
    }
    data = http_json(API + "?" + urllib.parse.urlencode(q))
    return data if isinstance(data, list) else [data]


# ---------------------------------------------------------------- per-resort numbers

def window(series, i0, i1):
    """Sum of series[i0:i1], or None when the model does not cover the whole window."""
    if i0 < 0 or i1 > len(series) or i1 <= i0:
        return None
    part = series[i0:i1]
    if any(x is None for x in part):
        return None
    return sum(part)


def med(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def rnd(x, nd=0):
    return None if x is None else int(round(x, nd))


def model_metrics(hourly, model, i_now, day_idx):
    def series(var):
        return hourly.get(f"{var}_{model}")

    sf = series("snowfall")
    if sf is None:
        return None
    sums24 = [window(sf, k, k + 24) for k in range(i_now, i_now + 49)]
    temps = (series("temperature_2m") or [])[i_now:i_now + 24]
    depth = series("snow_depth")
    fl = series("freezing_level_height")
    return {
        "f48": window(sf, i_now - 48, i_now),
        "c72": window(sf, i_now, i_now + 72),
        "m24": None if None in sums24 else max(sums24),
        "d": [window(sf, a, b) for a, b in day_idx],
        "sd": depth[i_now] if depth else None,
        "tmin": min(temps) if len(temps) == 24 and None not in temps else None,
        "fl": fl[i_now] if fl else None,
    }


def resort_row(resort, loc, models, now):
    """Consensus row for the watch plus the per-model numbers for the archive."""
    hourly = loc["hourly"]
    times = hourly["time"]
    off = loc["utc_offset_seconds"]
    i_now = max(i for i, t in enumerate(times) if t <= now)
    today = (now + off) // 86400
    by_day = {}
    for i, t in enumerate(times):
        by_day.setdefault((t + off) // 86400 - today, []).append(i)
    day_idx = [(by_day[k][0], by_day[k][-1] + 1) if k in by_day else (0, 0) for k in range(7)]

    per = {}
    for m in models:
        mm = model_metrics(hourly, m, i_now, day_idx)
        if mm is not None:
            per[m] = mm

    def cons(key):
        return med(p[key] for p in per.values())

    c72s = [p["c72"] for p in per.values() if p["c72"] is not None]
    sd = cons("sd")
    row = {
        "id": resort["id"], "n": resort["n"], "reg": resort["reg"],
        "alt": resort["alt"], "drv": resort["drv"],
        "f48": rnd(cons("f48")), "c72": rnd(cons("c72")), "m24": rnd(cons("m24")),
        "lo": rnd(min(c72s)) if c72s else None, "hi": rnd(max(c72s)) if c72s else None,
        "sd": rnd(sd * 100) if sd is not None else None,
        "d": [rnd(med(p["d"][k] for p in per.values())) for k in range(7)],
        "tmin": rnd(cons("tmin")), "fl": rnd(cons("fl"), -1),
        "cam": resort.get("cam"),  # webcam still URL; the phone fetches it directly
    }
    archive = {m: {k: (round(v, 1) if isinstance(v, float) else
                       [None if x is None else round(x, 1) for x in v] if isinstance(v, list) else v)
                   for k, v in p.items()} for m, p in per.items()}
    return row, archive


# ---------------------------------------------------------------- alerts

def triggered(row, cfg):
    return row["c72"] is not None and (
        (row["m24"] or 0) >= cfg["alert_24h_cm"] or row["c72"] >= cfg["alert_72h_cm"])


def decide_alerts(rows, state, now, cfg):
    """Pick the resorts to alert on.

    state maps resort id -> {"at": unix time of the last alert, "c72": cm alerted}.
    A resort alerts once per storm: again only after realert_days, or when the 72 h
    total has grown by regrow_factor and regrow_cm since the last alert.
    """
    keep = cfg["realert_days"] * 86400
    new_state = {k: v for k, v in state.items() if now - v["at"] < keep}
    hits = []
    for row in rows:
        if not triggered(row, cfg):
            continue
        prev = new_state.get(row["id"])
        if prev and not (row["c72"] >= prev["c72"] * cfg["regrow_factor"]
                         and row["c72"] - prev["c72"] >= cfg["regrow_cm"]):
            continue
        hits.append(dict(row, prev=prev["c72"] if prev else None))
        new_state[row["id"]] = {"at": now, "c72": row["c72"]}
    hits.sort(key=lambda r: -r["c72"])
    return hits, new_state


def in_quiet_hours(now, off, quiet):
    start, end = quiet
    hour = (now + off) % 86400 // 3600
    return hour >= start or hour < end if start > end else start <= hour < end


def day_label(k, now, off):
    if k == 0:
        return "today"
    if k == 1:
        return "tomorrow"
    weekday = datetime.fromtimestamp(now + off, timezone.utc).weekday()
    return WEEKDAYS[(weekday + k) % 7]


def format_alert(hits, now, off, max_lines):
    lines = ["Snowscout: snow coming"]  # no emoji: the Pebble notification font may lack them
    for r in hits[:max_lines]:
        soon = [x or 0 for x in r["d"][:4]]
        peak = day_label(soon.index(max(soon)), now, off)
        grew = f" (up from {r['prev']})" if r["prev"] is not None else ""
        lines.append(f"{r['n']} {r['c72']} cm/72h{grew}, peak {peak}, "
                     f"max {r['m24']}/24h, models {r['lo']}-{r['hi']}")
    if len(hits) > max_lines:
        lines.append(f"+{len(hits) - max_lines} more")
    return "\n".join(lines)


def telegram(method, token, **params):
    data = urllib.parse.urlencode(params).encode() if params else None
    return http_json(f"https://api.telegram.org/bot{token}/{method}", data=data, tries=2)


# ---------------------------------------------------------------- main

def fresh_enough(data_path, now, hours):
    """True when data_path holds a data.json written less than `hours` before `now`."""
    data = load_json(data_path)
    return bool(data) and now - data.get("t", 0) < hours * 3600


def print_table(rows):
    print(f"{'resort':14} {'72h':>4} {'range':>9} {'24h':>4} {'48h ago':>7} {'depth':>5} {'fl':>5}  daily")
    for r in sorted(rows, key=lambda r: -(r["c72"] or 0)):
        rng = f"{r['lo']}-{r['hi']}"
        print(f"{r['n']:14} {r['c72']!s:>4} {rng:>9} {r['m24']!s:>4} {r['f48']!s:>7} "
              f"{r['sd']!s:>5} {r['fl']!s:>5}  {r['d']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE.parent / "site")
    ap.add_argument("--dry-run", action="store_true", help="print the alert instead of sending it")
    ap.add_argument("--now", type=int, help="override the current unix time (testing)")
    ap.add_argument("--skip-if-newer", type=float, metavar="HOURS",
                    help="do nothing if the existing data.json is younger than this (backup runs)")
    ap.add_argument("--telegram-chat-id", action="store_true", help="list chats that messaged the bot")
    ap.add_argument("--telegram-test", action="store_true", help="send a test message")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    load_env(HERE / ".env")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if a.telegram_chat_id or a.telegram_test:
        if not token:
            sys.exit("TELEGRAM_BOT_TOKEN is not set")
        if a.telegram_chat_id:
            for upd in telegram("getUpdates", token)["result"]:
                c = (upd.get("message") or upd.get("my_chat_member") or {}).get("chat", {})
                if c:
                    print(c["id"], c.get("type"), c.get("username") or c.get("title"))
        elif not chat:
            sys.exit("TELEGRAM_CHAT_ID is not set (find it with --telegram-chat-id)")
        else:
            telegram("sendMessage", token, chat_id=chat, text="Snowscout test: alerts reach you.")
            print("sent")
        return

    now = a.now or int(time.time())
    if a.skip_if_newer is not None and fresh_enough(a.out / "data.json", now, a.skip_if_newer):
        print(f"data.json is younger than {a.skip_if_newer} h: nothing to do")
        return

    cfg = load_json(HERE / "config.json")
    resorts = load_json(HERE / "resorts.json")
    locs = fetch_forecast(resorts, cfg["models"])
    off = locs[0]["utc_offset_seconds"]

    rows, archive = [], {}
    for resort, loc in zip(resorts, locs):
        row, per = resort_row(resort, loc, cfg["models"], now)
        rows.append(row)
        archive[resort["id"]] = per

    day0 = now - (now + off) % 86400
    save_json(a.out / "data.json", {"v": 1, "t": now, "d0": day0, "m": cfg["models"], "r": rows},
              compact=True)
    date = datetime.fromtimestamp(now + off, timezone.utc).strftime("%Y-%m-%d")
    save_json(a.out / "history" / f"{date}.json", {"t": now, "r": archive}, compact=True)
    print_table(rows)

    state_path = a.out / "state.json"
    state = load_json(state_path, {})
    hits, new_state = decide_alerts(rows, state, now, cfg)
    if not hits:
        print("no alert")
        save_json(state_path, new_state)
        return
    msg = format_alert(hits, now, off, cfg["max_lines"])
    print(msg)
    if in_quiet_hours(now, off, cfg["quiet_hours"]):
        print("quiet hours: holding the alert for the next run")
    elif a.dry_run or not (token and chat):
        print("dry run / no Telegram credentials: not sent")
    else:
        telegram("sendMessage", token, chat_id=chat, text=msg)
        save_json(state_path, new_state)
        print("alert sent")


if __name__ == "__main__":
    main()
