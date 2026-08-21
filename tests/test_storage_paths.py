"""raw HTML パス推定のユニットテスト。

実行:
    python -m unittest tests.test_storage_paths
    python -m unittest tests.test_storage_paths -v
"""

import unittest
from datetime import date
from pathlib import Path

from storage_paths import (
    parse_raw_html_path,
    raw_html_path,
    slump_chained_machine_dir,
    slump_daily_average_dir,
    slump_daily_machine_dir,
    slump_series_dir,
)


class RawHtmlPathTest(unittest.TestCase):
    def test_new_path(self):
        path = Path("data/raw/100928/1/2026-08-12/M0001.html")
        loc = parse_raw_html_path(path)
        self.assertEqual(loc.store_id, "100928")
        self.assertEqual(loc.model_id, "1")
        self.assertEqual(loc.data_date, date(2026, 8, 12))
        self.assertEqual(loc.machine_code, "M0001")
        self.assertIsNone(loc.unit)

    def test_old_store_date_unit_path(self):
        path = Path("data/raw/100928/2026-08-12/3075.html")
        loc = parse_raw_html_path(path)
        self.assertEqual(loc.store_id, "100928")
        self.assertIsNone(loc.model_id)
        self.assertEqual(loc.data_date, date(2026, 8, 12))
        self.assertEqual(loc.unit, 3075)
        self.assertIsNone(loc.machine_code)

    def test_oldest_date_unit_path(self):
        path = Path("data/raw/2026-08-12/3075.html")
        loc = parse_raw_html_path(path)
        self.assertIsNone(loc.store_id)
        self.assertIsNone(loc.model_id)
        self.assertEqual(loc.data_date, date(2026, 8, 12))
        self.assertEqual(loc.unit, 3075)

    def test_builder_matches_new_layout(self):
        path = raw_html_path(
            Path("data/raw"),
            "100928",
            1,
            date(2026, 8, 12),
            "M0001",
        )
        self.assertEqual(
            path,
            Path("data/raw") / "100928" / "1" / "2026-08-12" / "M0001.html",
        )
        loc = parse_raw_html_path(path)
        self.assertEqual(loc.store_id, "100928")
        self.assertEqual(loc.model_id, "1")
        self.assertEqual(loc.machine_code, "M0001")


class SlumpPathTest(unittest.TestCase):
    def test_store_model_comes_first(self):
        root = Path("data/slump")
        self.assertEqual(
            slump_daily_machine_dir(root, date(2026, 8, 11), "100928", 1),
            root / "100928" / "1" / "01_daily_by_machine" / "2026-08-11",
        )
        self.assertEqual(
            slump_chained_machine_dir(root, "100928", 1),
            root / "100928" / "1" / "02_chained_by_machine",
        )
        self.assertEqual(
            slump_daily_average_dir(root, "100928", 1),
            root / "100928" / "1" / "03_daily_average",
        )
        self.assertEqual(
            slump_series_dir(root, "100928", 1),
            root / "100928" / "1" / "series",
        )


if __name__ == "__main__":
    unittest.main()
