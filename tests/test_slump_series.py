import unittest
from datetime import date, datetime

from slump_series import JST, SlumpSample, average_series, chain_days


def _ts(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(
        day.year, day.month, day.day, hour, minute, tzinfo=JST
    )


class ChainDaysTest(unittest.TestCase):
    def test_single_day_keeps_original_values(self):
        day = date(2026, 8, 11)
        samples = [
            SlumpSample(_ts(day, 10), 0),
            SlumpSample(_ts(day, 12), -200),
        ]
        chained = chain_days([(day, samples)])
        self.assertEqual([point.chained_value for point in chained], [0, -200])
        self.assertEqual(chained[0].hours_from_origin, 0.0)
        self.assertEqual(chained[1].hours_from_origin, 2.0)

    def test_next_day_starts_at_previous_end(self):
        day1 = date(2026, 8, 11)
        day2 = date(2026, 8, 12)
        days = [
            (
                day1,
                [
                    SlumpSample(_ts(day1, 10), 0),
                    SlumpSample(_ts(day1, 12), -100),
                ],
            ),
            (
                day2,
                [
                    SlumpSample(_ts(day2, 10), 0),
                    SlumpSample(_ts(day2, 11), 50),
                ],
            ),
        ]
        chained = chain_days(days)
        values = [point.chained_value for point in chained]
        self.assertEqual(values, [0, -100, -100, -50])
        self.assertEqual(
            chained[2].hours_from_origin, chained[1].hours_from_origin
        )
        self.assertTrue(chained[2].is_day_start)
        self.assertEqual(chained[3].hours_from_origin, 3.0)

    def test_empty_day_is_skipped(self):
        day1 = date(2026, 8, 11)
        day2 = date(2026, 8, 12)
        day3 = date(2026, 8, 13)
        days = [
            (day1, [SlumpSample(_ts(day1, 10), 10)]),
            (day2, []),
            (day3, [SlumpSample(_ts(day3, 10), 0), SlumpSample(_ts(day3, 11), 20)]),
        ]
        chained = chain_days(days)
        self.assertEqual(
            [point.chained_value for point in chained],
            [10, 10, 30],
        )


class AverageSeriesTest(unittest.TestCase):
    def test_averages_forward_filled_values(self):
        day = date(2026, 8, 11)
        series = {
            1: [
                SlumpSample(_ts(day, 10, 0), 0),
                SlumpSample(_ts(day, 10, 40), 100),
            ],
            2: [
                SlumpSample(_ts(day, 10, 0), 200),
                SlumpSample(_ts(day, 10, 40), 300),
            ],
            3: [
                SlumpSample(_ts(day, 10, 0), -100),
                SlumpSample(_ts(day, 10, 40), -200),
            ],
        }
        averaged = average_series(series, bucket_minutes=20, min_machines=3)
        by_minute = {
            sample.sampled_at.minute: sample.slump_value
            for sample in averaged
            if sample.sampled_at.hour == 10
        }
        self.assertEqual(by_minute[0], 33)
        self.assertEqual(by_minute[40], 67)

    def test_requires_minimum_machine_count(self):
        day = date(2026, 8, 11)
        series = {
            1: [SlumpSample(_ts(day, 10), 10)],
            2: [SlumpSample(_ts(day, 10), 20)],
        }
        averaged = average_series(series, min_machines=3)
        self.assertEqual(averaged, [])


if __name__ == "__main__":
    unittest.main()
