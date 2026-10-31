"""Avalanche danger (European scale 1-5) per resort.

Main source: the EAWS combined ratings file, one fetch for every service (ICGC, Lauegi, Andorra,
Meteo-France). Its Catalan part (ES-CT) is missing on some days, mostly when ICGC issues a
multi-day bulletin, so the ICGC API fills those gaps. 0 means "no snow / no rating".

`get(url)` returns the response body as text (raises on HTTP errors).
"""
import json
from datetime import date, timedelta

EAWS = "https://static.avalanche.report/eaws_bulletins/{d}/{d}.ratings.json"
ICGC = "https://bpa.icgc.cat/api/apiext/butlletiglobal?values={d};1"
ICGC_ZONES = {"1": "ES-CT-L-04", "2": "ES-CT-RF", "3": "ES-CT-PA", "4": "ES-CT-PP",
              "5": "ES-CT-VN", "6": "ES-CT-PR", "7": "ES-CT-TF"}


def eaws_levels(text):
    """{region id: overall level} from an EAWS *.ratings.json body (elevation/time keys dropped)."""
    ratings = json.loads(text).get("maxDangerRatings", {})
    return {k: int(v) for k, v in ratings.items() if ":" not in k and v is not None}


def icgc_levels(text, day):
    """{region id: level} for ICGC zones whose bulletin is valid on `day` (a date)."""
    out = {}
    for zone in json.loads(text):
        region = ICGC_ZONES.get(str(zone.get("id_zona")))
        valid_until = zone.get("datavalidesabutlleti") or ""
        if not region or valid_until < day.isoformat():
            continue
        levels = [int(x) for x in (zone.get("grau_perill_primari"), zone.get("grau_perill_secundari"))
                  if x not in (None, "")]
        out[region] = max(levels) if levels else 0
    return out


def levels(resorts, day, get, log=print):
    """{resort id: level 0-5}; a resort missing from the result has no rating today.

    Each resort lists its region ids under "av"; a resort on a region border lists both and
    gets the higher level.
    """
    eaws, icgc = {}, {}
    try:
        eaws = eaws_levels(get(EAWS.format(d=day.isoformat())))
    except Exception as exc:  # 404 off-season, network trouble: fall back below
        log(f"avalanche: EAWS unavailable ({exc})")
    wanted = {region for r in resorts for region in r.get("av", [])}
    if any(region.startswith("ES-CT") and region not in eaws for region in wanted):
        try:
            # values=D-1 returns the latest bulletin published on or before that day
            icgc = icgc_levels(get(ICGC.format(d=(day - timedelta(days=1)).isoformat())), day)
        except Exception as exc:
            log(f"avalanche: ICGC unavailable ({exc})")
    out = {}
    for r in resorts:
        found = [eaws[g] if g in eaws else icgc[g] for g in r.get("av", []) if g in eaws or g in icgc]
        if found:
            out[r["id"]] = max(found)
    return out


def today_local(now, utc_offset):
    return date.fromordinal(date(1970, 1, 1).toordinal() + (now + utc_offset) // 86400)
