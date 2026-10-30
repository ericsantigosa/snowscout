"""Build backend/resorts.json from an OpenSkiMap ski_areas.geojson dump.

Usage:
  python tools/build_resorts.py ski_areas.geojson --home LAT,LON [--out backend/resorts.json]

The dump comes from https://tiles.openskimap.org/geojson/ski_areas.geojson (OSM data, ODbL).
Drive times come from the public OSRM demo server; only the minutes are stored, not the home point.
"""
import argparse
import json
import urllib.request

# OpenSkiMap name -> (id, short display name, region)
PICK = {
    "Estació d'Esquí Baqueira-Beret": ("baq", "Baqueira", "CAT"),
    "Boí Taüll": ("boi", "Boí Taüll", "CAT"),
    "Estació d'esquí de Port-Ainé": ("pai", "Port Ainé", "CAT"),
    "Espot": ("esp", "Espot", "CAT"),
    "Tavascan": ("tav", "Tavascan", "CAT"),
    "Estació d'esquí Port del Comte": ("pdc", "Port Comte", "CAT"),
    "La Molina": ("mol", "La Molina", "CAT"),
    "Masella": ("mas", "Masella", "CAT"),
    "Estació d'esquí i muntanya Vallter 2000": ("vlt", "Vallter", "CAT"),
    "Estació de muntanya Vall de Núria": ("nur", "Núria", "CAT"),
    "GrandValira": ("gv", "Grandvalira", "AND"),
    "Pal-Arinsal": ("pal", "Pal-Arinsal", "AND"),
    "Ordino-Arcalis": ("arc", "Arcalís", "AND"),
    "Font-Romeu Pyrénées 2000, Font-Romeu": ("frm", "Font-Romeu", "FR"),
    "Les Angles, Els Angles": ("ang", "Les Angles", "FR"),
    "Formiguères": ("for", "Formiguères", "FR"),
    "Porté-Puymorens": ("por", "Porté", "FR"),
    "Espace Cambre d'Aze": ("cda", "Cambre d'Aze", "FR"),
    "Ax 3 Domaines": ("ax3", "Ax 3 Domaines", "FR"),
    "Guzet-Neige": ("guz", "Guzet", "FR"),
    "Superbagnères": ("sup", "Superbagnères", "FR"),
    "Peyragudes": ("pey", "Peyragudes", "FR"),
    "Saint-Lary": ("stl", "Saint-Lary", "FR"),
    "Piau-Engaly": ("pia", "Piau-Engaly", "FR"),
    "Grand Tourmalet": ("tou", "Tourmalet", "FR"),
}

# Resorts whose area centroid is not a sensible route target: (lat, lon, extra minutes)
DRIVE_POINT = {
    "nur": (42.3497, 2.1640, 40),  # drive to Queralbs, then the rack railway
    "boi": (42.5186, 0.8481, 0),   # Taüll village, the access road starts there
}


def points(c, acc):
    if isinstance(c[0], (int, float)):
        acc.append(c)
    else:
        for x in c:
            points(x, acc)
    return acc


def drive_minutes(home, resorts):
    targets = [DRIVE_POINT.get(r["id"], (r["lat"], r["lon"], 0)) for r in resorts]
    coords = ";".join([f"{home[1]},{home[0]}"] + [f"{lon},{lat}" for lat, lon, _ in targets])
    url = (f"https://router.project-osrm.org/table/v1/driving/{coords}"
           "?sources=0&annotations=duration")
    req = urllib.request.Request(url, headers={"User-Agent": "snowscout-build/0.1"})
    data = json.load(urllib.request.urlopen(req, timeout=60))
    return [round(s / 60) + t[2] if s is not None else None
            for s, t in zip(data["durations"][0][1:], targets)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("geojson")
    ap.add_argument("--home", required=True, help="LAT,LON for drive times")
    ap.add_argument("--out", default="backend/resorts.json")
    a = ap.parse_args()
    home = [float(x) for x in a.home.split(",")]

    fc = json.load(open(a.geojson, encoding="utf-8"))
    found = {}
    for f in fc["features"]:
        name = f["properties"].get("name")
        if name in PICK and f["properties"].get("status") == "operating":
            st = f["properties"].get("statistics") or {}
            if "minElevation" not in st:
                continue
            # the dump can hold several features per name; keep the one with the most downhill km
            dh = st.get("runs", {}).get("byActivity", {}).get("downhill", {}).get("byDifficulty", {})
            km = sum(v.get("lengthInKm", 0) for v in dh.values())
            rid, short, reg = PICK[name]
            if rid in found and found[rid]["_km"] >= km:
                continue
            pts = points(f["geometry"]["coordinates"], [])
            lo, hi = st["minElevation"], st["maxElevation"]
            found[rid] = {
                "_km": km, "id": rid, "n": short, "reg": reg,
                "lat": round(sum(p[1] for p in pts) / len(pts), 4),
                "lon": round(sum(p[0] for p in pts) / len(pts), 4),
                "base": round(lo), "top": round(hi), "alt": round((lo + hi) / 2 / 10) * 10,
            }
    missing = [v[0] for v in PICK.values() if v[0] not in found]
    if missing:
        raise SystemExit(f"not found in dump: {missing}")

    resorts = [found[v[0]] for v in PICK.values()]
    for r, m in zip(resorts, drive_minutes(home, resorts)):
        del r["_km"]
        r["drv"] = m
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(resorts, fh, ensure_ascii=False, indent=1)
    for r in resorts:
        print(f'{r["id"]:4} {r["n"]:14} {r["reg"]:4} {r["lat"]:8} {r["lon"]:8} '
              f'{r["base"]:5}-{r["top"]:<5} mid {r["alt"]:5}  {r["drv"]} min')


if __name__ == "__main__":
    main()
