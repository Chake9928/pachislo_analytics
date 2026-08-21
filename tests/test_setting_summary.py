"""setting_summary のユニットテスト（CSV読込・指数・HTML生成）。

実行:
    python -m unittest tests.test_setting_summary
    python -m unittest tests.test_setting_summary -v
"""

import csv
import tempfile
import unittest
from pathlib import Path

from setting_summary import (
    classify_machine,
    load_setting_dir,
    render_summary_html,
    write_setting_summary,
)


def _write_csv(path: Path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class SettingSummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        _write_csv(
            self.dir / "store_total.csv",
            [
                "store_id",
                "model_id",
                "machine_count",
                "date_from",
                "date_to",
                "zone_150g",
                "zone_250g",
                "zone_450g",
                "zone_650g",
                "over_zone_650g",
                "zone_1000g",
                "over_3time_single",
                "zone_special",
            ],
            [
                {
                    "store_id": "100928",
                    "model_id": "1",
                    "machine_count": "2",
                    "date_from": "2026-08-12",
                    "date_to": "2026-08-13",
                    "zone_150g": "5",
                    "zone_250g": "3",
                    "zone_450g": "1",
                    "zone_650g": "4",
                    "over_zone_650g": "2",
                    "zone_1000g": "1",
                    "over_3time_single": "3",
                    "zone_special": "6",
                }
            ],
        )
        machine_fields = [
            "store_id",
            "model_id",
            "machine_id",
            "unit_number",
            "date_from",
            "date_to",
            "zone_150g",
            "zone_250g",
            "zone_450g",
            "zone_650g",
            "over_zone_650g",
            "zone_1000g",
            "over_3time_single",
            "zone_special",
        ]
        _write_csv(
            self.dir / "machine_total.csv",
            machine_fields,
            [
                {
                    "store_id": "100928",
                    "model_id": "1",
                    "machine_id": "M0001",
                    "unit_number": "3075",
                    "date_from": "2026-08-12",
                    "date_to": "2026-08-13",
                    "zone_150g": "5",
                    "zone_250g": "1",
                    "zone_450g": "1",
                    "zone_650g": "3",
                    "over_zone_650g": "1",
                    "zone_1000g": "0",
                    "over_3time_single": "1",
                    "zone_special": "6",
                },
                {
                    "store_id": "100928",
                    "model_id": "1",
                    "machine_id": "M0002",
                    "unit_number": "3076",
                    "date_from": "2026-08-12",
                    "date_to": "2026-08-13",
                    "zone_150g": "0",
                    "zone_250g": "2",
                    "zone_450g": "0",
                    "zone_650g": "1",
                    "over_zone_650g": "1",
                    "zone_1000g": "1",
                    "over_3time_single": "2",
                    "zone_special": "0",
                },
            ],
        )
        daily_fields = [
            "store_id",
            "model_id",
            "machine_id",
            "unit_number",
            "data_date",
            "zone_150g",
            "zone_250g",
            "zone_450g",
            "zone_650g",
            "over_zone_650g",
            "zone_1000g",
            "over_3time_single",
            "zone_special",
        ]
        _write_csv(
            self.dir / "machine_daily.csv",
            daily_fields,
            [
                {
                    "store_id": "100928",
                    "model_id": "1",
                    "machine_id": "M0001",
                    "unit_number": "3075",
                    "data_date": "2026-08-12",
                    "zone_150g": "2",
                    "zone_250g": "0",
                    "zone_450g": "1",
                    "zone_650g": "1",
                    "over_zone_650g": "0",
                    "zone_1000g": "0",
                    "over_3time_single": "0",
                    "zone_special": "3",
                },
                {
                    "store_id": "100928",
                    "model_id": "1",
                    "machine_id": "M0001",
                    "unit_number": "3075",
                    "data_date": "2026-08-13",
                    "zone_150g": "3",
                    "zone_250g": "1",
                    "zone_450g": "0",
                    "zone_650g": "2",
                    "over_zone_650g": "1",
                    "zone_1000g": "0",
                    "over_3time_single": "1",
                    "zone_special": "3",
                },
                {
                    "store_id": "100928",
                    "model_id": "1",
                    "machine_id": "M0002",
                    "unit_number": "3076",
                    "data_date": "2026-08-12",
                    "zone_150g": "0",
                    "zone_250g": "1",
                    "zone_450g": "0",
                    "zone_650g": "0",
                    "over_zone_650g": "1",
                    "zone_1000g": "0",
                    "over_3time_single": "1",
                    "zone_special": "0",
                },
                {
                    "store_id": "100928",
                    "model_id": "1",
                    "machine_id": "M0002",
                    "unit_number": "3076",
                    "data_date": "2026-08-13",
                    "zone_150g": "0",
                    "zone_250g": "1",
                    "zone_450g": "0",
                    "zone_650g": "1",
                    "over_zone_650g": "0",
                    "zone_1000g": "1",
                    "over_3time_single": "1",
                    "zone_special": "0",
                },
            ],
        )
        _write_csv(
            self.dir / "store_daily.csv",
            [
                "store_id",
                "model_id",
                "data_date",
                "machine_count",
                "zone_150g",
                "zone_250g",
                "zone_450g",
                "zone_650g",
                "over_zone_650g",
                "zone_1000g",
                "over_3time_single",
                "zone_special",
            ],
            [
                {
                    "store_id": "100928",
                    "model_id": "1",
                    "data_date": "2026-08-12",
                    "machine_count": "2",
                    "zone_150g": "2",
                    "zone_250g": "1",
                    "zone_450g": "1",
                    "zone_650g": "1",
                    "over_zone_650g": "1",
                    "zone_1000g": "0",
                    "over_3time_single": "1",
                    "zone_special": "3",
                },
                {
                    "store_id": "100928",
                    "model_id": "1",
                    "data_date": "2026-08-13",
                    "machine_count": "2",
                    "zone_150g": "3",
                    "zone_250g": "2",
                    "zone_450g": "0",
                    "zone_650g": "3",
                    "over_zone_650g": "1",
                    "zone_1000g": "1",
                    "over_3time_single": "2",
                    "zone_special": "3",
                },
            ],
        )
        _write_csv(
            self.dir / "pseudo_bonus_events.csv",
            [
                "store_id",
                "model_id",
                "machine_id",
                "unit_number",
                "data_date",
                "start_count",
                "zone",
            ],
            [
                {
                    "store_id": "100928",
                    "model_id": "1",
                    "machine_id": "M0001",
                    "unit_number": "3075",
                    "data_date": "2026-08-12",
                    "start_count": "185",
                    "zone": "zone_150g",
                }
            ],
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_high_index_and_tags(self):
        data = load_setting_dir(self.dir)
        by_id = {m["machine_id"]: m for m in data["machines"]}
        self.assertEqual(by_id["M0001"]["late_zone"], 1)
        self.assertEqual(by_id["M0001"]["high_index"], 2 * 6 + 3 - 1)
        self.assertIn("高設定候補", by_id["M0001"]["tags"])
        self.assertIn("低設定寄り", by_id["M0002"]["tags"])

    def test_classify_cold_and_ceiling(self):
        tags = classify_machine(
            {
                "zone_special": 4,
                "late_zone": 12,
                "over_3time_single": 8,
                "zone_1000g": 7,
            }
        )
        self.assertIn("高設定シグナル", tags)
        self.assertIn("冷遇多発", tags)
        self.assertIn("天井寄り", tags)

    def test_html_contains_commentary_and_store(self):
        path = write_setting_summary(self.dir)
        text = path.read_text(encoding="utf-8")
        self.assertIn("100928", text)
        self.assertIn("考察", text)
        self.assertIn("M0001", text)
        self.assertIn("<!DOCTYPE html>", text)
        html = render_summary_html(load_setting_dir(self.dir))
        self.assertIn("高設定候補", html)


if __name__ == "__main__":
    unittest.main()
