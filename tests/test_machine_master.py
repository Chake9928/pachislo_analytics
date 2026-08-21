"""machine_master の配置絞り込みテスト。

実行:
    python -m unittest tests.test_machine_master
    python -m unittest tests.test_machine_master -v
"""

import unittest

from machine_master import UnitAssignment, filter_assignments


def _assignment(**kwargs):
    defaults = dict(
        machine_id="M0001",
        store_id="100928",
        model="L ToLOVEるﾀﾞｰｸﾈｽver.8.7",
        unit=3075,
        valid_from=None,
        valid_to=None,
    )
    defaults.update(kwargs)
    return UnitAssignment(**defaults)


MASTER = [
    _assignment(machine_id="M0001", unit=3075),
    _assignment(machine_id="M0002", unit=3076),
    _assignment(
        machine_id="M0061",
        model="L ﾏｷﾞｱﾚｺｰﾄﾞ",
        unit=2046,
    ),
    _assignment(
        machine_id="M0100",
        store_id="200001",
        model="L ﾏｷﾞｱﾚｺｰﾄﾞ",
        unit=1001,
    ),
]


class FilterAssignmentsTest(unittest.TestCase):
    def test_no_filter_returns_all(self):
        filtered = filter_assignments(MASTER)
        self.assertEqual(
            [a.machine_id for a in filtered],
            ["M0001", "M0002", "M0061", "M0100"],
        )

    def test_store_id_only(self):
        filtered = filter_assignments(MASTER, store_id="100928")
        self.assertEqual(
            [a.machine_id for a in filtered],
            ["M0001", "M0002", "M0061"],
        )

    def test_model_only(self):
        filtered = filter_assignments(MASTER, model="L ﾏｷﾞｱﾚｺｰﾄﾞ")
        self.assertEqual(
            [a.machine_id for a in filtered],
            ["M0061", "M0100"],
        )

    def test_store_and_model(self):
        filtered = filter_assignments(
            MASTER,
            store_id="100928",
            model="L ﾏｷﾞｱﾚｺｰﾄﾞ",
        )
        self.assertEqual([a.machine_id for a in filtered], ["M0061"])

    def test_model_ignores_width_and_spaces(self):
        filtered = filter_assignments(
            MASTER,
            store_id="100928",
            model="Ｌ　マギアレコード",
        )
        self.assertEqual([a.machine_id for a in filtered], ["M0061"])

    def test_unknown_store_id_raises(self):
        with self.assertRaises(ValueError) as ctx:
            filter_assignments(MASTER, store_id="999999")
        self.assertIn("store_id=999999", str(ctx.exception))
        self.assertIn("100928", str(ctx.exception))

    def test_unknown_model_in_store_raises(self):
        with self.assertRaises(ValueError) as ctx:
            filter_assignments(
                MASTER,
                store_id="200001",
                model="L ToLOVEるﾀﾞｰｸﾈｽver.8.7",
            )
        self.assertIn("model=", str(ctx.exception))
        self.assertIn("L ﾏｷﾞｱﾚｺｰﾄﾞ", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
