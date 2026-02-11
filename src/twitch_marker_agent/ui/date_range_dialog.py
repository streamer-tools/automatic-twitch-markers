"""
Tkinter date range dialog for multi-fetch feature.

Provides a dialog for selecting start and end dates using calendar
date pickers (ttkbootstrap.DateEntry) within the past 60 days from today.
Includes preset buttons for common date ranges and custom validation.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import ttkbootstrap as ttk
from ttkbootstrap import DateEntry


_SHARED_HIDDEN_ROOT: tk.Tk | None = None


def _get_shared_hidden_root() -> tk.Tk:
    """Return a process-wide hidden Tk root for parentless dialogs."""
    global _SHARED_HIDDEN_ROOT
    if _SHARED_HIDDEN_ROOT is None:
        _SHARED_HIDDEN_ROOT = tk.Tk()
        _SHARED_HIDDEN_ROOT.withdraw()
    return _SHARED_HIDDEN_ROOT


def compute_allowed_window(
    today: date,
    max_days_back: int
) -> tuple[date, date]:
    """
    Compute min and max allowed dates.
    
    Args:
        today: Current date (typically date.today()).
        max_days_back: Maximum days allowed in the past.
    
    Returns:
        (earliest_allowed, latest_allowed) tuple.
    """
    earliest = today - timedelta(days=max_days_back)
    return (earliest, today)


def validate_date_in_range(
    d: date,
    min_date: date,
    max_date: date,
    field_name: str = "Date"
) -> None:
    """
    Validate date is within allowed range.
    
    Args:
        d: Date to validate.
        min_date: Minimum allowed date (inclusive).
        max_date: Maximum allowed date (inclusive).
        field_name: Name of field for error message.
    
    Raises:
        ValueError: If date is out of range.
    """
    if d < min_date:
        raise ValueError(
            f"{field_name} ({d}) cannot be earlier than {min_date}"
        )
    if d > max_date:
        raise ValueError(
            f"{field_name} ({d}) cannot be later than {max_date}"
        )


def validate_date_range_order(
    start: date,
    end: date
) -> None:
    """
    Validate start date is before or equal to end date.
    
    Args:
        start: Start date.
        end: End date.
    
    Raises:
        ValueError: If start > end.
    """
    if start > end:
        raise ValueError(
            f"Start date ({start}) must be before or equal to end date ({end})"
        )


def compute_preset_dates(
    days: int,
    today: date,
    earliest_allowed: date,
) -> tuple[date, date]:
    """
    Compute start and end dates for a preset range.

    Args:
        days: Number of days back from today.
        today: Today's date (end date).
        earliest_allowed: Earliest allowed start date.

    Returns:
        (start_date, end_date) tuple with start clamped to earliest_allowed.
    """
    start_date = today - timedelta(days=days)
    # Clamp to earliest allowed
    if start_date < earliest_allowed:
        start_date = earliest_allowed
    return (start_date, today)


@dataclass(frozen=True)
class DateRangeDialogStyle:
    """
    Style options for DateRangeDialog appearance.

    These options are dialog-scoped and do not change global application theme.
    """

    theme: str = "flatly"
    title_bootstyle: str = "primary"
    date_entry_bootstyle: str = "primary"
    preset_button_bootstyle: str = "secondary"
    ok_button_bootstyle: str = "primary"
    cancel_button_bootstyle: str = "secondary"
    error_bootstyle: str = "danger"
    title_font: tuple[str, int, str] = ("Arial", 12, "bold")
    body_font: tuple[str, int] = ("Arial", 10)
    info_font: tuple[str, int] = ("Arial", 9)


class DateRangeDialog:
    """
    Tkinter dialog for selecting date range with calendar pickers.

    Uses ttkbootstrap.DateEntry for both start and end dates with custom validation.
    Opens a modal dialog with:
    - Calendar date pickers with styled appearance
    - Preset buttons (7/14/30/60 days)
    - Validation for start <= end and within allowed range

    Constraints:
    - start_date <= end_date
    - end_date <= today
    - start_date >= today - max_days_back

    Defaults:
    - end_date = today
    - start_date = today - 7 (or earliest_allowed if less)
    """

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel | None = None,
        max_days_back: int = 60,
        style: DateRangeDialogStyle | None = None,
    ) -> None:
        """
        Initialize date range dialog.

        Args:
            parent: Optional parent window.
            max_days_back: Maximum days back from today (default: 60).
            style: Optional dialog-only style overrides.
        """
        self.parent = parent
        self.max_days_back = max_days_back
        self.style = style or DateRangeDialogStyle()
        self.result: tuple[date, date] | None = None

        # Calculate defaults
        self.today = date.today()
        self.earliest_allowed, self.latest_allowed = compute_allowed_window(
            self.today, max_days_back
        )
        # Default: 7 days back, or earliest_allowed if that's less
        default_start = max(self.today - timedelta(days=7), self.earliest_allowed)
        self.default_start = default_start
        self.default_end = self.today

        # Track last valid values for revert-on-error
        self.last_valid_start = self.default_start
        self.last_valid_end = self.default_end

        # Will be set on show()
        self._hidden_root: tk.Tk | None = None
        self.dialog: tk.Toplevel | None = None
        self.start_entry: DateEntry | None = None
        self.end_entry: DateEntry | None = None
        self.error_label: ttk.Label | None = None
        self._ttk_style: ttk.Style | None = None
        self._focus_after_id: str | None = None

    def show(self) -> tuple[date, date] | None:
        """
        Show dialog and wait for user input.

        Returns:
            (start_date, end_date) if OK clicked, None if cancelled.
        """
        # Create window - handle parentless case properly for focus
        if self.parent:
            self.dialog = tk.Toplevel(self.parent)
        else:
            # Reuse one hidden root to avoid destroying the Tcl app between openings.
            self._hidden_root = _get_shared_hidden_root()
            self.dialog = tk.Toplevel(self._hidden_root)

        # Apply ttkbootstrap theme (dialog-only)
        self._ttk_style = ttk.Style(theme=self.style.theme)

        self.dialog.title("Select Date Range")
        self.dialog.geometry("440x320")
        self.dialog.resizable(False, False)

        # Center window
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (440 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (320 // 2)
        self.dialog.geometry(f"+{x}+{y}")

        # Title label
        title_label = ttk.Label(
            self.dialog,
            text="Fetch Multiple Stream Markers",
            bootstyle=self.style.title_bootstyle,
            font=self.style.title_font,
        )
        title_label.pack(pady=10)

        # Info label
        info_text = f"Select date range (max {self.max_days_back} days back from today)"
        info_label = ttk.Label(self.dialog, text=info_text, font=self.style.info_font)
        info_label.pack(pady=5)

        # Preset buttons frame
        preset_frame = ttk.Frame(self.dialog)
        preset_frame.pack(pady=8)

        ttk.Label(preset_frame, text="Quick select:", font=self.style.info_font).pack(
            side=tk.LEFT, padx=5
        )

        for days in [7, 14, 30, 60]:
            btn = ttk.Button(
                preset_frame,
                text=f"Last {days}",
                width=7,
                command=lambda d=days: self._set_preset(d),
                bootstyle=self.style.preset_button_bootstyle,
            )
            btn.pack(side=tk.LEFT, padx=2)

        # Date input frame
        input_frame = ttk.Frame(self.dialog)
        input_frame.pack(pady=10)

        # Start date with DateEntry
        ttk.Label(input_frame, text="Start Date:", font=self.style.body_font).grid(
            row=0, column=0, sticky="e", padx=5, pady=8
        )
        self.start_entry = DateEntry(
            input_frame,
            width=14,
            dateformat="%Y-%m-%d",
            bootstyle=self.style.date_entry_bootstyle,
            startdate=self.default_start,
        )
        self.start_entry.grid(row=0, column=1, padx=5, pady=8)

        # End date with DateEntry
        ttk.Label(input_frame, text="End Date:", font=self.style.body_font).grid(
            row=1, column=0, sticky="e", padx=5, pady=8
        )
        self.end_entry = DateEntry(
            input_frame,
            width=14,
            dateformat="%Y-%m-%d",
            bootstyle=self.style.date_entry_bootstyle,
            startdate=self.default_end,
        )
        self.end_entry.grid(row=1, column=1, padx=5, pady=8)

        # Error label (initially hidden)
        self.error_label = ttk.Label(
            self.dialog,
            text="",
            bootstyle=self.style.error_bootstyle,
            font=self.style.info_font,
            wraplength=400,
        )
        self.error_label.pack(pady=5)

        # Button frame
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(pady=10)

        ok_button = ttk.Button(
            button_frame,
            text="OK",
            width=10,
            command=self._on_ok,
            bootstyle=self.style.ok_button_bootstyle,
        )
        ok_button.grid(row=0, column=0, padx=5)

        cancel_button = ttk.Button(
            button_frame,
            text="Cancel",
            width=10,
            command=self._on_cancel,
            bootstyle=self.style.cancel_button_bootstyle,
        )
        cancel_button.grid(row=0, column=1, padx=5)

        # Bind keyboard shortcuts
        self.dialog.bind("<Return>", lambda e: self._on_ok())
        self.dialog.bind("<Escape>", lambda e: self._on_cancel())

        self.dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Keep pseudo-modal behavior (no grab_set).
        if self.parent:
            self.dialog.transient(self.parent)

        # Avoid focus forcing because DateEntry opens its own modal popup.
        self.dialog.lift()
        self._focus_after_id = self.dialog.after_idle(self._focus_start_entry)

        # Wait for dialog to close
        self.dialog.wait_window(self.dialog)
        self.dialog = None
        self.start_entry = None
        self.end_entry = None
        self.error_label = None

        return self.result

    def _focus_start_entry(self) -> None:
        """Focus the start date input when the dialog is idle."""
        self._focus_after_id = None
        if self.start_entry and self.start_entry.winfo_exists():
            self.start_entry.focus_set()

    def _close_dialog(self) -> None:
        """Cancel pending callbacks and close the dialog window safely."""
        if self.dialog is None:
            return
        if self._focus_after_id is not None:
            try:
                self.dialog.after_cancel(self._focus_after_id)
            except tk.TclError:
                pass
            self._focus_after_id = None
        self.dialog.destroy()

    def _set_preset(self, days: int) -> None:
        """Set date range to last N days (end=today, start=today-N)."""
        start_date, end_date = compute_preset_dates(
            days=days,
            today=self.today,
            earliest_allowed=self.earliest_allowed,
        )
        if self.start_entry and self.end_entry:
            self.start_entry.set_date(start_date)
            self.end_entry.set_date(end_date)
            # Update last valid values
            self.last_valid_start = start_date
            self.last_valid_end = end_date
            # Clear any error
            if self.error_label:
                self.error_label.config(text="")

    def _on_ok(self) -> None:
        """Validate inputs and close dialog if valid."""
        if self.error_label:
            self.error_label.config(text="")

        if not self.start_entry or not self.end_entry:
            return

        # Get dates from DateEntry widgets
        try:
            start_val = self.start_entry.get_date()
            end_val = self.end_entry.get_date()

            # Convert datetime to date if needed (ttkbootstrap returns datetime)
            if isinstance(start_val, datetime):
                start_date = start_val.date()
            else:
                start_date = start_val

            if isinstance(end_val, datetime):
                end_date = end_val.date()
            else:
                end_date = end_val

        except Exception as e:
            if self.error_label:
                self.error_label.config(text=f"Invalid date format: {e}")
            return

        # Validate using pure helpers
        try:
            validate_date_in_range(
                start_date, self.earliest_allowed, self.latest_allowed, "Start date"
            )
            validate_date_in_range(
                end_date, self.earliest_allowed, self.latest_allowed, "End date"
            )
            validate_date_range_order(start_date, end_date)
        except ValueError as e:
            if self.error_label:
                self.error_label.config(text=str(e))
            return

        # Valid - store result and close
        self.result = (start_date, end_date)
        self._close_dialog()

    def _on_cancel(self) -> None:
        """Close dialog without returning a result."""
        self.result = None
        self._close_dialog()
