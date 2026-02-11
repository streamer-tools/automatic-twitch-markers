"""
Tests for date range validation helpers.

Tests the pure helper functions for date range validation,
avoiding tkinter event loop testing.
"""

import unittest
from datetime import date, timedelta

from twitch_marker_agent.ui.date_range_dialog import (
    compute_allowed_window,
    validate_date_in_range,
    validate_date_range_order,
)


class TestComputeAllowedWindow(unittest.TestCase):
    """Tests for compute_allowed_window pure function."""

    def test_computes_60_day_window(self):
        """Compute 60-day window from today."""
        today = date(2026, 2, 9)
        earliest, latest = compute_allowed_window(today, max_days_back=60)
        self.assertEqual(latest, today)
        self.assertEqual(earliest, date(2025, 12, 11))  # 60 days back

    def test_computes_7_day_window(self):
        """Compute 7-day window from today."""
        today = date(2026, 2, 9)
        earliest, latest = compute_allowed_window(today, max_days_back=7)
        self.assertEqual(latest, today)
        self.assertEqual(earliest, date(2026, 2, 2))  # 7 days back

    def test_computes_30_day_window(self):
        """Compute 30-day window from today."""
        today = date(2026, 2, 9)
        earliest, latest = compute_allowed_window(today, max_days_back=30)
        self.assertEqual(latest, today)
        self.assertEqual(earliest, date(2026, 1, 10))  # 30 days back

    def test_zero_days_back_returns_today(self):
        """Max days back of 0 should return today for both."""
        today = date(2026, 2, 9)
        earliest, latest = compute_allowed_window(today, max_days_back=0)
        self.assertEqual(latest, today)
        self.assertEqual(earliest, today)


class TestValidateDateInRange(unittest.TestCase):
    """Tests for validate_date_in_range pure function."""

    def test_valid_date_passes(self):
        """Date within range should not raise."""
        d = date(2026, 2, 5)
        min_d = date(2026, 2, 1)
        max_d = date(2026, 2, 9)
        # Should not raise
        validate_date_in_range(d, min_d, max_d)

    def test_date_before_min_raises(self):
        """Date before min should raise ValueError."""
        d = date(2026, 1, 31)
        min_d = date(2026, 2, 1)
        max_d = date(2026, 2, 9)
        with self.assertRaises(ValueError) as ctx:
            validate_date_in_range(d, min_d, max_d)
        self.assertIn("cannot be earlier than", str(ctx.exception))

    def test_date_after_max_raises(self):
        """Date after max should raise ValueError."""
        d = date(2026, 2, 10)
        min_d = date(2026, 2, 1)
        max_d = date(2026, 2, 9)
        with self.assertRaises(ValueError) as ctx:
            validate_date_in_range(d, min_d, max_d)
        self.assertIn("cannot be later than", str(ctx.exception))

    def test_boundary_dates_pass(self):
        """Min and max boundary dates should pass."""
        min_d = date(2026, 2, 1)
        max_d = date(2026, 2, 9)
        # Min boundary
        validate_date_in_range(min_d, min_d, max_d)
        # Max boundary
        validate_date_in_range(max_d, min_d, max_d)

    def test_custom_field_name_in_error(self):
        """Custom field name should appear in error message."""
        d = date(2026, 1, 31)
        min_d = date(2026, 2, 1)
        max_d = date(2026, 2, 9)
        with self.assertRaises(ValueError) as ctx:
            validate_date_in_range(d, min_d, max_d, field_name="Custom Field")
        self.assertIn("Custom Field", str(ctx.exception))

    def test_single_day_range(self):
        """Single-day range (min=max) should only allow that day."""
        target = date(2026, 2, 5)
        # Exact day should pass
        validate_date_in_range(target, target, target)
        # Day before should fail
        with self.assertRaises(ValueError):
            validate_date_in_range(date(2026, 2, 4), target, target)
        # Day after should fail
        with self.assertRaises(ValueError):
            validate_date_in_range(date(2026, 2, 6), target, target)


class TestValidateDateRangeOrder(unittest.TestCase):
    """Tests for validate_date_range_order pure function."""

    def test_start_before_end_passes(self):
        """Start before end should pass."""
        start = date(2026, 2, 1)
        end = date(2026, 2, 9)
        # Should not raise
        validate_date_range_order(start, end)

    def test_start_equals_end_passes(self):
        """Start equal to end should pass (same-day range)."""
        start = date(2026, 2, 5)
        end = date(2026, 2, 5)
        # Should not raise
        validate_date_range_order(start, end)

    def test_start_after_end_raises(self):
        """Start after end should raise ValueError."""
        start = date(2026, 2, 10)
        end = date(2026, 2, 5)
        with self.assertRaises(ValueError) as ctx:
            validate_date_range_order(start, end)
        self.assertIn("must be before or equal to", str(ctx.exception))

    def test_error_message_contains_dates(self):
        """Error message should include both dates."""
        start = date(2026, 2, 10)
        end = date(2026, 2, 5)
        with self.assertRaises(ValueError) as ctx:
            validate_date_range_order(start, end)
        error_msg = str(ctx.exception)
        self.assertIn("2026-02-10", error_msg)
        self.assertIn("2026-02-05", error_msg)


if __name__ == "__main__":
    unittest.main()
