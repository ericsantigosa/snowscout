"""Tests for avalanche.py and reports.py, on small hand-made snippets shaped like each source."""
import json
import unittest
from datetime import date

import avalanche as av
import reports as rp

DAY = date(2026, 2, 16)


class AvalancheTest(unittest.TestCase):
    def test_eaws_levels_drop_elevation_keys(self):
        text = json.dumps({"maxDangerRatings": {"AD-01": 3, "AD-01:high": 3, "AD-01:low:pm": 2, "FR-73": 0}})
        self.assertEqual(av.eaws_levels(text), {"AD-01": 3, "FR-73": 0})

    def test_icgc_levels_use_the_higher_grade_and_validity(self):
        zones = [
            {"id_zona": "3", "grau_perill_primari": "3", "grau_perill_secundari": "2",
             "datavalidesabutlleti": "2026-02-17"},
            {"id_zona": "5", "grau_perill_primari": "2", "grau_perill_secundari": None,
             "datavalidesabutlleti": "2026-02-15"},  # expired before DAY
            {"id_zona": "7", "grau_perill_primari": None, "grau_perill_secundari": None,
             "datavalidesabutlleti": "2026-02-16"},
        ]
        self.assertEqual(av.icgc_levels(json.dumps(zones), DAY), {"ES-CT-PA": 3, "ES-CT-TF": 0})

    def test_levels_fill_catalan_gaps_from_icgc_and_take_border_max(self):
        resorts = [{"id": "pai", "av": ["ES-CT-PA"]}, {"id": "pey", "av": ["FR-67", "FR-68"]},
                   {"id": "gv", "av": ["AD-01"]}]

        def get(url):
            if "avalanche.report" in url:
                return json.dumps({"maxDangerRatings": {"FR-67": 2, "FR-68": 3}})  # no ES-CT, no AD
            self.assertIn("values=2026-02-15;", url)  # ICGC is asked for the day before
            return json.dumps([{"id_zona": "3", "grau_perill_primari": "4",
                                "datavalidesabutlleti": "2026-02-16"}])
        self.assertEqual(av.levels(resorts, DAY, get, log=lambda *_: None), {"pai": 4, "pey": 3})

    def test_levels_survive_both_sources_failing(self):
        def get(url):
            raise OSError("down")
        self.assertEqual(av.levels([{"id": "pai", "av": ["ES-CT-PA"]}], DAY, get, log=lambda *_: None), {})


def otb(o, t):
    return f'<div class="text"><span class="strong">{o}</span> /{t}</div>'


class ReportParserTest(unittest.TestCase):
    def test_pirineu365_counts_colours_from_the_slope_list(self):
        data = {"data": {"is_open": True, "is_winter": True, "report_type": "Snowreport", "updated": "08/02/2026 08:45",
                         "skilifts": {"stats": {"open": 9, "total": 10}},
                         "skislopes": {"stats": {"open": 3, "total": 4}, "items": [
                             {"type": "Verda", "is_open": True}, {"type": "Verda", "is_open": False},
                             {"type": "Negra", "is_open": True}, {"type": "Vermella", "is_open": True}]},
                         "kilometers": {"open": 14, "total": 14}, "snow": {"min": 200, "max": 280}}}
        r = rp.parse_pirineu365(json.dumps(data))
        self.assertTrue(r["open"])
        self.assertEqual(r["col"], {"g": [1, 2], "k": [1, 1], "r": [1, 1]})
        self.assertEqual((r["lifts"], r["slopes"], r["km"], r["depth"]), ([9, 10], [3, 4], [14, 14], [200, 280]))

    def test_pirineu365_summer_mode_is_closed(self):
        r = rp.parse_pirineu365(json.dumps({"data": {"is_open": True, "is_winter": False, "report_type": "Infostiu"}}))
        self.assertFalse(r["open"])
        self.assertIsNone(r["slopes"])

    def test_lumiplan(self):
        html = ('<div class="totaux_lift_inter">' + otb(15, 15) + '</div><div class="totaux_trails">'
                '<img class="image" src="image/type/DOWNHILL_SKIING.svg" alt="">' + otb(24, 24) +
                '<img class="image" src="image/type/DOWNHILL_SKIING_GREEN.svg" alt="">' + otb(9, 9) +
                '<img class="image" src="image/type/DOWNHILL_SKIING_BLACK.svg" alt="">' + otb(3, 4) + '</div>')
        r = rp.parse_lumiplan(html)
        self.assertEqual((r["open"], r["lifts"], r["slopes"], r["col"]), (True, [15, 15], [24, 24], {"g": [9, 9], "k": [3, 4]}))

    def test_lumiplan_lifts_alone_are_not_open(self):
        r = rp.parse_lumiplan('<div class="totaux_lift_inter">' + otb(2, 2) + '</div>')
        self.assertFalse(r["open"])

    def test_grandvalira_both_label_styles(self):
        def badge(label, o, t):
            return (f'<span class="badge__label">Pistes {label}</span><span class="badge__icon"><svg></svg>'
                    f'<span class="badge__internal-text">{o} / {t}</span></span>')
        html = ('<span class="board-panel__subtitle">Darrera actualització: dv., 13/02/2026 - 15:40</span>'
                '<label for="x">Pistes obertes</label><progress id="x" max="27" value="25"></progress>'
                '<label for="y">Instal·lacions</label><progress id="y" max="16" value="13"></progress>'
                + badge("verdes", 8, 8) + badge("Blava", 6, 6) + badge("vermelles", 11, 11) + badge("Negra", 0, 2))
        r = rp.parse_grandvalira(html)
        self.assertEqual((r["open"], r["slopes"], r["lifts"]), (True, [25, 27], [13, 16]))
        self.assertEqual(r["col"], {"g": [8, 8], "b": [6, 6], "r": [11, 11], "k": [0, 2]})
        self.assertEqual(r["date"], "dv., 13/02/2026 - 15:40")

    def test_altiservice(self):
        html = ('<label>Pistes ouvertes</label><p>41<em>/41</em></p><label>Remontées ouvertes</label><p>24<em>/24</em></p>'
                '<label>Pistes vertes</label><p>16<em>/16</em></p><label>Pistes rouges</label><p><em>7/7</em></p>')
        r = rp.parse_altiservice(html)
        self.assertEqual((r["open"], r["slopes"], r["lifts"], r["col"]), (True, [41, 41], [24, 24], {"g": [16, 16], "r": [7, 7]}))

    def test_francemontagnes(self):
        html = ('<li><strong>38</strong> /38 de pistes</li><li><strong>18</strong> /21 remontées</li>'
                '<div class="ski-area__piste--blue"><span class="ski-area__pistes-number"><strong>13</strong>/13</span></div>')
        r = rp.parse_francemontagnes(html)
        self.assertEqual((r["open"], r["slopes"], r["lifts"], r["col"]), (True, [38, 38], [18, 21], {"b": [13, 13]}))


def rsc_page(rows):
    """An HTML page carrying Next.js RSC flight rows, the way OnTheSnow serves them in 2026."""
    flight = "".join(f"{k}:{json.dumps(v, separators=(',', ':'))}\n" for k, v in rows.items())
    return f'<script>self.__next_f.push([1,{json.dumps(flight)}])</script>'


class OnTheSnowTest(unittest.TestCase):
    ROWS = {
        "a": {"title": "Guzet", "slug": "guzet", "snow": "$b", "lifts": "$c", "runs": "$d", "status": "$e",
              "updatedAt": "2026-01-13T16:07:00+00:00"},
        "b": {"base": 35, "summit": 45, "last24": 5},
        "c": {"open": 12, "total": 13},
        "d": {"open": 25, "total": 31},
        "e": {"openFlag": 1, "openingDate": "2025-12-20"},
        "f": {"runs": "$d", "runsBeginner": "$10", "runsExpert": "$11"},  # row ids are hex
        "10": {"openNum": 6, "total": 6},
        "11": {"openNum": None, "total": 4},
    }

    def test_region_page(self):
        r = rp.parse_onthesnow(rsc_page(self.ROWS))["guzet"]
        self.assertEqual((r["open"], r["lifts"], r["slopes"], r["depth"], r["new"]), (True, [12, 13], [25, 31], [35, 45], 5))

    def test_resort_page_levels_as_colours(self):
        r = rp.parse_ots_resort(rsc_page(self.ROWS), {"id": "pyrenees/guzet"})
        self.assertEqual(r["col"], {"g": [6, 6], "k": [0, 4]})

    def test_older_next_data_markup(self):
        page = {"props": {"pageProps": {"fullResort": {
            "slug": "guzet", "snow": {"base": 35}, "lifts": {"open": 12, "total": 13}, "runs": {"open": 25, "total": 31},
            "status": {"openFlag": 1}, "terrain": {"runsBeginner": {"openNum": 6, "total": 6}}}}}}
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(page)}</script>'
        r = rp.parse_ots_resort(html, {"id": "pyrenees/guzet"})
        self.assertEqual((r["open"], r["slopes"], r["col"]), (True, [25, 31], {"g": [6, 6]}))

    def test_collect_falls_back_to_onthesnow_and_adds_opening_dates(self):
        closed = dict(self.ROWS, e={"openFlag": 2, "openingDate": "2026-12-19"})
        resorts = [{"id": "guz", "ots": "guzet", "rep": {"src": "lumiplan", "id": "guzet"}},
                   {"id": "xyz", "ots": "missing"}]

        def get(url):
            if "lumiplan" in url:
                raise OSError("down")
            return rsc_page(closed)
        out = rp.collect(resorts, get, log=lambda *_: None)
        self.assertEqual(list(out), ["guz"])
        self.assertEqual((out["guz"]["src"], out["guz"]["open"], out["guz"]["opens"]), ("onthesnow", False, "2026-12-19"))


if __name__ == "__main__":
    unittest.main()
