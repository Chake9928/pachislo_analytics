"""setting_detect のユニットテスト（ゾーン分類・疑似ボーナス・3連単）。

実行:
    python -m unittest tests.test_setting_detect
    python -m unittest tests.test_setting_detect -v
"""

import unittest
from dataclasses import dataclass
from typing import Optional

from setting_detect import (
    ToloveruTranceSpec,
    count_over_3time_single,
    extract_pseudo_bonuses,
    get_spec,
    resolve_known_model_id,
)


@dataclass(frozen=True)
class Event:
    event_type: str
    start_count: Optional[int] = None
    event_seq: Optional[int] = None


def seq(*pairs):
    events = []
    for index, item in enumerate(pairs, start=1):
        if isinstance(item, str):
            events.append(Event(item, event_seq=index))
        else:
            event_type, start_count = item
            events.append(
                Event(event_type, start_count=start_count, event_seq=index)
            )
    return events


class ZoneClassifyTest(unittest.TestCase):
    def setUp(self):
        self.spec = ToloveruTranceSpec()

    def test_boundaries(self):
        self.assertEqual(self.spec.classify_zone(180), "")
        self.assertEqual(self.spec.classify_zone(181), "zone_150g")
        self.assertEqual(self.spec.classify_zone(189), "zone_150g")
        self.assertEqual(self.spec.classify_zone(190), "")
        self.assertEqual(self.spec.classify_zone(280), "")
        self.assertEqual(self.spec.classify_zone(281), "zone_250g")
        self.assertEqual(self.spec.classify_zone(289), "zone_250g")
        self.assertEqual(self.spec.classify_zone(290), "")
        self.assertEqual(self.spec.classify_zone(480), "")
        self.assertEqual(self.spec.classify_zone(485), "zone_450g")
        self.assertEqual(self.spec.classify_zone(490), "")
        self.assertEqual(self.spec.classify_zone(680), "")
        self.assertEqual(self.spec.classify_zone(685), "zone_650g")
        self.assertEqual(self.spec.classify_zone(689), "zone_650g")
        self.assertEqual(self.spec.classify_zone(690), "over_zone_650g")
        self.assertEqual(self.spec.classify_zone(1000), "over_zone_650g")
        self.assertEqual(self.spec.classify_zone(1001), "zone_1000g")
        self.assertEqual(self.spec.classify_zone(None), "")


class PseudoBonusTest(unittest.TestCase):
    def test_bb_followed_by_art_is_pseudo(self):
        events = seq(("BB", 185), "ART", ("BB", 6), ("BB", 8), ("BB", 434), "ART")
        bonuses = extract_pseudo_bonuses(events)
        self.assertEqual([b.start_count for b in bonuses], [185, 434])

    def test_at_continuation_is_excluded(self):
        events = seq("ART", ("BB", 4), ("BB", 6), ("BB", 12))
        self.assertEqual(extract_pseudo_bonuses(events), [])

    def test_trailing_bb_without_st_is_excluded(self):
        events = seq(("BB", 685), "ART", ("BB", 5))
        bonuses = extract_pseudo_bonuses(events)
        self.assertEqual([b.start_count for b in bonuses], [685])


class SingleStreakTest(unittest.TestCase):
    def test_two_singles_are_not_counted(self):
        events = seq("ART", ("BB", 40), "ART", ("BB", 50), "ART", ("BB", 6), ("BB", 80), "ART")
        self.assertEqual(count_over_3time_single(events), 0)

    def test_three_singles_count_as_one(self):
        events = seq(
            "ART",
            ("BB", 324),
            "ART",
            ("BB", 57),
            "ART",
            ("BB", 683),
            "ART",
            ("BB", 6),
            ("BB", 51),
            "ART",
        )
        self.assertEqual(count_over_3time_single(events), 1)

    def test_four_singles_still_one_episode(self):
        events = seq(
            "ART",
            ("BB", 1),
            "ART",
            ("BB", 2),
            "ART",
            ("BB", 3),
            "ART",
            ("BB", 4),
            "ART",
        )
        self.assertEqual(count_over_3time_single(events), 1)

    def test_two_separate_streaks(self):
        events = seq(
            "ART",
            ("BB", 1),
            "ART",
            ("BB", 2),
            "ART",
            ("BB", 3),
            "ART",
            ("BB", 6),
            ("BB", 9),
            "ART",
            ("BB", 4),
            "ART",
            ("BB", 5),
            "ART",
            ("BB", 6),
            "ART",
        )
        self.assertEqual(count_over_3time_single(events), 2)


class AnalyzeDayTest(unittest.TestCase):
    def test_zone_special_is_sum_of_150_and_450(self):
        spec = ToloveruTranceSpec()
        events = seq(
            ("BB", 185),
            "ART",
            ("BB", 485),
            "ART",
            ("BB", 281),
            "ART",
            ("BB", 1032),
            "ART",
        )
        result = spec.analyze_events(events)
        self.assertEqual(result.zone_150g, 1)
        self.assertEqual(result.zone_250g, 1)
        self.assertEqual(result.zone_450g, 1)
        self.assertEqual(result.zone_1000g, 1)
        self.assertEqual(result.zone_special, 2)
        self.assertEqual(result.over_3time_single, 1)

    def test_unknown_model_id(self):
        self.assertIsNone(get_spec(99))
        self.assertIsNone(resolve_known_model_id("unknown"))
        self.assertEqual(get_spec(1).model_id, 1)
        self.assertEqual(
            resolve_known_model_id("L ToLOVEるﾀﾞｰｸﾈｽver.8.7"),
            1,
        )


if __name__ == "__main__":
    unittest.main()
