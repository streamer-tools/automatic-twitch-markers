"""
Tests for CSV export functionality.

Tests verify:
- Canonical 4-column format without a header row
- Timestamp formatting for edge cases
- Correct row value mapping
- File naming conventions and fallbacks
- UTF-8 BOM encoding
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from twitch_marker_agent.core.export_csv import (
    export_markers_csv,
    generate_csv_filename,
    sanitize_filename,
    seconds_to_timestamp,
)
from twitch_marker_agent.core.markers_api import Marker


class TestSecondsToTimestamp(unittest.TestCase):
    """Tests for seconds_to_timestamp conversion."""

    def test_zero_seconds(self) -> None:
        """0 seconds should produce 00:00:00."""
        self.assertEqual(seconds_to_timestamp(0), "00:00:00")

    def test_59_seconds(self) -> None:
        """59 seconds should produce 00:00:59."""
        self.assertEqual(seconds_to_timestamp(59), "00:00:59")

    def test_60_seconds_is_one_minute(self) -> None:
        """60 seconds should produce 00:01:00."""
        self.assertEqual(seconds_to_timestamp(60), "00:01:00")

    def test_3599_seconds(self) -> None:
        """3599 seconds should produce 00:59:59."""
        self.assertEqual(seconds_to_timestamp(3599), "00:59:59")

    def test_3600_seconds_is_one_hour(self) -> None:
        """3600 seconds should produce 01:00:00."""
        self.assertEqual(seconds_to_timestamp(3600), "01:00:00")

    def test_3661_seconds(self) -> None:
        """3661 seconds should produce 01:01:01."""
        self.assertEqual(seconds_to_timestamp(3661), "01:01:01")

    def test_long_stream_10_hours(self) -> None:
        """36000 seconds (10 hours) should produce 10:00:00."""
        self.assertEqual(seconds_to_timestamp(36000), "10:00:00")

    def test_very_long_stream(self) -> None:
        """Test streams over 24 hours (86400+ seconds)."""
        # 25 hours = 90000 seconds
        self.assertEqual(seconds_to_timestamp(90000), "25:00:00")

    def test_negative_seconds_clamps_to_zero(self) -> None:
        """Negative seconds should clamp to 00:00:00."""
        self.assertEqual(seconds_to_timestamp(-100), "00:00:00")


class TestSanitizeFilename(unittest.TestCase):
    """Tests for filename sanitization."""

    def test_removes_backslash(self) -> None:
        """Should remove backslash."""
        self.assertEqual(sanitize_filename("hello\\world"), "helloworld")

    def test_removes_forward_slash(self) -> None:
        """Should remove forward slash."""
        self.assertEqual(sanitize_filename("hello/world"), "helloworld")

    def test_removes_colon(self) -> None:
        """Should remove colon."""
        self.assertEqual(sanitize_filename("hello:world"), "helloworld")

    def test_removes_asterisk(self) -> None:
        """Should remove asterisk."""
        self.assertEqual(sanitize_filename("hello*world"), "helloworld")

    def test_removes_question_mark(self) -> None:
        """Should remove question mark."""
        self.assertEqual(sanitize_filename("hello?world"), "helloworld")

    def test_removes_quotes(self) -> None:
        """Should remove double quotes."""
        self.assertEqual(sanitize_filename('hello"world'), "helloworld")

    def test_removes_angle_brackets(self) -> None:
        """Should remove angle brackets."""
        self.assertEqual(sanitize_filename("hello<world>"), "helloworld")

    def test_removes_pipe(self) -> None:
        """Should remove pipe character."""
        self.assertEqual(sanitize_filename("hello|world"), "helloworld")

    def test_collapses_multiple_spaces(self) -> None:
        """Should collapse multiple spaces to single space."""
        self.assertEqual(sanitize_filename("hello   world"), "hello world")

    def test_strips_whitespace(self) -> None:
        """Should strip leading and trailing whitespace."""
        self.assertEqual(sanitize_filename("  hello world  "), "hello world")

    def test_preserves_safe_characters(self) -> None:
        """Should preserve letters, numbers, spaces, dashes, underscores."""
        self.assertEqual(
            sanitize_filename("Epic Gaming Session - Day 1"),
            "Epic Gaming Session - Day 1",
        )


class TestGenerateCsvFilename(unittest.TestCase):
    """Tests for CSV filename generation."""

    def test_preferred_format_with_title_and_date(self) -> None:
        """Should use preferred format when title and date available."""
        filename = generate_csv_filename(
            video_id="123",
            stream_title="Epic Gaming Session",
            stream_date="2026-02-04",
        )
        self.assertEqual(filename, "2026-02-04 Epic Gaming Session - Twitch Markers.csv")

    def test_fallback_when_title_missing(self) -> None:
        """Should fallback to video_id when title missing."""
        filename = generate_csv_filename(
            video_id="1234567890",
            stream_title=None,
            stream_date="2026-02-04",
        )
        self.assertEqual(filename, "1234567890_2026-02-04 - Twitch Markers.csv")

    def test_fallback_when_title_empty(self) -> None:
        """Should fallback to video_id when title is empty string."""
        filename = generate_csv_filename(
            video_id="1234567890",
            stream_title="",
            stream_date="2026-02-04",
        )
        self.assertEqual(filename, "1234567890_2026-02-04 - Twitch Markers.csv")

    def test_fallback_when_title_only_illegal_chars(self) -> None:
        """Should fallback when title becomes empty after sanitization."""
        filename = generate_csv_filename(
            video_id="1234567890",
            stream_title="<>:?",
            stream_date="2026-02-04",
        )
        self.assertEqual(filename, "1234567890_2026-02-04 - Twitch Markers.csv")

    def test_sanitizes_title_in_filename(self) -> None:
        """Should sanitize illegal characters from title."""
        filename = generate_csv_filename(
            video_id="123",
            stream_title="Epic: The <Game>",
            stream_date="2026-02-04",
        )
        self.assertEqual(filename, "2026-02-04 Epic The Game - Twitch Markers.csv")

    def test_uses_current_date_when_date_missing(self) -> None:
        """Should use current date when stream_date is None."""
        filename = generate_csv_filename(
            video_id="1234567890",
            stream_title=None,
            stream_date=None,
        )
        # Just check format, don't hardcode date
        self.assertRegex(filename, r"1234567890_\d{4}-\d{2}-\d{2} - Twitch Markers\.csv")


class TestExportMarkersCsv(unittest.TestCase):
    """Tests for export_markers_csv function."""

    def setUp(self) -> None:
        """Create temporary directory and mock config."""
        self.temp_dir = tempfile.mkdtemp()
        self.output_path = Path(self.temp_dir)
        self.config = MagicMock()
        self.config.timecode_fps = 24

    def tearDown(self) -> None:
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_markers(self) -> list[Marker]:
        """Create sample markers for testing."""
        return [
            Marker(
                id="marker1",
                created_at="2026-02-04T10:30:00Z",
                position_seconds=5400,  # 01:30:00
                description="Boss fight starts",
                user_type="broadcaster",
                username="teststreamer",
            ),
            Marker(
                id="marker2",
                created_at="2026-02-04T11:15:45Z",
                position_seconds=8145,  # 02:15:45
                description="Epic win moment",
                user_type="broadcaster",
                username="teststreamer",
            ),
        ]

    def test_first_row_is_marker_data_without_header(self) -> None:
        """First CSV row should be marker data (no header row)."""
        markers = self._create_markers()
        file_path = export_markers_csv(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            stream_date="2026-02-04",
        )

        with file_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            first_row = next(reader)

        self.assertEqual(len(first_row), 4)
        self.assertEqual(first_row[0], "01:30:00")
        self.assertEqual(first_row[1], "broadcaster")
        self.assertEqual(first_row[2], "teststreamer")
        self.assertEqual(first_row[3], "Boss fight starts")

    def test_data_rows_have_correct_values(self) -> None:
        """Data rows should map marker fields correctly."""
        markers = self._create_markers()
        file_path = export_markers_csv(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
        )

        with file_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 2)

        # First marker: 5400 seconds = 01:30:00
        self.assertEqual(rows[0][0], "01:30:00")
        self.assertEqual(rows[0][1], "broadcaster")
        self.assertEqual(rows[0][2], "teststreamer")
        self.assertEqual(rows[0][3], "Boss fight starts")

        # Second marker: 8145 seconds = 02:15:45
        self.assertEqual(rows[1][0], "02:15:45")
        self.assertEqual(rows[1][1], "broadcaster")
        self.assertEqual(rows[1][2], "teststreamer")
        self.assertEqual(rows[1][3], "Epic win moment")

    def test_utf8_bom_present(self) -> None:
        """CSV should have UTF-8 BOM for Excel compatibility."""
        markers = self._create_markers()
        file_path = export_markers_csv(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
        )

        with file_path.open("rb") as f:
            first_bytes = f.read(3)

        # UTF-8 BOM is EF BB BF
        self.assertEqual(first_bytes, b"\xef\xbb\xbf")

    def test_all_fields_quoted(self) -> None:
        """All fields should be quoted."""
        markers = self._create_markers()
        file_path = export_markers_csv(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
        )

        with file_path.open("r", encoding="utf-8-sig") as f:
            raw_content = f.read()

        self.assertIn('"01:30:00","broadcaster","teststreamer","Boss fight starts"', raw_content)

    def test_empty_markers_creates_empty_csv(self) -> None:
        """Empty marker list should create a CSV with no data rows."""
        file_path = export_markers_csv(
            markers=[],
            output_path=self.output_path,
            config=self.config,
            video_id="123",
        )

        with file_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 0)

    def test_description_with_comma_stays_in_single_column(self) -> None:
        """Descriptions with commas must remain intact when parsed."""
        markers = [
            Marker(
                id="marker1",
                created_at="2026-02-04T10:30:00Z",
                position_seconds=5400,
                description="Boss fight, phase 2 starts",
                user_type="broadcaster",
                username="teststreamer",
            )
        ]
        file_path = export_markers_csv(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
        )

        with file_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 4)
        self.assertEqual(rows[0][3], "Boss fight, phase 2 starts")

    def test_filename_uses_preferred_format(self) -> None:
        """Should use preferred filename format when title available."""
        markers = self._create_markers()
        file_path = export_markers_csv(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            stream_title="Epic Gaming Session",
            stream_date="2026-02-04",
        )

        self.assertEqual(
            file_path.name,
            "2026-02-04 Epic Gaming Session - Twitch Markers.csv",
        )

    def test_filename_uses_fallback_format(self) -> None:
        """Should use fallback filename format when title unavailable."""
        markers = self._create_markers()
        file_path = export_markers_csv(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="1234567890",
            stream_title=None,
            stream_date="2026-02-04",
        )

        self.assertEqual(
            file_path.name,
            "1234567890_2026-02-04 - Twitch Markers.csv",
        )


class TestExportCsvLogging(unittest.TestCase):
    """Tests to verify no sensitive data in logs."""

    def setUp(self) -> None:
        """Create temporary directory and mock config."""
        self.temp_dir = tempfile.mkdtemp()
        self.output_path = Path(self.temp_dir)
        self.config = MagicMock()
        self.config.timecode_fps = 24

    def tearDown(self) -> None:
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_no_token_in_log_calls(self) -> None:
        """Logger should not receive any token/auth data."""
        mock_logger = MagicMock()

        markers = [
            Marker(
                id="m1",
                created_at="2026-02-04T10:00:00Z",
                position_seconds=3600,
                description="Test marker",
                user_type="broadcaster",
                username="teststreamer",
            )
        ]

        export_markers_csv(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            logger=mock_logger,
        )

        # Check all log calls
        for method_name in ["info", "debug", "warning", "error"]:
            method = getattr(mock_logger, method_name)
            for call in method.call_args_list:
                args = call.args if call.args else ()
                all_args = " ".join(str(a) for a in args)
                # No tokens, secrets, or auth headers
                self.assertNotIn("token", all_args.lower())
                self.assertNotIn("secret", all_args.lower())
                self.assertNotIn("bearer", all_args.lower())


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    unittest.main()
