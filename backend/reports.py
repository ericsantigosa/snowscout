"""Official snow reports: open/closed, lifts and slopes open, per difficulty colour where the
source has it (g/b/r/k = green/blue/red/black, each [open, total]).

Sources, chosen per resort in resorts.json under "rep":
  pirineu365      FGC's public JSON API (La Molina, Nuria, Vallter, Espot, Port Aine, Boi)
  lumiplan        the Lumiplan bulletin the resorts embed (French resorts)
  grandvalira     the Grandvalira Resorts site template (Grandvalira, Arcalis, Pal-Arinsal)
  altiservice     Altiservice's resort pages (Font-Romeu, Saint-Lary)
  francemontagnes France Montagnes resort page (Ax 3 Domaines)
  ots             OnTheSnow resort page, for resorts without an official per-colour source; its
                  Beginner/Intermediate/Advanced/Expert levels stand in for green/blue/red/black
OnTheSnow's three region pages ("ots" slug) cover every resort with totals, the opening date and
24 h new snow; they fill in when a resort's own source fails.

A resort counts as open when slopes are open (some report summer lifts as open lifts).

`get(url)` returns the response body as text (raises on HTTP errors).
"""
import json
import re

URLS = {
    "pirineu365": "https://api.pirineu365.cat/api/v1/web/stations/{id}/report?days_offset=0&format=json&language=ca",
    "lumiplan": "https://bulletinv3.lumiplan.pro/bulletin.php?station={id}&lang=fr&isSoir=false",
    "grandvalira": "{url}",
    "altiservice": "https://www.altiservice.com/{id}/meteo-et-enneigement",
    "francemontagnes": "https://www.france-montagnes.com/sit/{id}/",
    "ots": "https://www.onthesnow.co.uk/{id}/skireport",
}
OTS_PAGES = ["https://www.onthesnow.co.uk/pyrenees/skireport",
             "https://www.onthesnow.co.uk/spain/skireport",
             "https://www.onthesnow.co.uk/andorra/skireport"]
COLOURS = "gbrk"


def report(src, open_, lifts=None, slopes=None, col=None, km=None, depth=None, date=None):
    return {"src": src, "open": open_, "lifts": lifts, "slopes": slopes, "col": col or None,
            "km": km, "depth": depth, "new": None, "opens": None, "date": date}


def pair(stats):
    if not stats or stats.get("total") in (None, 0):
        return None
    return [stats.get("open") or 0, stats["total"]]


# ---------------------------------------------------------------- per-source parsers

FGC_TYPES = {"Verda": "g", "Blava": "b", "Vermella": "r", "Negra": "k"}


def parse_pirineu365(text, src=None):
    d = json.loads(text)["data"]
    if not (d.get("is_winter") and d.get("report_type") == "Snowreport"):
        return report("pirineu365", False, date=d.get("updated"))  # summer mode: no ski data
    col = {}
    for item in (d.get("skislopes") or {}).get("items") or []:
        c = FGC_TYPES.get(item.get("type"))
        if c:
            counts = col.setdefault(c, [0, 0])
            counts[0] += bool(item.get("is_open"))
            counts[1] += 1
    snow = d.get("snow") or {}
    depth = [snow["min"], snow["max"]] if snow.get("max") is not None else None
    return report("pirineu365", bool(d.get("is_open")), pair((d.get("skilifts") or {}).get("stats")),
                  pair((d.get("skislopes") or {}).get("stats")), col, pair(d.get("kilometers")), depth,
                  d.get("updated"))


LUMIPLAN_COLOURS = {"GREEN": "g", "BLUE": "b", "RED": "r", "BLACK": "k"}
OPEN_TOTAL = r'<span class="strong">\s*(\d+)\s*</span>\s*/\s*(\d+)'


def parse_lumiplan(text, src=None):
    lifts = re.search(r'totaux_lift.{0,600}?' + OPEN_TOTAL, text, re.S)
    slopes, col = None, {}
    for kind, o, t in re.findall(r'DOWNHILL_SKIING(?:_([A-Z]+))?\.svg".{0,400}?' + OPEN_TOTAL, text, re.S):
        if not kind:
            slopes = slopes or [int(o), int(t)]
        elif kind in LUMIPLAN_COLOURS:
            col.setdefault(LUMIPLAN_COLOURS[kind], [int(o), int(t)])
    lifts = [int(lifts.group(1)), int(lifts.group(2))] if lifts else None
    date = re.search(r'class="intro_maj"[^>]*>\s*([^<]+?)\s*<', text)
    return report("lumiplan", bool(slopes and slopes[0]), lifts, slopes, col, date=date.group(1) if date else None)


# the labels changed during 2025-26 ("Pistes verdes" -> "Pistes Verda"), so match word stems
GV_COLOURS = {"verd": "g", "blav": "b", "vermell": "r", "negr": "k"}


def labelled_progress(text, labels):
    """[value, max] of the first <progress> after a <label> in `labels`."""
    for label, attrs in re.findall(r'<label[^>]*>\s*([^<]+?)\s*</label>\s*<progress([^>]*)>', text):
        if label in labels:
            mx = re.search(r'max="(\d+)"', attrs)
            val = re.search(r'value="(\d+)"', attrs)
            if mx and val and int(mx.group(1)):
                return [int(val.group(1)), int(mx.group(1))]
    return None


def parse_grandvalira(text, src=None):
    slopes = labelled_progress(text, ("Pistes obertes", "Pistes"))
    lifts = labelled_progress(text, ("Instal·lacions",))
    km = labelled_progress(text, ("Km esquiables",))
    col = {}
    for stem, o, t in re.findall(r'badge__label">\s*Pistes (verd|blav|vermell|negr)\w*\s*</span>'
                                 r'.{0,3000}?badge__internal-text">\s*(\d+)\s*/\s*(\d+)', text, re.S | re.I):
        col.setdefault(GV_COLOURS[stem.lower()], [int(o), int(t)])
    date = re.search(r'Darrera actualitzaci[^:<]*:\s*([^<]+?)\s*<', text)
    return report("grandvalira", bool(slopes and slopes[0]), lifts, slopes, col, km,
                  date=date.group(1) if date else None)


ALTI_COLOURS = {"vertes": "g", "bleues": "b", "rouges": "r", "noires": "k"}


def parse_altiservice(text, src=None):
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style|svg).*?</\1>", "", text, flags=re.S)))

    def counts(label):
        m = re.search(label + r"\s*(\d+)\s*/\s*(\d+)", plain)
        return [int(m.group(1)), int(m.group(2))] if m else None

    slopes = counts("Pistes ouvertes")
    col = {c: v for word, c in ALTI_COLOURS.items() if (v := counts("Pistes " + word))}
    return report("altiservice", bool(slopes and slopes[0]), counts("Remontées ouvertes"), slopes, col)


FM_COLOURS = {"green": "g", "blue": "b", "red": "r", "black": "k"}


def parse_francemontagnes(text, src=None):
    col = {}
    for name, o, t in re.findall(r'ski-area__piste--(green|blue|red|black)".{0,400}?ski-area__pistes-number">'
                                 r'\s*<strong>\s*(\d+)\s*</strong>\s*/\s*(\d+)', text, re.S):
        col.setdefault(FM_COLOURS[name], [int(o), int(t)])
    slopes = re.search(r"<strong>\s*(\d+)\s*</strong>\s*/\s*(\d+)\s*de pistes", text)
    lifts = re.search(r"<strong>\s*(\d+)\s*</strong>\s*/\s*(\d+)\s*remont", text)
    slopes = [int(slopes.group(1)), int(slopes.group(2))] if slopes else None
    lifts = [int(lifts.group(1)), int(lifts.group(2))] if lifts else None
    return report("francemontagnes", bool(slopes and slopes[0]), lifts, slopes, col)


OTS_LEVELS = {"runsBeginner": "g", "runsIntermediate": "b", "runsAdvanced": "r", "runsExpert": "k"}


def parse_ots_resort(text, src):
    """One OnTheSnow resort page: the resort's totals plus open/total per difficulty level."""
    slug = src["id"].rsplit("/", 1)[-1]
    objects, terrain = _ots_objects(text)
    rep = next((ots_report(o) for o in objects if o.get("slug") == slug), None)
    if rep is None:
        raise ValueError(f"resort {slug} not on the page")
    col = {}
    for level, c in OTS_LEVELS.items():
        counts = (terrain or {}).get(level) or {}
        if counts.get("total"):
            col[c] = [counts.get("openNum") or 0, counts["total"]]
    rep["col"] = col or None
    return rep


PARSERS = {"pirineu365": parse_pirineu365, "lumiplan": parse_lumiplan,
           "grandvalira": parse_grandvalira, "altiservice": parse_altiservice,
           "francemontagnes": parse_francemontagnes, "ots": parse_ots_resort}


# ---------------------------------------------------------------- OnTheSnow region pages

def _ots_objects(text):
    """(resort objects, terrain object or None) from an OnTheSnow page: Next.js RSC flight rows
    (2026 markup) or __NEXT_DATA__ JSON (older markup)."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
    if m:
        out, terrain = [], []

        def walk(node):
            if isinstance(node, dict):
                if "snow" in node and "lifts" in node and "status" in node and "slug" in node:
                    out.append(node)
                if "runsBeginner" in node:
                    terrain.append(node)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(json.loads(m.group(1)))
        return out, (terrain[0] if terrain else None)

    flight = ""
    for chunk in re.findall(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', text, re.S):
        try:
            flight += json.loads(chunk)
        except ValueError:
            pass
    rows = {}
    for line in re.split(r"\n(?=[0-9a-f]+:)", flight):
        key, _, value = line.partition(":")
        rows[key] = value

    def resolve(v, depth=0):
        if isinstance(v, str) and v.startswith("$") and v[1:] in rows and depth < 3:
            try:
                return resolve(json.loads(rows[v[1:]]), depth + 1)
            except ValueError:
                return None
        if isinstance(v, dict) and depth < 3:
            return {k: resolve(x, depth + 1) for k, x in v.items()}
        return v

    out, terrain = [], None
    for value in rows.values():
        if '"runsBeginner"' in value and terrain is None:
            try:
                terrain = resolve(json.loads(value))
            except ValueError:
                pass
        if not re.search(r'"snow"\s*:\s*"\$', value) or '"slug"' not in value:
            continue
        try:
            obj = json.loads(value)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append({k: resolve(obj.get(k)) for k in ("slug", "snow", "lifts", "runs", "status", "updatedAt")})
    return out, terrain


def ots_report(o):
    status = o.get("status") or {}
    snow = o.get("snow") or {}
    is_open = status.get("openFlag") == 1
    rep = report("onthesnow", is_open, pair(o.get("lifts")), pair(o.get("runs")),
                 depth=[snow.get("base"), snow.get("summit")] if is_open and snow.get("base") is not None else None,
                 date=o.get("updatedAt"))
    rep["new"] = snow.get("last24") if is_open else None
    rep["opens"] = status.get("openingDate")
    return rep


def parse_onthesnow(text):
    """{slug: report} from one OnTheSnow region page."""
    out = {}
    for o in _ots_objects(text)[0]:
        out.setdefault(o["slug"], ots_report(o))
    return out


# ---------------------------------------------------------------- all resorts

def collect(resorts, get, log=print):
    """{resort id: report}; resorts with no working source are left out."""
    ots = {}
    for url in OTS_PAGES:
        try:
            ots.update(parse_onthesnow(get(url)))
        except Exception as exc:
            log(f"reports: OnTheSnow page failed ({url}: {exc})")
    out = {}
    for r in resorts:
        rep = None
        src = r.get("rep")
        if src:
            try:
                rep = PARSERS[src["src"]](get(URLS[src["src"]].format(**src)), src)
            except Exception as exc:
                log(f"reports: {r['id']} via {src['src']} failed ({exc})")
        fallback = ots.get(r.get("ots"))
        if rep is None:
            rep = fallback
        elif fallback:
            rep["opens"] = fallback["opens"]
            rep["new"] = fallback["new"] if rep["open"] else None
        if rep:
            if rep["open"]:
                rep["opens"] = None
            out[r["id"]] = rep
    return out
