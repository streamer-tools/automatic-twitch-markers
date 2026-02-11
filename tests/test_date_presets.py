"""
Tests for date preset computation in multi-fetch dialog.

Tests the pure helper function that computes preset date ranges,
avoiding tkinter event loop testing.
"""

import unittest
from datetime import date, timedelta

from twitch_marker_agent.ui.date_range_dialog import compute_preset_dates


class TestComputePresetDates(unittest.TestCase):
    """Tests for compute_preset_dates pure function."""

    def setUp(self):
        """Set up test fixtures."""
        self.today = date(2026, 2, 9)
        self.earliest_allowed = self.today - timedelta(days=60)

    def test_preset_7_days(self):
        """Preset 7 days: start=today-7, end=today."""
        start, end = compute_preset_dates(
            days=7,
            today=self.today,
            earliest_allowed=self.earliest_allowed,
        )

        self.assertEqual(end, self.today)
        self.assertEqual(start, self.today - timedelta(days=7))

    def test_preset_14_days(self):
        """Preset 14 days: start=today-14, end=today."""
        start, end = compute_preset_dates(
            days=14,
            today=self.today,
            earliest_allowed=self.earliest_allowed,
        )

        self.assertEqual(end, self.today)
        self.assertEqual(start, self.today - timedelta(days=14))

    def test_preset_30_days(self):
        """Preset 30 days: start=today-30, end=today."""
        start, end = compute_preset_dates(
            days=30,
            today=self.today,
            earliest_allowed=self.earliest_allowed,
        )

        self.assertEqual(end, self.today)
        self.assertEqual(start, self.today - timedelta(days=30))

    def test_preset_60_days(self):
        """Preset 60 days: start=today-60 (=earliest), end=today."""
        start, end = compute_preset_dates(
            days=60,
            today=self.today,
            earliest_allowed=self.earliest_allowed,
        )

        self.assertEqual(end, self.today)
        self.assertEqual(start, self.earliest_allowed)

    def test_preset_clamps_to_earliest(self):
        """Preset exceeding max days should clamp to earliest_allowed."""
        start, end = compute_preset_dates(
            days=90,  # exceeds 60 day limit
            today=self.today,
            earliest_allowed=self.earliest_allowed,
        )

        self.assertEqual(end, self.today)
        self.assertEqual(start, self.earliest_allowed)
        # start should NOT be today-90, should be clamped
        self.assertNotEqual(start, self.today - timedelta(days=90))

    def test_preset_0_days(self):
        """Preset 0 days: start=today, end=today (same day)."""
        start, end = compute_preset_dates(
            days=0,
            today=self.today,
            earliest_allowed=self.earliest_allowed,
        )

        self.assertEqual(end, self.today)
        self.assertEqual(start, self.today)

    def test_end_always_equals_today(self):
        """End date is always today regardless of days value."""
        for days in [1, 7, 14, 30, 60, 100]:
            start, end = compute_preset_dates(
                days=days,
                today=self.today,
                earliest_allowed=self.earliest_allowed,
            )
            self.assertEqual(end, self.today, f"end should be today for days={days}")


if __name__ == "__main__":
    unittest.main()
