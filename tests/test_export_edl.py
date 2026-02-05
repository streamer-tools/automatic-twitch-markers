"""
Tests for EDL export functionality.

Tests verify:
- EDL header format (TITLE:, FCM:)
- Event line format with correct timecode
- Resolve marker metadata lines
- Timecode offset (0s vs 3600s)
- Timestamp edge cases
- File naming conventions and fallbacks
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from twitch_marker_agent.core.export_edl import (
    add_one_frame,
    export_markers_edl,
    format_marker_metadata,
    generate_edl_filename,
    sanitize_title,
    seconds_to_timecode,
    timecode_to_seconds,
)
from twitch_marker_agent.core.markers_api import Marker


class TestSecondsToTimecode(unittest.TestCase):
    """Tests for seconds_to_timecode conversion."""

    def test_zero_seconds_no_offset(self) -> None:
        """0 seconds with no offset should produce 00:00:00:00."""
        self.assertEqual(seconds_to_timecode(0, 24, 0), "00:00:00:00")

    def test_zero_seconds_with_3600_offset(self) -> None:
        """0 seconds with 3600s offset should produce 01:00:00:00."""
        self.assertEqual(seconds_to_timecode(0, 24, 3600), "01:00:00:00")

    def test_60_seconds_no_offset(self) -> None:
        """60 seconds with no offset should produce 00:01:00:00."""
        self.assertEqual(seconds_to_timecode(60, 24, 0), "00:01:00:00")

    def test_60_seconds_with_3600_offset(self) -> None:
        """60 seconds with 3600s offset should produce 01:01:00:00."""
        self.assertEqual(seconds_to_timecode(60, 24, 3600), "01:01:00:00")

    def test_3661_seconds_no_offset(self) -> None:
        """3661 seconds should produce 01:01:01:00."""
        self.assertEqual(seconds_to_timecode(3661, 24, 0), "01:01:01:00")

    def test_3661_seconds_with_3600_offset(self) -> None:
        """3661 seconds with +1h offset should produce 02:01:01:00."""
        self.assertEqual(seconds_to_timecode(3661, 24, 3600), "02:01:01:00")

    def test_59_seconds(self) -> None:
        """59 seconds should produce 00:00:59:00."""
        self.assertEqual(seconds_to_timecode(59, 24, 0), "00:00:59:00")

    def test_3599_seconds(self) -> None:
        """3599 seconds should produce 00:59:59:00."""
        self.assertEqual(seconds_to_timecode(3599, 24, 0), "00:59:59:00")

    def test_negative_clamps_to_zero(self) -> None:
        """Negative position should clamp to 00:00:00:00."""
        self.assertEqual(seconds_to_timecode(-100, 24, 0), "00:00:00:00")


class TestTimecodeToSeconds(unittest.TestCase):
    """Tests for timecode_to_seconds parsing."""

    def test_one_hour(self) -> None:
        """01:00:00:00 should return 3600."""
        self.assertEqual(timecode_to_seconds("01:00:00:00"), 3600)

    def test_59_seconds(self) -> None:
        """00:00:59:00 should return 59."""
        self.assertEqual(timecode_to_seconds("00:00:59:00"), 59)

    def test_one_minute(self) -> None:
        """00:01:00:00 should return 60."""
        self.assertEqual(timecode_to_seconds("00:01:00:00"), 60)

    def test_3661_seconds(self) -> None:
        """01:01:01:00 should return 3661."""
        self.assertEqual(timecode_to_seconds("01:01:01:00"), 3661)

    def test_invalid_format_single_digit(self) -> None:
        """1:00:00:00 should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            timecode_to_seconds("1:00:00:00")
        self.assertIn("Invalid timecode", str(ctx.exception))

    def test_invalid_minutes_bounds(self) -> None:
        """00:60:00:00 should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            timecode_to_seconds("00:60:00:00")
        self.assertIn("minutes must be 00-59", str(ctx.exception))

    def test_invalid_seconds_bounds(self) -> None:
        """00:00:60:00 should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            timecode_to_seconds("00:00:60:00")
        self.assertIn("seconds must be 00-59", str(ctx.exception))

    def test_non_zero_frames_raises(self) -> None:
        """01:00:00:01 should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            timecode_to_seconds("01:00:00:01")
        self.assertIn("frames must be 00", str(ctx.exception))

    def test_missing_component(self) -> None:
        """01:00:00 should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            timecode_to_seconds("01:00:00")
        self.assertIn("expected HH:MM:SS:FF", str(ctx.exception))


class TestAddOneFrame(unittest.TestCase):
    """Tests for add_one_frame function."""

    def test_converts_00_to_01(self) -> None:
        """Should change :00 to :01."""
        self.assertEqual(add_one_frame("01:30:00:00"), "01:30:00:01")

    def test_preserves_non_zero_frame(self) -> None:
        """Should not change non-00 frames."""
        self.assertEqual(add_one_frame("01:30:00:05"), "01:30:00:05")


class TestSanitizeTitle(unittest.TestCase):
    """Tests for title sanitization."""

    def test_removes_illegal_chars(self) -> None:
        """Should remove illegal filesystem characters."""
        self.assertEqual(sanitize_title("Epic: The <Game>"), "Epic The Game")

    def test_collapses_spaces(self) -> None:
        """Should collapse multiple spaces."""
        self.assertEqual(sanitize_title("hello   world"), "hello world")


class TestGenerateEdlFilename(unittest.TestCase):
    """Tests for EDL filename generation."""

    def test_preferred_format(self) -> None:
        """Should use preferred format with title and date."""
        filename = generate_edl_filename(
            video_id="123",
            stream_title="Epic Gaming Session",
            stream_date="2026-02-04",
        )
        self.assertEqual(filename, "2026-02-04 Epic Gaming Session - Twitch Markers.edl")

    def test_fallback_format(self) -> None:
        """Should fallback to video_id when title missing."""
        filename = generate_edl_filename(
            video_id="1234567890",
            stream_title=None,
            stream_date="2026-02-04",
        )
        self.assertEqual(filename, "1234567890_2026-02-04 - Twitch Markers.edl")


class TestFormatMarkerMetadata(unittest.TestCase):
    """Tests for Resolve marker metadata line formatting."""

    def test_formats_metadata_line(self) -> None:
        """Should format metadata with color, description, user info."""
        marker = Marker(
            id="m1",
            created_at="2026-02-04T10:00:00Z",
            position_seconds=5400,
            description="Boss fight starts",
            user_type="broadcaster",
            username="teststreamer",
        )
        metadata = format_marker_metadata(marker)
        self.assertEqual(
            metadata,
            " |C:ResolveColorBlue |M:Boss fight starts by teststreamer [broadcaster] |D:1",
        )

    def test_handles_empty_description(self) -> None:
        """Should use 'Marker' for empty description."""
        marker = Marker(
            id="m1",
            created_at="2026-02-04T10:00:00Z",
            position_seconds=0,
            description="",
            user_type="broadcaster",
            username="streamer",
        )
        metadata = format_marker_metadata(marker)
        self.assertIn("|M:Marker by", metadata)


class TestExportMarkersEdl(unittest.TestCase):
    """Tests for export_markers_edl function."""

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

    def test_header_format(self) -> None:
        """EDL should have TITLE: and FCM: header lines."""
        markers = self._create_markers()
        file_path = export_markers_edl(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            stream_title="Test Stream",
            stream_date="2026-02-04",
            timecode_offset_seconds=0,
        )

        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        self.assertIn("TITLE:", lines[0])
        self.assertEqual(lines[1], "FCM: NON-DROP FRAME")

    def test_event_line_format(self) -> None:
        """Event lines should have correct format."""
        markers = self._create_markers()
        file_path = export_markers_edl(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            timecode_offset_seconds=0,
        )

        content = file_path.read_text(encoding="utf-8")
        # First marker at 5400s = 01:30:00
        self.assertIn("001  001      V     C        01:30:00:00 01:30:00:01", content)

    def test_marker_metadata_line(self) -> None:
        """Should include Resolve marker metadata lines."""
        markers = self._create_markers()
        file_path = export_markers_edl(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            timecode_offset_seconds=0,
        )

        content = file_path.read_text(encoding="utf-8")
        self.assertIn("|C:ResolveColorBlue", content)
        self.assertIn("|M:Boss fight starts by teststreamer [broadcaster]", content)
        self.assertIn("|D:1", content)

    def test_offset_3600_seconds(self) -> None:
        """With +3600 offset, timecodes should be +1 hour."""
        markers = [
            Marker(
                id="m1",
                created_at="2026-02-04T10:00:00Z",
                position_seconds=0,  # 00:00:00
                description="Start",
                user_type="broadcaster",
                username="streamer",
            )
        ]
        file_path = export_markers_edl(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            timecode_offset_seconds=3600,
        )

        content = file_path.read_text(encoding="utf-8")
        # 0s + 3600s offset = 01:00:00:00
        self.assertIn("01:00:00:00 01:00:00:01", content)

    def test_offset_0_seconds(self) -> None:
        """With 0 offset, timecodes should be raw."""
        markers = [
            Marker(
                id="m1",
                created_at="2026-02-04T10:00:00Z",
                position_seconds=0,
                description="Start",
                user_type="broadcaster",
                username="streamer",
            )
        ]
        file_path = export_markers_edl(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            timecode_offset_seconds=0,
        )

        content = file_path.read_text(encoding="utf-8")
        self.assertIn("00:00:00:00 00:00:00:01", content)

    def test_marker_duration_is_1_frame(self) -> None:
        """Marker duration should be 1 frame (:00 to :01)."""
        markers = self._create_markers()
        file_path = export_markers_edl(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            timecode_offset_seconds=0,
        )

        content = file_path.read_text(encoding="utf-8")
        # Check that all timecodes end with :00 and :01
        lines = [l for l in content.split("\n") if "001      V" in l]
        for line in lines:
            self.assertIn(":00", line)
            self.assertIn(":01", line)

    def test_file_naming_preferred(self) -> None:
        """Should use preferred filename format."""
        markers = self._create_markers()
        file_path = export_markers_edl(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            stream_title="Epic Gaming Session",
            stream_date="2026-02-04",
        )

        self.assertEqual(
            file_path.name,
            "2026-02-04 Epic Gaming Session - Twitch Markers.edl",
        )

    def test_file_naming_fallback(self) -> None:
        """Should use fallback filename format when title missing."""
        markers = self._create_markers()
        file_path = export_markers_edl(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="1234567890",
            stream_title=None,
            stream_date="2026-02-04",
        )

        self.assertEqual(
            file_path.name,
            "1234567890_2026-02-04 - Twitch Markers.edl",
        )


class TestExportEdlLogging(unittest.TestCase):
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

    def test_no_tokens_in_logs(self) -> None:
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

        export_markers_edl(
            markers=markers,
            output_path=self.output_path,
            config=self.config,
            video_id="123",
            logger=mock_logger,
        )

        for method_name in ["info", "debug", "warning", "error"]:
            method = getattr(mock_logger, method_name)
            for call in method.call_args_list:
                args = call.args if call.args else ()
                all_args = " ".join(str(a) for a in args)
                self.assertNotIn("token", all_args.lower())
                self.assertNotIn("secret", all_args.lower())
                self.assertNotIn("bearer", all_args.lower())


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    unittest.main()
