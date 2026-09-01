import unittest
from datetime import datetime
from hourly_heat_engine import HourlyHeatEngine

class TestHourlyHeatEngine(unittest.TestCase):
    def setUp(self):
        self.engine = HourlyHeatEngine("test_hourly_data.json")

    def test_hourly_multipliers(self):
        # Peak London kill zone hour (15:00 UTC+7)
        mult, desc = self.engine.get_hour_multiplier(15)
        self.assertGreaterEqual(mult, 1.0)
        self.assertIn("Peak", desc)

        # Record some wins
        dt = datetime(2026, 9, 1, 15, 30)
        self.engine.record_outcome(dt, 15.0)
        self.engine.record_outcome(dt, 20.0)
        self.engine.record_outcome(dt, 10.0)
        
        mult_after, desc_after = self.engine.get_hour_multiplier(15)
        self.assertEqual(mult_after, 1.20)
        self.assertIn("High-Winrate", desc_after)

    def tearDown(self):
        import os
        if os.path.exists("test_hourly_data.json"):
            os.remove("test_hourly_data.json")

if __name__ == '__main__':
    unittest.main()
