"""
Unit tests for retry utility with exponential backoff.
"""

import unittest
from unittest.mock import MagicMock

from twitch_marker_agent.core.retry import (
    RetryError,
    calculate_backoff,
    retry_with_backoff,
)


class TestCalculateBackoff(unittest.TestCase):
    """Tests for calculate_backoff function."""

    def test_exponential_growth(self) -> None:
        """Test that backoff grows exponentially."""
        base_delay = 1.0
        max_delay = 60.0

        # Without jitter, should be exact powers of 2
        delay_0 = calculate_backoff(0, base_delay, max_delay, jitter=False)
        delay_1 = calculate_backoff(1, base_delay, max_delay, jitter=False)
        delay_2 = calculate_backoff(2, base_delay, max_delay, jitter=False)

        self.assertEqual(delay_0, 1.0)  # 1 * 2^0 = 1
        self.assertEqual(delay_1, 2.0)  # 1 * 2^1 = 2
        self.assertEqual(delay_2, 4.0)  # 1 * 2^2 = 4

    def test_max_delay_cap(self) -> None:
        """Test that delay is capped at max_delay."""
        base_delay = 1.0
        max_delay = 10.0

        # Attempt 5 would be 1 * 2^5 = 32, but should be capped
        delay = calculate_backoff(5, base_delay, max_delay, jitter=False)
        self.assertEqual(delay, 10.0)

    def test_jitter_adds_variance(self) -> None:
        """Test that jitter adds variance to delay."""
        base_delay = 10.0
        max_delay = 60.0

        # Run multiple times and check for variance
        delays = [calculate_backoff(0, base_delay, max_delay, jitter=True) for _ in range(10)]

        # With jitter, delays should vary
        self.assertTrue(len(set(delays)) > 1, "Jitter should produce varying delays")

        # All delays should be within ±25% of base
        for delay in delays:
            self.assertGreaterEqual(delay, base_delay * 0.75)
            self.assertLessEqual(delay, base_delay * 1.25)

    def test_never_negative(self) -> None:
        """Test that backoff delay is never negative."""
        # Edge case with very small base delay and jitter
        for _ in range(100):
            delay = calculate_backoff(0, 0.1, 60.0, jitter=True)
            self.assertGreaterEqual(delay, 0)


class TestRetryWithBackoff(unittest.TestCase):
    """Tests for retry_with_backoff function."""

    def test_success_on_first_attempt(self) -> None:
        """Test that successful function returns immediately."""
        mock_fn = MagicMock(return_value="success")

        result = retry_with_backoff(mock_fn, max_attempts=5)

        self.assertEqual(result, "success")
        mock_fn.assert_called_once()

    def test_retry_on_failure(self) -> None:
        """Test that function retries on exception."""
        mock_fn = MagicMock(side_effect=[ValueError("fail"), ValueError("fail"), "success"])

        result = retry_with_backoff(
            mock_fn,
            max_attempts=5,
            base_delay=0.01,  # Fast for testing
            retryable_exceptions=(ValueError,),
        )

        self.assertEqual(result, "success")
        self.assertEqual(mock_fn.call_count, 3)

    def test_raises_retry_error_after_max_attempts(self) -> None:
        """Test that RetryError is raised when all attempts fail."""
        mock_fn = MagicMock(side_effect=ValueError("always fails"))

        with self.assertRaises(RetryError) as ctx:
            retry_with_backoff(
                mock_fn,
                max_attempts=3,
                base_delay=0.01,
                retryable_exceptions=(ValueError,),
            )

        self.assertEqual(mock_fn.call_count, 3)
        self.assertIsInstance(ctx.exception.last_exception, ValueError)

    def test_non_retryable_exception_raises_immediately(self) -> None:
        """Test that non-retryable exceptions are not caught."""
        mock_fn = MagicMock(side_effect=TypeError("not retryable"))

        with self.assertRaises(TypeError):
            retry_with_backoff(
                mock_fn,
                max_attempts=5,
                base_delay=0.01,
                retryable_exceptions=(ValueError,),  # TypeError not included
            )

        # Should only try once
        mock_fn.assert_called_once()

    def test_logger_receives_warnings(self) -> None:
        """Test that logger receives retry warnings."""
        mock_fn = MagicMock(side_effect=[ValueError("fail"), "success"])
        mock_logger = MagicMock()

        retry_with_backoff(
            mock_fn,
            max_attempts=5,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
            logger=mock_logger,
        )

        # Logger should have been called with warning
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        self.assertIn("Attempt 1/5", warning_msg)
        self.assertIn("fail", warning_msg)

    def test_returns_correct_type(self) -> None:
        """Test that return value type is preserved."""
        # Test with different return types
        list_fn = MagicMock(return_value=[1, 2, 3])
        result = retry_with_backoff(list_fn)
        self.assertEqual(result, [1, 2, 3])

        dict_fn = MagicMock(return_value={"key": "value"})
        result = retry_with_backoff(dict_fn)
        self.assertEqual(result, {"key": "value"})


class TestRetryError(unittest.TestCase):
    """Tests for RetryError exception."""

    def test_error_message(self) -> None:
        """Test that error contains message."""
        error = RetryError("Test message")
        self.assertEqual(str(error), "Test message")

    def test_last_exception_stored(self) -> None:
        """Test that last_exception is accessible."""
        original = ValueError("original error")
        error = RetryError("Wrapped", last_exception=original)

        self.assertIs(error.last_exception, original)

    def test_last_exception_none(self) -> None:
        """Test that last_exception can be None."""
        error = RetryError("No original")
        self.assertIsNone(error.last_exception)


if __name__ == "__main__":
    unittest.main()
