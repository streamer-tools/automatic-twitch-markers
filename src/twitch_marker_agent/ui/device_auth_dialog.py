"""
Tkinter dialog for Device Code Flow authentication.

Displays user_code prominently, provides buttons to open Twitch
and copy code, shows status/countdown, and allows cancellation.

The dialog does NOT perform polling itself - that is handled by the
controller. This keeps the UI thin and testable.
"""

from __future__ import annotations

import queue
import tkinter as tk
import webbrowser
from typing import Callable


class DeviceAuthDialog:
    """
    Tkinter dialog for Device Code Flow authentication.

    Shows:
    - Large user_code display
    - "Open Browser" button (opens verification_uri_complete or verification_uri)
    - "Copy Code" button (copies user_code to clipboard)
    - Status text + countdown timer
    - Cancel button

    The dialog runs its own mainloop and blocks until closed.
    External code can update status via update_status() method.

    By default, on show():
    - Auto-copies user_code to clipboard
    - Auto-opens browser to the appropriate verification URL
    """

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel | None,
        user_code: str,
        verification_uri: str,
        expires_in: int,
        on_cancel: Callable[[], None],
        verification_uri_complete: str | None = None,
        browser_opener: Callable[[str], bool] | None = None,
        clipboard_copier: Callable[[tk.Misc, str], None] | None = None,
        auto_open_browser: bool = True,
        auto_copy_code: bool = True,
    ):
        """
        Initialize dialog.

        Args:
            parent: Optional parent window.
            user_code: The code to display to user.
            verification_uri: URL for user to visit.
            expires_in: Seconds until code expires.
            on_cancel: Callback when user clicks cancel or closes window.
            verification_uri_complete: Optional URL with pre-filled code.
            browser_opener: Optional callable to open URLs (for testing).
            clipboard_copier: Optional callable to copy to clipboard (for testing).
            auto_open_browser: If True, open browser automatically on show().
            auto_copy_code: If True, copy code to clipboard on show().
        """
        self.parent = parent
        self.user_code = user_code
        self.verification_uri = verification_uri
        self.verification_uri_complete = verification_uri_complete
        self.expires_in = expires_in
        self.on_cancel = on_cancel
        self.browser_opener = browser_opener or webbrowser.open
        self.clipboard_copier = clipboard_copier or self._default_clipboard_copy
        self.auto_open_browser = auto_open_browser
        self.auto_copy_code = auto_copy_code

        self._cancelled = False
        self._success = False
        self._remaining_seconds = expires_in
        self._status_text = "Waiting for authorization..."
        self._dialog: tk.Toplevel | tk.Tk | None = None
        self._countdown_label: tk.Label | None = None
        self._status_label: tk.Label | None = None
        self._after_id: str | None = None
        self._ui_after_id: str | None = None
        self._hidden_root: tk.Tk | None = None
        self._ui_commands: queue.SimpleQueue[tuple[str, str | None]] = queue.SimpleQueue()

    @staticmethod
    def _default_clipboard_copy(widget: tk.Misc, text: str) -> None:
        """Default clipboard copy implementation."""
        widget.clipboard_clear()
        widget.clipboard_append(text)

    def _get_open_url(self) -> str:
        """Get the URL to open (prefer verification_uri_complete if available)."""
        return self.verification_uri_complete or self.verification_uri

    def show(self) -> bool:
        """
        Show dialog and wait for completion.

        Returns:
            True if authentication completed successfully,
            False if cancelled or closed.
        """
        # Create window - handle parentless case properly for focus
        if self.parent:
            self._dialog = tk.Toplevel(self.parent)
        else:
            # Create hidden root to avoid focus issues
            self._hidden_root = tk.Tk()
            self._hidden_root.withdraw()
            self._dialog = tk.Toplevel(self._hidden_root)

        self._dialog.title("Authenticate with Twitch")
        self._dialog.geometry("420x340")
        self._dialog.resizable(False, False)

        # Center window
        self._dialog.update_idletasks()
        x = (self._dialog.winfo_screenwidth() // 2) - (420 // 2)
        y = (self._dialog.winfo_screenheight() // 2) - (340 // 2)
        self._dialog.geometry(f"+{x}+{y}")

        # Handle window close
        self._dialog.protocol("WM_DELETE_WINDOW", self._handle_cancel)

        # Title
        title_label = tk.Label(
            self._dialog,
            text="Authenticate with Twitch",
            font=("Arial", 14, "bold"),
        )
        title_label.pack(pady=15)

        # Instructions - updated to reflect auto-copy/open behavior
        if self.auto_copy_code and self.auto_open_browser:
            instruction_text = "Code copied! Paste it on the Twitch page if prompted:"
        elif self.auto_copy_code:
            instruction_text = "Code copied! Enter it on Twitch:"
        else:
            instruction_text = "Enter this code on Twitch:"

        instruction_label = tk.Label(
            self._dialog,
            text=instruction_text,
            font=("Arial", 10),
        )
        instruction_label.pack(pady=5)

        # User code (large, prominent)
        code_frame = tk.Frame(
            self._dialog,
            bg="#9146FF",  # Twitch purple
            padx=20,
            pady=10,
        )
        code_frame.pack(pady=10)

        code_label = tk.Label(
            code_frame,
            text=self.user_code,
            font=("Consolas", 24, "bold"),
            bg="#9146FF",
            fg="white",
        )
        code_label.pack()

        # Buttons
        button_frame = tk.Frame(self._dialog)
        button_frame.pack(pady=15)

        open_button = tk.Button(
            button_frame,
            text="Open Browser",
            width=12,
            command=self._open_browser,
            font=("Arial", 10),
            bg="#9146FF",
            fg="white",
            activebackground="#772CE8",
            activeforeground="white",
        )
        open_button.grid(row=0, column=0, padx=5)

        copy_button = tk.Button(
            button_frame,
            text="Copy Code",
            width=12,
            command=self._copy_code,
            font=("Arial", 10),
        )
        copy_button.grid(row=0, column=1, padx=5)

        # Status
        self._status_label = tk.Label(
            self._dialog,
            text=self._status_text,
            font=("Arial", 10),
            wraplength=380,
        )
        self._status_label.pack(pady=5)

        # Countdown
        self._countdown_label = tk.Label(
            self._dialog,
            text=self._format_countdown(),
            font=("Arial", 9),
            fg="gray",
        )
        self._countdown_label.pack(pady=2)

        # Cancel button
        cancel_button = tk.Button(
            self._dialog,
            text="Cancel",
            width=10,
            command=self._handle_cancel,
            font=("Arial", 10),
        )
        cancel_button.pack(pady=15)

        # Start countdown timer
        self._start_countdown()

        # Make modal
        if self.parent:
            self._dialog.transient(self.parent)
        self._dialog.grab_set()

        # Ensure focus
        self._dialog.lift()
        self._dialog.focus_force()

        # Auto-copy and auto-open on show
        self._auto_setup()

        # Process queued UI commands (status updates / close signals)
        self._poll_ui_commands()

        # Wait for dialog to close
        self._dialog.wait_window(self._dialog)

        # Clean up hidden root if we created one
        if self._hidden_root:
            self._hidden_root.destroy()
            self._hidden_root = None

        return self._success

    def _poll_ui_commands(self) -> None:
        """Run queued UI operations on the Tk main thread."""
        if self._dialog is None:
            return

        try:
            while True:
                command, payload = self._ui_commands.get_nowait()
                if command == "update_status" and payload is not None:
                    self._do_update_status(payload)
                elif command == "close_success":
                    self._do_close_success()
                elif command == "close_error":
                    self._close()
        except queue.Empty:
            pass

        if self._dialog is not None:
            self._ui_after_id = self._dialog.after(50, self._poll_ui_commands)

    def _auto_setup(self) -> None:
        """Perform auto-copy and auto-open actions on dialog show."""
        if self.auto_copy_code and self._dialog:
            try:
                self.clipboard_copier(self._dialog, self.user_code)
            except Exception:
                pass  # Ignore clipboard errors

        if self.auto_open_browser:
            try:
                self.browser_opener(self._get_open_url())
            except Exception:
                pass  # Ignore browser open errors

    def _format_countdown(self) -> str:
        """Format remaining time as MM:SS."""
        minutes = self._remaining_seconds // 60
        seconds = self._remaining_seconds % 60
        return f"Expires in: {minutes}:{seconds:02d}"

    def _start_countdown(self) -> None:
        """Start the countdown timer."""
        self._tick_countdown()

    def _tick_countdown(self) -> None:
        """Update countdown every second."""
        if self._dialog is None:
            return

        self._remaining_seconds -= 1

        if self._remaining_seconds <= 0:
            if self._status_label:
                self._status_label.config(text="Code expired. Please try again.")
            if self._countdown_label:
                self._countdown_label.config(text="Expired")
            return

        if self._countdown_label:
            self._countdown_label.config(text=self._format_countdown())

        # Schedule next tick
        self._after_id = self._dialog.after(1000, self._tick_countdown)

    def _open_browser(self) -> None:
        """Open verification URL in browser."""
        try:
            self.browser_opener(self._get_open_url())
        except Exception:
            pass  # Ignore browser open errors

    def _copy_code(self) -> None:
        """Copy user code to clipboard."""
        if self._dialog:
            try:
                self.clipboard_copier(self._dialog, self.user_code)
                # Show feedback
                if self._status_label:
                    original_text = self._status_label.cget("text")
                    self._status_label.config(text="Code copied to clipboard!")
                    self._dialog.after(
                        1500,
                        lambda: self._status_label.config(text=original_text)
                        if self._status_label else None,
                    )
            except Exception:
                pass  # Ignore clipboard errors

    def _handle_cancel(self) -> None:
        """Handle cancel button or window close."""
        self._cancelled = True
        self.on_cancel()
        self._close()

    def update_status(self, status: str) -> None:
        """
        Update status text (thread-safe via after()).

        Args:
            status: New status text to display.
        """
        self._ui_commands.put(("update_status", status))

    def _do_update_status(self, status: str) -> None:
        """Actually update status (must be called from main thread)."""
        self._status_text = status
        if self._status_label:
            self._status_label.config(text=status)

    def close_success(self) -> None:
        """
        Close dialog indicating success (thread-safe).

        Called by controller when auth completes successfully.
        """
        self._ui_commands.put(("close_success", None))

    def _do_close_success(self) -> None:
        """Actually close with success (must be called from main thread)."""
        self._success = True
        self._close()

    def close_error(self, message: str) -> None:
        """
        Close dialog indicating error (thread-safe).

        Args:
            message: Error message (not currently displayed, just closes).
        """
        self._ui_commands.put(("close_error", message))

    def _close(self) -> None:
        """Close the dialog."""
        if self._after_id and self._dialog:
            self._dialog.after_cancel(self._after_id)
            self._after_id = None

        if self._ui_after_id and self._dialog:
            self._dialog.after_cancel(self._ui_after_id)
            self._ui_after_id = None

        if self._dialog:
            self._dialog.destroy()
            self._dialog = None

    @property
    def is_open(self) -> bool:
        """Check if dialog is still open."""
        return self._dialog is not None and self._dialog.winfo_exists()
