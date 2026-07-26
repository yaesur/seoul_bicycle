import unittest

from src.prioritization import Station, allocate_by_priority, rank_candidates


class PrioritizationTest(unittest.TestCase):
    def setUp(self):
        self.stations = [
            Station("과잉", 37.50, 127.00, 20),
            Station("가까운부족", 37.51, 127.00, -10),
            Station("먼부족", 37.54, 127.00, -10),
        ]

    def test_closer_equal_imbalance_has_higher_priority(self):
        candidates = rank_candidates(self.stations, 10)
        self.assertEqual(candidates[0].target.name, "가까운부족")

    def test_allocation_respects_budget_supply_and_demand(self):
        orders = allocate_by_priority(self.stations, rank_candidates(self.stations, 10), 15)
        self.assertEqual(sum(amount for _, amount in orders), 15)
        self.assertLessEqual(sum(amount for candidate, amount in orders if candidate.source.name == "과잉"), 20)


if __name__ == "__main__":
    unittest.main()
