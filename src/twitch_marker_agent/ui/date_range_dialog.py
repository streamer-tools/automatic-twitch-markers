"""
Tkinter date range dialog for multi-fetch feature.

Provides a simple dialog for selecting start and end dates
within the past 60 days from today.
"""

from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import messagebox


class DateRangeDialog:
    """
    Tkinter dialog for selecting date range.

    Opens a modal dialog with date inputs and validates constraints:
    - start_date <= end_date
    - end_date <= today
    - start_date >= today - max_days_back

    Defaults:
    - end_date = today
    - start_date = today - 7 (or today - max_days_back if > max_days_back)
    """

    def __init__(self, parent=None, max_days_back: int = 60):
        """
        Initialize date range dialog.

        Args:
            parent: Optional parent window.
            max_days_back: Maximum days back from today (default: 60).
        """
        self.parent = parent
        self.max_days_back = max_days_back
        self.result: tuple[date, date] | None = None

        # Calculate defaults
        self.today = date.today()
        self.earliest_allowed = self.today - timedelta(days=max_days_back)
        # Default: 7 days back, or earliest_allowed if that's less
        default_start = max(self.today - timedelta(days=7), self.earliest_allowed)
        self.default_start = default_start
        self.default_end = self.today

    def show(self) -> tuple[date, date] | None:
        """
        Show dialog and wait for user input.

        Returns:
            (start_date, end_date) if OK clicked, None if cancelled.
        """
        # Create top-level window
        self.dialog = tk.Toplevel(self.parent) if self.parent else tk.Tk()
        self.dialog.title("Select Date Range")
        self.dialog.geometry("400x250")
        self.dialog.resizable(False, False)

        # Center window
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (250 // 2)
        self.dialog.geometry(f"+{x}+{y}")

        # Title label
        title_label = tk.Label(
            self.dialog,
            text="Fetch Multiple Stream Markers",
            font=("Arial", 12, "bold"),
        )
        title_label.pack(pady=10)

        # Info label
        info_text = f"Select date range (max {self.max_days_back} days back from today)"
        info_label = tk.Label(self.dialog, text=info_text, font=("Arial", 9))
        info_label.pack(pady=5)

        # Date input frame
        input_frame = tk.Frame(self.dialog)
        input_frame.pack(pady=10)

        # Start date
        tk.Label(input_frame, text="Start Date (YYYY-MM-DD):", font=("Arial", 10)).grid(
            row=0, column=0, sticky="e", padx=5, pady=5
        )
        self.start_entry = tk.Entry(input_frame, width=15, font=("Arial", 10))
        self.start_entry.grid(row=0, column=1, padx=5, pady=5)
        self.start_entry.insert(0, self.default_start.isoformat())

        # End date
        tk.Label(input_frame, text="End Date (YYYY-MM-DD):", font=("Arial", 10)).grid(
            row=1, column=0, sticky="e", padx=5, pady=5
        )
        self.end_entry = tk.Entry(input_frame, width=15, font=("Arial", 10))
        self.end_entry.grid(row=1, column=1, padx=5, pady=5)
        self.end_entry.insert(0, self.default_end.isoformat())

        # Error label (initially hidden)
        self.error_label = tk.Label(
            self.dialog,
            text="",
            fg="red",
            font=("Arial", 9),
            wraplength=350,
        )
        self.error_label.pack(pady=5)

        # Button frame
        button_frame = tk.Frame(self.dialog)
        button_frame.pack(pady=10)

        ok_button = tk.Button(
            button_frame,
            text="OK",
            width=10,
            command=self._on_ok,
            font=("Arial", 10),
        )
        ok_button.grid(row=0, column=0, padx=5)

        cancel_button = tk.Button(
            button_frame,
            text="Cancel",
            width=10,
            command=self._on_cancel,
            font=("Arial", 10),
        )
        cancel_button.grid(row=0, column=1, padx=5)

        # Make dialog modal
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # Wait for dialog to close
        self.dialog.wait_window(self.dialog)

        return self.result

    def _on_ok(self) -> None:
        """Validate inputs and close dialog if valid."""
        self.error_label.config(text="")

        # Parse dates
        start_str = self.start_entry.get().strip()
        end_str = self.end_entry.get().strip()

        try:
            start_date = date.fromisoformat(start_str)
        except ValueError:
            self.error_label.config(text=f"Invalid start date format: {start_str}")
            return

        try:
            end_date = date.fromisoformat(end_str)
        except ValueError:
            self.error_label.config(text=f"Invalid end date format: {end_str}")
            return

        # Validate constraints
        if start_date > end_date:
            self.error_label.config(
                text=f"Start date ({start_date}) must be before or equal to end date ({end_date})"
            )
            return

        if end_date > self.today:
            self.error_label.config(
                text=f"End date ({end_date}) cannot be in the future (today is {self.today})"
            )
            return

        if start_date < self.earliest_allowed:
            self.error_label.config(
                text=f"Start date ({start_date}) cannot be more than {self.max_days_back} days ago (earliest: {self.earliest_allowed})"
            )
            return

        # Valid - store result and close
        self.result = (start_date, end_date)
        self.dialog.destroy()

    def _on_cancel(self) -> None:
        """Close dialog without returning a result."""
        self.result = None
        self.dialog.destroy()
