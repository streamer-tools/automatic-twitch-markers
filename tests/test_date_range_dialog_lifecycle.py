"""Tests for DateRangeDialog focus/callback lifecycle behavior."""

import tkinter as tk
import unittest

from twitch_marker_agent.ui.date_range_dialog import DateRangeDialog


class _FakeDialog:
    """Minimal fake dialog for lifecycle tests without a GUI loop."""

    def __init__(
        self,
        exists: bool = True,
        fail_cancel_ids: set[str] | None = None,
        fail_focus: bool = False,
    ) -> None:
        self._exists = exists
        self._fail_cancel_ids = fail_cancel_ids or set()
        self._fail_focus = fail_focus
        self.after_cancel_calls: list[str] = []
        self.after_idle_calls: list[object] = []
        self.lift_called = 0
        self.focus_force_called = 0
        self.destroy_called = 0

    def winfo_exists(self) -> bool:
        """Return whether dialog is considered alive."""
        return self._exists

    def lift(self) -> None:
        """Record lift calls."""
        self.lift_called += 1

    def focus_force(self) -> None:
        """Record focus_force calls and optionally fail."""
        if self._fail_focus:
            raise tk.TclError("focus failed")
        self.focus_force_called += 1

    def after_idle(self, callback: object) -> str:
        """Record after_idle callback and return fake callback id."""
        self.after_idle_calls.append(callback)
        return "focus_after_id"

    def after_cancel(self, callback_id: str) -> None:
        """Record after_cancel and optionally fail for selected ids."""
        self.after_cancel_calls.append(callback_id)
        if callback_id in self._fail_cancel_ids:
            raise tk.TclError("cancel failed")

    def destroy(self) -> None:
        """Record destroy calls."""
        self.destroy_called += 1


class TestDateRangeDialogLifecycle(unittest.TestCase):
    """Tests for lifecycle callbacks in DateRangeDialog."""

    def test_activate_dialog_schedules_focus_callback(self) -> None:
        """Dialog activation should schedule start-entry focus callback."""
        dialog = DateRangeDialog(max_days_back=60)
        fake_dialog = _FakeDialog()
        dialog.dialog = fake_dialog  # type: ignore[assignment]
        dialog._activate_after_id = "activate_after_id"

        dialog._activate_dialog()

        self.assertIsNone(dialog._activate_after_id)
        self.assertEqual(dialog._focus_after_id, "focus_after_id")
        self.assertEqual(fake_dialog.lift_called, 1)
        self.assertEqual(fake_dialog.focus_force_called, 1)
        self.assertEqual(len(fake_dialog.after_idle_calls), 1)

    def test_activate_dialog_noops_when_dialog_missing(self) -> None:
        """Activation should no-op if dialog is not available."""
        dialog = DateRangeDialog(max_days_back=60)
        dialog.dialog = None
        dialog._activate_after_id = "activate_after_id"

        dialog._activate_dialog()

        self.assertIsNone(dialog._activate_after_id)
        self.assertIsNone(dialog._focus_after_id)

    def test_activate_dialog_noops_when_dialog_not_alive(self) -> None:
        """Activation should no-op if dialog widget no longer exists."""
        dialog = DateRangeDialog(max_days_back=60)
        fake_dialog = _FakeDialog(exists=False)
        dialog.dialog = fake_dialog  # type: ignore[assignment]
        dialog._activate_after_id = "activate_after_id"

        dialog._activate_dialog()

        self.assertIsNone(dialog._activate_after_id)
        self.assertIsNone(dialog._focus_after_id)
        self.assertEqual(fake_dialog.after_idle_calls, [])

    def test_activate_dialog_handles_focus_error(self) -> None:
        """Activation should swallow Tcl focus errors safely."""
        dialog = DateRangeDialog(max_days_back=60)
        fake_dialog = _FakeDialog(fail_focus=True)
        dialog.dialog = fake_dialog  # type: ignore[assignment]
        dialog._activate_after_id = "activate_after_id"

        dialog._activate_dialog()

        self.assertIsNone(dialog._activate_after_id)
        self.assertIsNone(dialog._focus_after_id)
        self.assertEqual(fake_dialog.after_idle_calls, [])

    def test_close_dialog_cancels_activate_and_focus_callbacks(self) -> None:
        """Close should cancel pending callback ids before destroy."""
        dialog = DateRangeDialog(max_days_back=60)
        fake_dialog = _FakeDialog()
        dialog.dialog = fake_dialog  # type: ignore[assignment]
        dialog._activate_after_id = "activate_after_id"
        dialog._focus_after_id = "focus_after_id"

        dialog._close_dialog()

        self.assertEqual(
            fake_dialog.after_cancel_calls,
            ["activate_after_id", "focus_after_id"],
        )
        self.assertIsNone(dialog._activate_after_id)
        self.assertIsNone(dialog._focus_after_id)
        self.assertEqual(fake_dialog.destroy_called, 1)

    def test_close_dialog_ignores_cancel_errors(self) -> None:
        """Close should still destroy when callback cancel raises TclError."""
        dialog = DateRangeDialog(max_days_back=60)
        fake_dialog = _FakeDialog(
            fail_cancel_ids={"activate_after_id", "focus_after_id"}
        )
        dialog.dialog = fake_dialog  # type: ignore[assignment]
        dialog._activate_after_id = "activate_after_id"
        dialog._focus_after_id = "focus_after_id"

        dialog._close_dialog()

        self.assertEqual(fake_dialog.destroy_called, 1)
        self.assertIsNone(dialog._activate_after_id)
        self.assertIsNone(dialog._focus_after_id)


if __name__ == "__main__":
    unittest.main()
