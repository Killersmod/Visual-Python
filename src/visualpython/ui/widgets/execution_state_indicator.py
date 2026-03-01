"""
Execution state indicator widget for VisualPython.

This module provides a widget that displays the current execution state
in the status bar, giving users visual feedback about script status.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
)

from visualpython.execution.state_manager import ExecutionState, ExecutionStateManager


class ExecutionStateIndicator(QWidget):
    """
    A widget that displays the current execution state with a colored indicator.

    The widget shows:
    - A colored circle indicator (green=idle, yellow=running, red=error, blue=paused)
    - A text label describing the current state
    - Optional progress information during execution

    Example:
        >>> indicator = ExecutionStateIndicator()
        >>> indicator.set_state(ExecutionState.RUNNING)
        >>> # Shows yellow indicator with "Running" text
    """

    # Colors for each execution state
    STATE_COLORS = {
        ExecutionState.IDLE: QColor("#4CAF50"),      # Green
        ExecutionState.RUNNING: QColor("#FFC107"),   # Amber/Yellow
        ExecutionState.PAUSED: QColor("#2196F3"),    # Blue
        ExecutionState.ERROR: QColor("#F44336"),     # Red
    }

    # Display text for each state
    STATE_TEXTS = {
        ExecutionState.IDLE: "Ready",
        ExecutionState.RUNNING: "Running",
        ExecutionState.PAUSED: "Paused",
        ExecutionState.ERROR: "Error",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the execution state indicator.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._state: ExecutionState = ExecutionState.IDLE
        self._progress_current: int = 0
        self._progress_total: int = 0
        self._error_message: Optional[str] = None

        # Animation for running state
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._on_animation_tick)
        self._animation_frame: int = 0

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 8, 2)
        layout.setSpacing(6)

        # Indicator circle (custom painted)
        self._indicator = StateIndicatorCircle(self)
        self._indicator.setFixedSize(12, 12)
        layout.addWidget(self._indicator)

        # State label
        self._label = QLabel(self.STATE_TEXTS[self._state])
        self._label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._label)

        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(20)

        # Set tooltip
        self._update_tooltip()

    def set_state(self, state: ExecutionState) -> None:
        """
        Set the current execution state.

        Args:
            state: The new execution state.
        """
        if self._state != state:
            self._state = state
            self._update_display()

            # Start/stop animation for running state
            if state == ExecutionState.RUNNING:
                self._animation_frame = 0
                self._animation_timer.start(100)  # 10 FPS
            else:
                self._animation_timer.stop()

    def set_progress(self, current: int, total: int) -> None:
        """
        Set the execution progress.

        Args:
            current: Number of nodes executed.
            total: Total number of nodes.
        """
        self._progress_current = current
        self._progress_total = total
        self._update_display()

    def set_error_message(self, message: Optional[str]) -> None:
        """
        Set the error message.

        Args:
            message: The error message, or None to clear.
        """
        self._error_message = message
        self._update_tooltip()

    def connect_to_manager(self, manager: ExecutionStateManager) -> None:
        """
        Connect to an ExecutionStateManager to automatically update state.

        Args:
            manager: The execution state manager to observe.
        """
        manager.state_changed.connect(self.set_state)
        manager.progress_updated.connect(self.set_progress)
        manager.error_occurred.connect(self.set_error_message)

        # Also sync with clear error
        manager.execution_started.connect(lambda: self.set_error_message(None))

    def _update_display(self) -> None:
        """Update the display based on current state."""
        # Update indicator color
        color = self.STATE_COLORS.get(self._state, QColor("#9E9E9E"))
        self._indicator.set_color(color)

        # Update label text
        text = self.STATE_TEXTS.get(self._state, "Unknown")

        if self._state == ExecutionState.RUNNING and self._progress_total > 0:
            text = f"Running ({self._progress_current}/{self._progress_total})"

        self._label.setText(text)
        self._update_tooltip()

    def _update_tooltip(self) -> None:
        """Update the tooltip based on current state."""
        tooltip = f"Execution State: {self.STATE_TEXTS.get(self._state, 'Unknown')}"

        if self._state == ExecutionState.RUNNING and self._progress_total > 0:
            percentage = (self._progress_current / self._progress_total) * 100
            tooltip += f"\nProgress: {self._progress_current}/{self._progress_total} ({percentage:.0f}%)"

        if self._state == ExecutionState.ERROR and self._error_message:
            tooltip += f"\nError: {self._error_message}"

        self.setToolTip(tooltip)

    def _on_animation_tick(self) -> None:
        """Handle animation timer tick for running state."""
        self._animation_frame = (self._animation_frame + 1) % 10
        # Create a pulsing effect by slightly varying the color
        self._indicator.set_pulse_frame(self._animation_frame)


class StateIndicatorCircle(QWidget):
    """
    A small circular indicator that shows a colored state.

    This widget paints a filled circle with an optional pulse animation
    for the running state.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the indicator circle.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._color = QColor("#4CAF50")  # Default green
        self._pulse_frame = 0

    def set_color(self, color: QColor) -> None:
        """
        Set the indicator color.

        Args:
            color: The color to display.
        """
        self._color = color
        self.update()

    def set_pulse_frame(self, frame: int) -> None:
        """
        Set the pulse animation frame.

        Args:
            frame: Animation frame (0-9).
        """
        self._pulse_frame = frame
        self.update()

    def sizeHint(self) -> QSize:
        """Return the recommended size."""
        return QSize(12, 12)

    def paintEvent(self, event) -> None:
        """Paint the indicator circle."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Calculate the circle rect with some padding
        rect = self.rect().adjusted(1, 1, -1, -1)

        # Apply pulse effect (subtle size/opacity change)
        color = QColor(self._color)
        if self._pulse_frame > 0:
            # Create a subtle pulse by adjusting alpha
            pulse_factor = abs(5 - self._pulse_frame) / 5.0  # 0.0 to 1.0
            alpha = int(200 + 55 * pulse_factor)  # 200-255
            color.setAlpha(alpha)

        # Draw the filled circle
        painter.setPen(QPen(color.darker(120), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(rect)
