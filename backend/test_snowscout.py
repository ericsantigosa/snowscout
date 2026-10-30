import unittest

import snowscout as s

CFG = {"alert_24h_cm": 20, "alert_72h_cm": 40, "realert_days": 4,
       "regrow_factor": 1.5, "regrow_cm": 15, "quiet_hours": [23, 7], "max_lines": 2}
OFF = 3600                      # CET
DAY0 = 1793314800               # 2026-10-30 00:00 CET
NOW = DAY0 + 10 * 3600          # 10:00 local
RESORT = {"id": "mol", "n": "La Molina", "reg": "CAT", "alt": 2090, "drv": 117}


def fake_loc(snow_by_model):
    """Hourly data from 2 days before DAY0 to 7 days after, like past_days=2/forecast_days=7."""
    start = DAY0 - 2 * 86400
    times = [start + 3600 * i for i in range(9 * 24)]
    hourly = {"time": times}
    for model, fn in snow_by_model.items():
        hourly[f"snowfall_{model}"] = [fn(t) for t in times]
        hourly[f"temperature_2m_{model}"] = [-3.0 for _ in times]
    return {"utc_offset_seconds": OFF, "hourly": hourly}


def row(rid="mol", c72=0, m24=0, d=None):
    return {"id": rid, "n": rid, "c72": c72, "m24": m24, "lo": c72, "hi": c72,
            "d": d or [0] * 7}


class WindowTest(unittest.TestCase):
    def test_window(self):
        self.assertEqual(s.window([1, 2, 3], 0, 2), 3)
        self.assertIsNone(s.window([1, None, 3], 0, 3))
        self.assertIsNone(s.window([1, 2], -1, 2))
        self.assertIsNone(s.window([1, 2], 0, 3))
        self.assertIsNone(s.window([1, 2], 1, 1))


class ResortRowTest(unittest.TestCase):
    def test_sums_and_median(self):
        loc = fake_loc({
            # 1 cm/h for the 10 hours starting now
            "a": lambda t: 1.0 if NOW <= t < NOW + 10 * 3600 else 0.0,
            # 2 cm/h during the 5 hours before now
            "b": lambda t: 2.0 if NOW - 5 * 3600 <= t < NOW else 0.0,
            # stops 30 h from now, so it cannot give a 72 h total
            "c": lambda t: 0.0 if t < NOW + 30 * 3600 else None,
        })
        r, per = s.resort_row(RESORT, loc, ["a", "b", "c"], NOW)
        self.assertEqual(per["a"]["c72"], 10)
        self.assertEqual(per["a"]["m24"], 10)
        self.assertEqual(per["b"]["f48"], 10)
        self.assertIsNone(per["c"]["c72"])
        self.assertEqual(r["c72"], 5)          # median of a=10, b=0; c excluded
        self.assertEqual((r["lo"], r["hi"]), (0, 10))
        self.assertEqual(r["d"][0], 10)        # today: a=10, b=10, c=0 -> median 10
        self.assertEqual(r["tmin"], -3)

    def test_daily_alignment(self):
        # 1 cm every hour of local day 2 only
        loc = fake_loc({"a": lambda t: 1.0 if DAY0 + 2 * 86400 <= t < DAY0 + 3 * 86400 else 0.0})
        r, _ = s.resort_row(RESORT, loc, ["a"], NOW)
        self.assertEqual(r["d"], [0, 0, 24, 0, 0, 0, 0])


class AlertTest(unittest.TestCase):
    def test_thresholds(self):
        hits, _ = s.decide_alerts([row("x", c72=39, m24=19), row("y", c72=25, m24=20),
                                   row("z", c72=40, m24=10)], {}, NOW, CFG)
        self.assertEqual([h["id"] for h in hits], ["z", "y"])

    def test_once_per_storm(self):
        _, state = s.decide_alerts([row(c72=45, m24=25)], {}, NOW, CFG)
        hits, _ = s.decide_alerts([row(c72=55, m24=30)], state, NOW + 7200, CFG)
        self.assertEqual(hits, [])

    def test_realert_when_storm_grows(self):
        _, state = s.decide_alerts([row(c72=40, m24=25)], {}, NOW, CFG)
        hits, state2 = s.decide_alerts([row(c72=60, m24=30)], state, NOW + 7200, CFG)
        self.assertEqual(hits[0]["prev"], 40)
        self.assertEqual(state2["mol"]["c72"], 60)

    def test_realert_after_expiry(self):
        _, state = s.decide_alerts([row(c72=45, m24=25)], {}, NOW, CFG)
        hits, _ = s.decide_alerts([row(c72=45, m24=25)], state, NOW + 4 * 86400, CFG)
        self.assertEqual(len(hits), 1)
        self.assertIsNone(hits[0]["prev"])

    def test_quiet_hours(self):
        self.assertTrue(s.in_quiet_hours(DAY0 + 23 * 3600 + 1800, OFF, [23, 7]))
        self.assertTrue(s.in_quiet_hours(DAY0 + 6 * 3600 + 3540, OFF, [23, 7]))
        self.assertFalse(s.in_quiet_hours(DAY0 + 7 * 3600, OFF, [23, 7]))
        self.assertFalse(s.in_quiet_hours(DAY0 + 12 * 3600, OFF, [23, 7]))

    def test_message(self):
        hits, _ = s.decide_alerts([row("a", c72=50, m24=30, d=[0, 0, 30, 20, 0, 0, 0]),
                                   row("b", c72=45, m24=25), row("c", c72=41, m24=21)],
                                  {}, NOW, CFG)
        msg = s.format_alert(hits, NOW, OFF, CFG["max_lines"])
        lines = msg.splitlines()
        self.assertEqual(len(lines), 4)        # title, 2 resorts, "+1 more"
        self.assertIn("a 50 cm/72h, peak Sun", lines[1])   # 2026-10-30 is a Friday
        self.assertEqual(lines[3], "+1 more")


if __name__ == "__main__":
    unittest.main()
