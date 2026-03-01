"""
Inline value widgets for embedded port value editors.

This module provides the base class and factory for inline value widgets that
allow users to enter literal values directly into unconnected input ports on
nodes in the visual graph.

These widgets are embedded using QGraphicsProxyWidget to display Qt widgets
within the QGraphicsScene.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget,
    QGraphicsProxyWidget,
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
)

from visualpython.utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from visualpython.nodes.models.port import InputPort, PortType


# Maximum width for inline widgets to prevent nodes from becoming too wide
INLINE_WIDGET_MAX_WIDTH = 80
INLINE_WIDGET_MIN_WIDTH = 40
INLINE_WIDGET_HEIGHT = 20


class InlineValueWidgetSignals(QObject):
    """Signals for inline value widget events.

    Attributes:
        value_changed: Emitted when the value in the widget changes.
                      Parameters: (new_value: Any)
        editing_started: Emitted when the user starts editing the value.
        editing_finished: Emitted when the user finishes editing the value.
        validation_error: Emitted when the entered value fails validation.
                         Parameters: (error_message: str)
    """

    value_changed = pyqtSignal(object)  # new_value
    editing_started = pyqtSignal()
    editing_finished = pyqtSignal()
    validation_error = pyqtSignal(str)  # error_message


class InlineValueWidget(ABC):
    """
    Abstract base class for inline value editor widgets.

    InlineValueWidget provides the common interface and functionality for
    widgets that allow users to edit literal values directly in input ports
    on the visual graph canvas. Subclasses implement specific editors for
    different data types (string, number, boolean, etc.).

    The widget is designed to be embedded in a QGraphicsProxyWidget for
    display on the QGraphicsScene.

    Attributes:
        port: The InputPort this widget edits.
        signals: Signal emitter for widget events.

    Usage Pattern:
        1. Create widget instance with the target InputPort
        2. Call create_graphics_proxy() to get a QGraphicsProxyWidget
        3. Position the proxy widget in the scene
        4. Connect to signals.value_changed to handle updates
        5. Use set_enabled() to disable when port is connected
    """

    def __init__(
        self,
        port: InputPort,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the inline value widget.

        Args:
            port: The input port this widget edits values for.
            parent: Optional parent widget.
        """
        self._port = port
        self._parent = parent
        self._widget: Optional[QWidget] = None
        self._proxy: Optional[QGraphicsProxyWidget] = None
        self._is_enabled = True
        self._has_error = False
        self._error_message: str = ""

        # Signals for external communication
        self.signals = InlineValueWidgetSignals()

        # Create the actual Qt widget
        self._widget = self._create_widget()
        self._setup_widget()

        # Initialize with port's inline value, default, or display hint
        initial_value = port.inline_value
        if initial_value is None:
            initial_value = port.default_value
        if initial_value is None:
            initial_value = port.display_hint
        if initial_value is not None:
            self.set_value(initial_value, emit_signal=False)

    @property
    def port(self) -> InputPort:
        """Get the input port this widget edits."""
        return self._port

    @property
    def widget(self) -> Optional[QWidget]:
        """Get the underlying Qt widget."""
        return self._widget

    @property
    def proxy(self) -> Optional[QGraphicsProxyWidget]:
        """Get the graphics proxy widget for scene embedding."""
        return self._proxy

    @property
    def is_enabled(self) -> bool:
        """Check if the widget is enabled for editing."""
        return self._is_enabled

    @property
    def has_error(self) -> bool:
        """Check if the widget has a validation error."""
        return self._has_error

    @property
    def error_message(self) -> str:
        """Get the current validation error message."""
        return self._error_message

    @abstractmethod
    def _create_widget(self) -> QWidget:
        """
        Create the Qt widget for editing.

        Subclasses must implement this to create the appropriate
        editor widget (QLineEdit, QSpinBox, QCheckBox, etc.).

        Returns:
            The created Qt widget.
        """
        pass

    @abstractmethod
    def get_value(self) -> Any:
        """
        Get the current value from the widget.

        Returns:
            The current value in the appropriate type for the port.
        """
        pass

    @abstractmethod
    def set_value(self, value: Any, emit_signal: bool = True) -> None:
        """
        Set the value displayed in the widget.

        Args:
            value: The value to display.
            emit_signal: Whether to emit the value_changed signal.
        """
        pass

    @abstractmethod
    def validate_value(self, value: Any) -> tuple[bool, str]:
        """
        Validate a value for this widget's port type.

        Args:
            value: The value to validate.

        Returns:
            Tuple of (is_valid, error_message).
            error_message is empty if is_valid is True.
        """
        pass

    def _setup_widget(self) -> None:
        """Set up common widget properties."""
        if self._widget is None:
            return

        # Set size constraints
        self._widget.setMinimumWidth(INLINE_WIDGET_MIN_WIDTH)
        self._widget.setMaximumWidth(INLINE_WIDGET_MAX_WIDTH)
        self._widget.setFixedHeight(INLINE_WIDGET_HEIGHT)

        # Set size policy
        self._widget.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed
        )

        # Apply common styling
        self._apply_base_style()

    def _apply_base_style(self) -> None:
        """Apply base styling to the widget."""
        if self._widget is None:
            return

        # Use a small, compact font
        font = QFont("Segoe UI", 8)
        self._widget.setFont(font)

        # Base stylesheet - subclasses can override
        self._update_style()

    def _update_style(self) -> None:
        """Update the widget style based on current state."""
        if self._widget is None:
            return

        if self._has_error:
            # Error state - red border
            base_style = """
                background-color: #3d2a2a;
                border: 1px solid #ff4444;
                border-radius: 2px;
                color: #ffffff;
                padding: 1px 3px;
            """
        elif not self._is_enabled:
            # Disabled state - dimmed
            base_style = """
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 2px;
                color: #666666;
                padding: 1px 3px;
            """
        else:
            # Normal state
            base_style = """
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 2px;
                color: #ffffff;
                padding: 1px 3px;
            """

        # Apply the style (subclasses may add widget-specific selectors)
        self._apply_style(base_style)

    def _apply_style(self, base_style: str) -> None:
        """
        Apply style to the widget.

        Subclasses can override this to add widget-specific style rules.

        Args:
            base_style: The base CSS style to apply.
        """
        if self._widget is not None:
            self._widget.setStyleSheet(base_style)

    def create_graphics_proxy(self) -> QGraphicsProxyWidget:
        """
        Create and return a QGraphicsProxyWidget for scene embedding.

        The proxy widget can be added to a QGraphicsScene to display
        this editor widget on the visual graph canvas.

        Returns:
            A QGraphicsProxyWidget wrapping this widget.
        """
        if self._proxy is None:
            self._proxy = QGraphicsProxyWidget()
            self._proxy.setWidget(self._widget)

            # Set proxy flags for proper interaction
            self._proxy.setFlag(
                QGraphicsProxyWidget.GraphicsItemFlag.ItemIsFocusable,
                True
            )
            self._proxy.setFlag(
                QGraphicsProxyWidget.GraphicsItemFlag.ItemIsSelectable,
                False
            )

            # Set Z-value above node body but below connections
            self._proxy.setZValue(2)

        return self._proxy

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the widget.

        When disabled (typically because the port is connected),
        the widget is visually dimmed and cannot be edited.

        Args:
            enabled: True to enable editing, False to disable.
        """
        self._is_enabled = enabled
        if self._widget is not None:
            self._widget.setEnabled(enabled)
        self._update_style()

    def set_visible(self, visible: bool) -> None:
        """
        Show or hide the widget.

        Args:
            visible: True to show, False to hide.
        """
        if self._widget is not None:
            self._widget.setVisible(visible)
        if self._proxy is not None:
            self._proxy.setVisible(visible)

    def set_error(self, has_error: bool, message: str = "") -> None:
        """
        Set the error state of the widget.

        Args:
            has_error: True if there's a validation error.
            message: The error message to display as tooltip.
        """
        self._has_error = has_error
        self._error_message = message

        if self._widget is not None:
            if has_error and message:
                self._widget.setToolTip(f"Error: {message}")
            else:
                self._widget.setToolTip(self._get_default_tooltip())

        self._update_style()

        if has_error:
            self.signals.validation_error.emit(message)

    def clear_error(self) -> None:
        """Clear any validation error state."""
        self.set_error(False, "")

    def _get_default_tooltip(self) -> str:
        """
        Get the default tooltip for the widget.

        Returns:
            Default tooltip string showing port info.
        """
        port_type = self._port.port_type.name
        return f"Enter {port_type.lower()} value"

    def _on_value_changed(self) -> None:
        """
        Handle value change from the widget.

        Validates the new value and updates the port's inline_value.
        """
        value = self.get_value()

        # Validate the value
        is_valid, error_msg = self.validate_value(value)

        if is_valid:
            self.clear_error()
            # Update the port's inline value
            self._port.inline_value = value
            # Emit signal
            self.signals.value_changed.emit(value)
        else:
            self.set_error(True, error_msg)

    def _on_editing_started(self) -> None:
        """Handle start of editing."""
        self.signals.editing_started.emit()

    def _on_editing_finished(self) -> None:
        """Handle end of editing."""
        self.signals.editing_finished.emit()

    def sync_from_port(self) -> None:
        """
        Synchronize the widget value from the port's inline_value.

        Call this to update the widget when the port's value has
        been changed externally (e.g., from deserialization).
        """
        value = self._port.inline_value
        if value is None:
            value = self._port.default_value
        if value is None:
            value = self._port.display_hint
        if value is not None:
            self.set_value(value, emit_signal=False)

    def get_preferred_width(self) -> int:
        """
        Get the preferred width for this widget.

        Subclasses can override to provide type-specific widths.

        Returns:
            Preferred width in pixels.
        """
        return INLINE_WIDGET_MAX_WIDTH

    def get_height(self) -> int:
        """
        Get the height of this widget.

        Returns:
            Height in pixels.
        """
        return INLINE_WIDGET_HEIGHT

    def cleanup(self) -> None:
        """
        Clean up resources when the widget is no longer needed.

        Call this when removing the widget from the scene.
        """
        if self._proxy is not None:
            self._proxy.setWidget(None)
            self._proxy = None

        if self._widget is not None:
            self._widget.deleteLater()
            self._widget = None

    def __repr__(self) -> str:
        """String representation."""
        port_name = self._port.name if self._port else "unknown"
        return f"{self.__class__.__name__}(port='{port_name}')"


class StringInlineWidget(InlineValueWidget):
    """
    Inline value widget for STRING type ports.

    Uses a QLineEdit to allow users to enter string values directly
    into input ports on the visual graph canvas. Supports single-line
    text input with placeholder text and validation feedback.

    The widget displays text with ellipsis when content overflows
    the compact widget width.

    Example:
        >>> port = InputPort("message", PortType.STRING)
        >>> widget = StringInlineWidget(port)
        >>> widget.set_value("Hello World")
        >>> widget.get_value()
        'Hello World'
    """

    def __init__(
        self,
        port: InputPort,
        parent: Optional[QWidget] = None,
        placeholder_text: str = "",
    ) -> None:
        """
        Initialize the string inline widget.

        Args:
            port: The input port this widget edits values for.
            parent: Optional parent widget.
            placeholder_text: Placeholder text to show when empty.
                            Defaults to showing the port name.
        """
        self._placeholder_text = placeholder_text
        super().__init__(port, parent)

    def _create_widget(self) -> QWidget:
        """
        Create the QLineEdit widget for string editing.

        Returns:
            A configured QLineEdit widget.
        """
        line_edit = QLineEdit()

        # Set placeholder text
        placeholder = self._placeholder_text or self._port.name
        line_edit.setPlaceholderText(placeholder)

        # Connect signals
        line_edit.textChanged.connect(self._on_text_changed)
        line_edit.editingFinished.connect(self._on_editing_finished)

        # Focus handling
        original_focus_in = line_edit.focusInEvent

        def focus_in_event(event):
            self._on_editing_started()
            original_focus_in(event)

        line_edit.focusInEvent = focus_in_event

        return line_edit

    def _apply_style(self, base_style: str) -> None:
        """
        Apply style to the QLineEdit widget.

        Adds QLineEdit-specific CSS selectors to the base style.

        Args:
            base_style: The base CSS style to apply.
        """
        if self._widget is not None:
            # Add QLineEdit selector for better specificity
            line_edit_style = f"QLineEdit {{ {base_style} }}"
            self._widget.setStyleSheet(line_edit_style)

    def get_value(self) -> str:
        """
        Get the current text value from the widget.

        Returns:
            The current text string, or empty string if widget not created.
        """
        if self._widget is not None and isinstance(self._widget, QLineEdit):
            return self._widget.text()
        return ""

    def set_value(self, value: Any, emit_signal: bool = True) -> None:
        """
        Set the text value displayed in the widget.

        Args:
            value: The value to display. Will be converted to string.
            emit_signal: Whether to emit the value_changed signal.
        """
        if self._widget is not None and isinstance(self._widget, QLineEdit):
            # Block signals if we don't want to emit
            if not emit_signal:
                self._widget.blockSignals(True)

            # Convert to string and set
            text_value = str(value) if value is not None else ""
            self._widget.setText(text_value)

            if not emit_signal:
                self._widget.blockSignals(False)

    def validate_value(self, value: Any) -> tuple[bool, str]:
        """
        Validate a value for string type.

        String values are always valid - any value can be converted
        to a string representation.

        Args:
            value: The value to validate.

        Returns:
            Tuple of (True, "") - string values are always valid.
        """
        # Strings are always valid - any value can be stringified
        return (True, "")

    def _on_text_changed(self, text: str) -> None:
        """
        Handle text change in the QLineEdit.

        Args:
            text: The new text value.
        """
        self._on_value_changed()

    def _get_default_tooltip(self) -> str:
        """
        Get the default tooltip for the string widget.

        Returns:
            Default tooltip string.
        """
        return f"Enter text value for '{self._port.name}'"

    def get_preferred_width(self) -> int:
        """
        Get the preferred width for string input.

        String inputs use the maximum inline widget width to
        accommodate text entry.

        Returns:
            Preferred width in pixels.
        """
        return INLINE_WIDGET_MAX_WIDTH


class NumberInlineWidget(InlineValueWidget):
    """
    Inline value widget for INTEGER and FLOAT type ports.

    Uses QSpinBox for INTEGER ports and QDoubleSpinBox for FLOAT ports
    to allow users to enter numeric values directly into input ports on
    the visual graph canvas. Supports value range limits and step sizes.

    The widget provides up/down arrows for easy value adjustment as well
    as direct text entry for precise values.

    Attributes:
        is_integer: True if this widget is for INTEGER type, False for FLOAT.
        min_value: Minimum allowed value.
        max_value: Maximum allowed value.
        step: Step size for increment/decrement.

    Example:
        >>> port = InputPort("count", PortType.INTEGER)
        >>> widget = NumberInlineWidget(port)
        >>> widget.set_value(42)
        >>> widget.get_value()
        42

        >>> port = InputPort("ratio", PortType.FLOAT)
        >>> widget = NumberInlineWidget(port)
        >>> widget.set_value(3.14)
        >>> widget.get_value()
        3.14
    """

    # Default ranges for number types
    DEFAULT_INT_MIN = -999999
    DEFAULT_INT_MAX = 999999
    DEFAULT_FLOAT_MIN = -999999.0
    DEFAULT_FLOAT_MAX = 999999.0
    DEFAULT_INT_STEP = 1
    DEFAULT_FLOAT_STEP = 0.1
    DEFAULT_FLOAT_DECIMALS = 4

    def __init__(
        self,
        port: InputPort,
        parent: Optional[QWidget] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        step: Optional[float] = None,
        decimals: int = DEFAULT_FLOAT_DECIMALS,
    ) -> None:
        """
        Initialize the number inline widget.

        Args:
            port: The input port this widget edits values for.
                  Must be of type INTEGER or FLOAT.
            parent: Optional parent widget.
            min_value: Minimum allowed value. Defaults based on port type.
            max_value: Maximum allowed value. Defaults based on port type.
            step: Step size for increment/decrement. Defaults based on port type.
            decimals: Number of decimal places for FLOAT type. Default is 4.
        """
        from visualpython.nodes.models.port import PortType

        # Determine if this is an integer or float port
        self._is_integer = port.port_type == PortType.INTEGER

        # Set default ranges based on type
        if self._is_integer:
            self._min_value = int(min_value) if min_value is not None else self.DEFAULT_INT_MIN
            self._max_value = int(max_value) if max_value is not None else self.DEFAULT_INT_MAX
            self._step = int(step) if step is not None else self.DEFAULT_INT_STEP
            self._decimals = 0
        else:
            self._min_value = float(min_value) if min_value is not None else self.DEFAULT_FLOAT_MIN
            self._max_value = float(max_value) if max_value is not None else self.DEFAULT_FLOAT_MAX
            self._step = float(step) if step is not None else self.DEFAULT_FLOAT_STEP
            self._decimals = decimals

        super().__init__(port, parent)

    @property
    def is_integer(self) -> bool:
        """Check if this widget is for INTEGER type."""
        return self._is_integer

    @property
    def min_value(self) -> float:
        """Get the minimum allowed value."""
        return self._min_value

    @property
    def max_value(self) -> float:
        """Get the maximum allowed value."""
        return self._max_value

    @property
    def step(self) -> float:
        """Get the step size for increment/decrement."""
        return self._step

    def _create_widget(self) -> QWidget:
        """
        Create the QSpinBox or QDoubleSpinBox widget for number editing.

        Returns:
            A configured QSpinBox (for INTEGER) or QDoubleSpinBox (for FLOAT).
        """
        if self._is_integer:
            spin_box = QSpinBox()
            spin_box.setRange(int(self._min_value), int(self._max_value))
            spin_box.setSingleStep(int(self._step))
            # Connect signal for integer
            spin_box.valueChanged.connect(self._on_int_value_changed)
        else:
            spin_box = QDoubleSpinBox()
            spin_box.setRange(self._min_value, self._max_value)
            spin_box.setSingleStep(self._step)
            spin_box.setDecimals(self._decimals)
            # Connect signal for float
            spin_box.valueChanged.connect(self._on_float_value_changed)

        # Common configuration
        spin_box.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)  # Hide arrows for compact view
        spin_box.setKeyboardTracking(True)  # Update as user types

        # Focus handling
        original_focus_in = spin_box.focusInEvent
        original_focus_out = spin_box.focusOutEvent

        def focus_in_event(event):
            self._on_editing_started()
            original_focus_in(event)

        def focus_out_event(event):
            self._on_editing_finished()
            original_focus_out(event)

        spin_box.focusInEvent = focus_in_event
        spin_box.focusOutEvent = focus_out_event

        return spin_box

    def _apply_style(self, base_style: str) -> None:
        """
        Apply style to the QSpinBox or QDoubleSpinBox widget.

        Adds widget-specific CSS selectors to the base style.

        Args:
            base_style: The base CSS style to apply.
        """
        if self._widget is not None:
            # Use appropriate selector based on widget type
            widget_type = "QSpinBox" if self._is_integer else "QDoubleSpinBox"
            spin_box_style = f"{widget_type} {{ {base_style} }}"
            self._widget.setStyleSheet(spin_box_style)

    def get_value(self) -> Any:
        """
        Get the current numeric value from the widget.

        Returns:
            The current value as int (for INTEGER) or float (for FLOAT),
            or 0 if widget not created.
        """
        if self._widget is not None:
            if self._is_integer and isinstance(self._widget, QSpinBox):
                return self._widget.value()
            elif not self._is_integer and isinstance(self._widget, QDoubleSpinBox):
                return self._widget.value()
        return 0 if self._is_integer else 0.0

    def set_value(self, value: Any, emit_signal: bool = True) -> None:
        """
        Set the numeric value displayed in the widget.

        Args:
            value: The value to display. Will be converted to appropriate type.
            emit_signal: Whether to emit the value_changed signal.
        """
        if self._widget is None:
            return

        # Block signals if we don't want to emit
        if not emit_signal:
            self._widget.blockSignals(True)

        try:
            if self._is_integer:
                # Convert to int, handling various input types
                if value is None:
                    int_value = 0
                elif isinstance(value, bool):
                    int_value = 1 if value else 0
                elif isinstance(value, (int, float)):
                    int_value = int(value)
                else:
                    try:
                        int_value = int(float(str(value)))
                    except (ValueError, TypeError):
                        int_value = 0
                        self.set_error(True, f"Cannot convert '{value}' to integer")

                if isinstance(self._widget, QSpinBox):
                    self._widget.setValue(int_value)
            else:
                # Convert to float, handling various input types
                if value is None:
                    float_value = 0.0
                elif isinstance(value, bool):
                    float_value = 1.0 if value else 0.0
                elif isinstance(value, (int, float)):
                    float_value = float(value)
                else:
                    try:
                        float_value = float(str(value))
                    except (ValueError, TypeError):
                        float_value = 0.0
                        self.set_error(True, f"Cannot convert '{value}' to float")

                if isinstance(self._widget, QDoubleSpinBox):
                    self._widget.setValue(float_value)
        finally:
            if not emit_signal:
                self._widget.blockSignals(False)

    def validate_value(self, value: Any) -> tuple[bool, str]:
        """
        Validate a value for this widget's numeric port type.

        Checks that the value can be converted to the appropriate
        numeric type (int or float) and is within the allowed range.

        Args:
            value: The value to validate.

        Returns:
            Tuple of (is_valid, error_message).
            error_message is empty if is_valid is True.
        """
        # Handle None
        if value is None:
            return (True, "")  # None is treated as 0

        # Handle bool specially (bool is subclass of int in Python)
        if isinstance(value, bool):
            return (True, "")

        # Try to convert to the appropriate type
        try:
            if self._is_integer:
                if isinstance(value, float):
                    # Allow floats that are whole numbers
                    if value != int(value):
                        return (False, f"Value {value} is not a whole number")
                    numeric_value = int(value)
                elif isinstance(value, int):
                    numeric_value = value
                else:
                    # Try string conversion
                    float_val = float(str(value))
                    if float_val != int(float_val):
                        return (False, f"Value '{value}' is not a whole number")
                    numeric_value = int(float_val)
            else:
                if isinstance(value, (int, float)):
                    numeric_value = float(value)
                else:
                    numeric_value = float(str(value))

            # Check range
            if numeric_value < self._min_value:
                return (False, f"Value {numeric_value} is below minimum {self._min_value}")
            if numeric_value > self._max_value:
                return (False, f"Value {numeric_value} is above maximum {self._max_value}")

            return (True, "")

        except (ValueError, TypeError) as e:
            type_name = "integer" if self._is_integer else "number"
            return (False, f"Cannot convert to {type_name}: {value}")

    def _on_int_value_changed(self, value: int) -> None:
        """
        Handle value change from QSpinBox.

        Args:
            value: The new integer value.
        """
        self._on_value_changed()

    def _on_float_value_changed(self, value: float) -> None:
        """
        Handle value change from QDoubleSpinBox.

        Args:
            value: The new float value.
        """
        self._on_value_changed()

    def _get_default_tooltip(self) -> str:
        """
        Get the default tooltip for the number widget.

        Returns:
            Default tooltip string showing port info and range.
        """
        type_name = "integer" if self._is_integer else "number"
        return (
            f"Enter {type_name} value for '{self._port.name}'\n"
            f"Range: {self._min_value} to {self._max_value}"
        )

    def get_preferred_width(self) -> int:
        """
        Get the preferred width for number input.

        Number inputs use a slightly narrower width since they
        typically contain shorter content than strings.

        Returns:
            Preferred width in pixels.
        """
        # Numbers are typically shorter, so use a slightly narrower width
        return INLINE_WIDGET_MAX_WIDTH - 10

    def set_range(self, min_value: float, max_value: float) -> None:
        """
        Set the allowed value range.

        Args:
            min_value: Minimum allowed value.
            max_value: Maximum allowed value.
        """
        self._min_value = min_value
        self._max_value = max_value

        if self._widget is not None:
            if self._is_integer and isinstance(self._widget, QSpinBox):
                self._widget.setRange(int(min_value), int(max_value))
            elif not self._is_integer and isinstance(self._widget, QDoubleSpinBox):
                self._widget.setRange(min_value, max_value)

    def set_step(self, step: float) -> None:
        """
        Set the step size for increment/decrement.

        Args:
            step: The step size.
        """
        self._step = step

        if self._widget is not None:
            if self._is_integer and isinstance(self._widget, QSpinBox):
                self._widget.setSingleStep(int(step))
            elif not self._is_integer and isinstance(self._widget, QDoubleSpinBox):
                self._widget.setSingleStep(step)


class BooleanInlineWidget(InlineValueWidget):
    """
    Inline value widget for BOOLEAN type ports.

    Uses a QCheckBox to allow users to toggle boolean values directly
    on input ports in the visual graph canvas. The checkbox provides
    a simple, intuitive way to enter True/False values.

    The widget displays a compact checkbox that can be checked (True)
    or unchecked (False). Clicking the checkbox toggles the value.

    Example:
        >>> port = InputPort("enabled", PortType.BOOLEAN)
        >>> widget = BooleanInlineWidget(port)
        >>> widget.set_value(True)
        >>> widget.get_value()
        True

        >>> widget.set_value(False)
        >>> widget.get_value()
        False
    """

    # Boolean widgets are more compact than other types
    BOOLEAN_WIDGET_WIDTH = 24

    def __init__(
        self,
        port: InputPort,
        parent: Optional[QWidget] = None,
        label_text: str = "",
    ) -> None:
        """
        Initialize the boolean inline widget.

        Args:
            port: The input port this widget edits values for.
                  Must be of type BOOLEAN.
            parent: Optional parent widget.
            label_text: Optional label text to display next to the checkbox.
                       If empty, no label is shown for compact display.
        """
        self._label_text = label_text
        super().__init__(port, parent)

    def _create_widget(self) -> QWidget:
        """
        Create the QCheckBox widget for boolean editing.

        Returns:
            A configured QCheckBox widget.
        """
        checkbox = QCheckBox()

        # Set optional label text (usually empty for compact inline display)
        if self._label_text:
            checkbox.setText(self._label_text)

        # Connect signal for state changes
        checkbox.stateChanged.connect(self._on_state_changed)

        # Focus handling
        original_focus_in = checkbox.focusInEvent
        original_focus_out = checkbox.focusOutEvent

        def focus_in_event(event):
            self._on_editing_started()
            original_focus_in(event)

        def focus_out_event(event):
            self._on_editing_finished()
            original_focus_out(event)

        checkbox.focusInEvent = focus_in_event
        checkbox.focusOutEvent = focus_out_event

        return checkbox

    def _setup_widget(self) -> None:
        """Set up common widget properties for the checkbox."""
        if self._widget is None:
            return

        # Boolean widgets are more compact
        self._widget.setMinimumWidth(self.BOOLEAN_WIDGET_WIDTH)
        self._widget.setMaximumWidth(INLINE_WIDGET_MAX_WIDTH)
        self._widget.setFixedHeight(INLINE_WIDGET_HEIGHT)

        # Set size policy
        self._widget.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed
        )

        # Apply common styling
        self._apply_base_style()

    def _apply_style(self, base_style: str) -> None:
        """
        Apply style to the QCheckBox widget.

        Adds QCheckBox-specific CSS selectors to the base style.
        Checkboxes need special styling for the indicator (the actual checkbox).

        Args:
            base_style: The base CSS style to apply.
        """
        if self._widget is None:
            return

        # Determine colors based on state
        if self._has_error:
            indicator_border = "#ff4444"
            indicator_bg = "#3d2a2a"
            indicator_checked_bg = "#ff4444"
        elif not self._is_enabled:
            indicator_border = "#333333"
            indicator_bg = "#1a1a1a"
            indicator_checked_bg = "#444444"
        else:
            indicator_border = "#555555"
            indicator_bg = "#2d2d2d"
            indicator_checked_bg = "#4a9eff"

        # Build checkbox-specific stylesheet
        checkbox_style = f"""
            QCheckBox {{
                spacing: 0px;
                background: transparent;
                color: #ffffff;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {indicator_border};
                border-radius: 2px;
                background-color: {indicator_bg};
            }}
            QCheckBox::indicator:checked {{
                background-color: {indicator_checked_bg};
                border-color: {indicator_checked_bg};
            }}
            QCheckBox::indicator:checked {{
                image: none;
            }}
            QCheckBox::indicator:checked::after {{
                content: "";
            }}
            QCheckBox::indicator:hover {{
                border-color: #6a9fff;
            }}
            QCheckBox::indicator:disabled {{
                background-color: {indicator_bg};
                border-color: #333333;
            }}
        """
        self._widget.setStyleSheet(checkbox_style)

    def get_value(self) -> bool:
        """
        Get the current boolean value from the widget.

        Returns:
            True if the checkbox is checked, False otherwise.
        """
        if self._widget is not None and isinstance(self._widget, QCheckBox):
            return self._widget.isChecked()
        return False

    def set_value(self, value: Any, emit_signal: bool = True) -> None:
        """
        Set the boolean value displayed in the widget.

        Args:
            value: The value to display. Will be converted to boolean.
                   Truthy values become True, falsy values become False.
            emit_signal: Whether to emit the value_changed signal.
        """
        if self._widget is None or not isinstance(self._widget, QCheckBox):
            return

        # Block signals if we don't want to emit
        if not emit_signal:
            self._widget.blockSignals(True)

        # Convert to boolean
        bool_value = self._to_boolean(value)
        self._widget.setChecked(bool_value)

        if not emit_signal:
            self._widget.blockSignals(False)

    def _to_boolean(self, value: Any) -> bool:
        """
        Convert a value to boolean.

        Handles various input types including strings like "true", "false",
        "yes", "no", "1", "0".

        Args:
            value: The value to convert.

        Returns:
            Boolean representation of the value.
        """
        if value is None:
            return False

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return bool(value)

        if isinstance(value, str):
            # Handle common string representations
            lower_value = value.lower().strip()
            if lower_value in ("true", "yes", "1", "on", "enabled"):
                return True
            elif lower_value in ("false", "no", "0", "off", "disabled", ""):
                return False
            else:
                # Non-empty string that isn't a recognized boolean -> True
                return bool(value)

        # For other types, use standard Python truthiness
        return bool(value)

    def validate_value(self, value: Any) -> tuple[bool, str]:
        """
        Validate a value for boolean type.

        Boolean values are always valid since any value can be
        converted to a boolean using Python's truthiness rules.

        Args:
            value: The value to validate.

        Returns:
            Tuple of (True, "") - boolean values are always valid.
        """
        # Booleans are always valid - any value can be converted to bool
        return (True, "")

    def _on_state_changed(self, state: int) -> None:
        """
        Handle state change from the QCheckBox.

        Args:
            state: The new state (Qt.CheckState enum value).
        """
        self._on_value_changed()

    def _get_default_tooltip(self) -> str:
        """
        Get the default tooltip for the boolean widget.

        Returns:
            Default tooltip string.
        """
        return f"Toggle '{self._port.name}' (True/False)"

    def get_preferred_width(self) -> int:
        """
        Get the preferred width for boolean input.

        Boolean inputs (checkboxes) are compact and only need
        enough space for the checkbox indicator.

        Returns:
            Preferred width in pixels.
        """
        if self._label_text:
            # If there's a label, use more width
            return INLINE_WIDGET_MAX_WIDTH
        return self.BOOLEAN_WIDGET_WIDTH


class GenericInlineWidget(InlineValueWidget):
    """
    Inline value widget for ANY, LIST, and DICT type ports.

    Uses a QLineEdit to allow users to enter JSON-formatted values directly
    into input ports on the visual graph canvas. The widget parses and validates
    JSON input to ensure proper data structures.

    For ANY type ports, the widget attempts to parse the input as JSON first,
    and if that fails, treats it as a plain string value.

    For LIST type ports, the input must be a valid JSON array (e.g., [1, 2, 3]).

    For DICT type ports, the input must be a valid JSON object (e.g., {"key": "value"}).

    The widget provides validation feedback and error tooltips for invalid input.

    Attributes:
        target_type: The specific port type (ANY, LIST, or DICT).
        strict_mode: If True, requires strict JSON for LIST/DICT types.
                    If False, allows more lenient parsing for ANY type.

    Example:
        >>> port = InputPort("data", PortType.LIST)
        >>> widget = GenericInlineWidget(port)
        >>> widget.set_value([1, 2, 3])
        >>> widget.get_value()
        [1, 2, 3]

        >>> port = InputPort("config", PortType.DICT)
        >>> widget = GenericInlineWidget(port)
        >>> widget.set_value({"key": "value"})
        >>> widget.get_value()
        {'key': 'value'}

        >>> port = InputPort("anything", PortType.ANY)
        >>> widget = GenericInlineWidget(port)
        >>> widget.set_value("hello")  # Can be any type
        >>> widget.get_value()
        'hello'
    """

    def __init__(
        self,
        port: InputPort,
        parent: Optional[QWidget] = None,
        placeholder_text: str = "",
    ) -> None:
        """
        Initialize the generic inline widget.

        Args:
            port: The input port this widget edits values for.
                  Must be of type ANY, LIST, or DICT.
            parent: Optional parent widget.
            placeholder_text: Placeholder text to show when empty.
                            Defaults to type-specific hints.
        """
        from visualpython.nodes.models.port import PortType

        self._placeholder_text = placeholder_text
        self._target_type = port.port_type

        # Determine if we're in strict mode (LIST/DICT require valid JSON)
        self._strict_mode = port.port_type in (PortType.LIST, PortType.DICT)

        # Store the last successfully parsed value
        self._last_valid_value: Any = None

        super().__init__(port, parent)

    @property
    def target_type(self) -> PortType:
        """Get the target port type."""
        return self._target_type

    @property
    def strict_mode(self) -> bool:
        """Check if strict JSON validation is required."""
        return self._strict_mode

    def _create_widget(self) -> QWidget:
        """
        Create the QLineEdit widget for JSON/generic value editing.

        Returns:
            A configured QLineEdit widget.
        """
        from visualpython.nodes.models.port import PortType

        line_edit = QLineEdit()

        # Set type-specific placeholder text
        if self._placeholder_text:
            placeholder = self._placeholder_text
        elif self._target_type == PortType.LIST:
            placeholder = "[...]"
        elif self._target_type == PortType.DICT:
            placeholder = "{...}"
        else:  # ANY
            placeholder = "value"

        line_edit.setPlaceholderText(placeholder)

        # Connect signals
        line_edit.textChanged.connect(self._on_text_changed)
        line_edit.editingFinished.connect(self._on_editing_finished)

        # Focus handling
        original_focus_in = line_edit.focusInEvent
        original_focus_out = line_edit.focusOutEvent

        def focus_in_event(event):
            self._on_editing_started()
            original_focus_in(event)

        def focus_out_event(event):
            # Validate on blur
            self._validate_current_input()
            original_focus_out(event)

        line_edit.focusInEvent = focus_in_event
        line_edit.focusOutEvent = focus_out_event

        return line_edit

    def _apply_style(self, base_style: str) -> None:
        """
        Apply style to the QLineEdit widget.

        Adds QLineEdit-specific CSS selectors to the base style.

        Args:
            base_style: The base CSS style to apply.
        """
        if self._widget is not None:
            line_edit_style = f"QLineEdit {{ {base_style} }}"
            self._widget.setStyleSheet(line_edit_style)

    def get_value(self) -> Any:
        """
        Get the current value from the widget.

        Parses the text as JSON if possible, otherwise returns
        the raw text (for ANY type) or the last valid value
        (for LIST/DICT types with invalid input).

        Returns:
            The parsed value, or the raw text for ANY type,
            or the last valid value if current input is invalid.
        """
        if self._widget is None or not isinstance(self._widget, QLineEdit):
            return self._last_valid_value

        text = self._widget.text().strip()

        if not text:
            return self._get_empty_value()

        # Try to parse as JSON
        parsed, success = self._parse_json(text)

        if success:
            return parsed
        elif self._strict_mode:
            # For LIST/DICT, return last valid value if parse fails
            return self._last_valid_value
        else:
            # For ANY type, return the raw text if JSON parse fails
            return text

    def _get_empty_value(self) -> Any:
        """
        Get the appropriate empty value for the port type.

        Returns:
            Empty list for LIST, empty dict for DICT, None for ANY.
        """
        from visualpython.nodes.models.port import PortType

        if self._target_type == PortType.LIST:
            return []
        elif self._target_type == PortType.DICT:
            return {}
        else:  # ANY
            return None

    def set_value(self, value: Any, emit_signal: bool = True) -> None:
        """
        Set the value displayed in the widget.

        Converts the value to a JSON string representation.

        Args:
            value: The value to display. Will be JSON-serialized.
            emit_signal: Whether to emit the value_changed signal.
        """
        import json

        if self._widget is None or not isinstance(self._widget, QLineEdit):
            return

        # Block signals if we don't want to emit
        if not emit_signal:
            self._widget.blockSignals(True)

        try:
            # Store as last valid value
            self._last_valid_value = value

            # Convert to JSON string representation
            if value is None:
                text = ""
            elif isinstance(value, str):
                # For strings, check if we should display as JSON or raw
                if self._strict_mode:
                    # For LIST/DICT ports, strings need to be JSON-encoded
                    text = json.dumps(value)
                else:
                    # For ANY port, try to display as-is if it looks like a simple value
                    text = value
            else:
                # For non-string values, use JSON representation
                text = json.dumps(value)

            self._widget.setText(text)
            self.clear_error()

        except (TypeError, ValueError) as e:
            # If we can't serialize to JSON, use str representation
            self._widget.setText(str(value) if value is not None else "")
        finally:
            if not emit_signal:
                self._widget.blockSignals(False)

    def validate_value(self, value: Any) -> tuple[bool, str]:
        """
        Validate a value for this widget's port type.

        For LIST ports: value must be a list.
        For DICT ports: value must be a dict.
        For ANY ports: any value is valid.

        Args:
            value: The value to validate.

        Returns:
            Tuple of (is_valid, error_message).
            error_message is empty if is_valid is True.
        """
        from visualpython.nodes.models.port import PortType

        if value is None:
            # None is acceptable for all types
            return (True, "")

        if self._target_type == PortType.LIST:
            if not isinstance(value, list):
                return (False, f"Expected a list, got {type(value).__name__}")
        elif self._target_type == PortType.DICT:
            if not isinstance(value, dict):
                return (False, f"Expected a dictionary, got {type(value).__name__}")
        # ANY accepts anything

        return (True, "")

    def _parse_json(self, text: str) -> tuple[Any, bool]:
        """
        Attempt to parse text as JSON.

        Tries JSON parsing first, then falls back to Python literal
        evaluation for additional flexibility.

        Args:
            text: The text to parse.

        Returns:
            Tuple of (parsed_value, success_flag).
            If parsing fails, returns (None, False).
        """
        import json
        import ast

        # First, try standard JSON parsing
        try:
            value = json.loads(text)
            return (value, True)
        except json.JSONDecodeError:
            logger.debug("Inline value parse error", exc_info=True)
            pass

        # For more flexibility, try Python literal evaluation
        # This allows things like single quotes, tuples, etc.
        try:
            value = ast.literal_eval(text)
            return (value, True)
        except (ValueError, SyntaxError):
            logger.debug("Inline value parse error", exc_info=True)
            pass

        return (None, False)

    def _validate_current_input(self) -> None:
        """
        Validate the current text input and update error state.

        Called on blur to ensure the user gets feedback about invalid input.
        """
        from visualpython.nodes.models.port import PortType

        if self._widget is None or not isinstance(self._widget, QLineEdit):
            return

        text = self._widget.text().strip()

        # Empty text is valid (will use default value)
        if not text:
            self.clear_error()
            self._last_valid_value = self._get_empty_value()
            return

        # Try to parse
        parsed, success = self._parse_json(text)

        if success:
            # Validate the parsed value type
            is_valid, error_msg = self.validate_value(parsed)
            if is_valid:
                self.clear_error()
                self._last_valid_value = parsed
            else:
                self.set_error(True, error_msg)
        else:
            # Parse failed
            if self._strict_mode:
                if self._target_type == PortType.LIST:
                    self.set_error(True, "Invalid JSON array. Use format: [1, 2, 3]")
                elif self._target_type == PortType.DICT:
                    self.set_error(True, 'Invalid JSON object. Use format: {"key": "value"}')
            else:
                # For ANY type, non-JSON text is treated as a string value
                self.clear_error()
                self._last_valid_value = text

    def _on_text_changed(self, text: str) -> None:
        """
        Handle text change in the QLineEdit.

        For non-strict mode (ANY type), updates immediately.
        For strict mode (LIST/DICT), only updates if valid.

        Args:
            text: The new text value.
        """
        self._on_value_changed()

    def _on_value_changed(self) -> None:
        """
        Handle value change from the widget.

        Overrides the base class to handle JSON parsing validation.
        """
        value = self.get_value()

        # Validate the value
        is_valid, error_msg = self.validate_value(value)

        if is_valid:
            # For strict mode, also check if the text is parseable
            if self._strict_mode and self._widget is not None:
                text = self._widget.text().strip() if isinstance(self._widget, QLineEdit) else ""
                if text:
                    _, parse_success = self._parse_json(text)
                    if not parse_success:
                        # Don't update port for invalid JSON in strict mode
                        return

            self.clear_error()
            # Update the port's inline value
            self._port.inline_value = value
            self._last_valid_value = value
            # Emit signal
            self.signals.value_changed.emit(value)
        else:
            self.set_error(True, error_msg)

    def _get_default_tooltip(self) -> str:
        """
        Get the default tooltip for the generic widget.

        Returns:
            Default tooltip string with type-specific hints.
        """
        from visualpython.nodes.models.port import PortType

        if self._target_type == PortType.LIST:
            return (
                f"Enter JSON array for '{self._port.name}'\n"
                "Example: [1, 2, 3] or [\"a\", \"b\", \"c\"]"
            )
        elif self._target_type == PortType.DICT:
            return (
                f"Enter JSON object for '{self._port.name}'\n"
                'Example: {"key": "value", "count": 42}'
            )
        else:  # ANY
            return (
                f"Enter value for '{self._port.name}'\n"
                "Accepts JSON (arrays, objects, numbers, strings)\n"
                "or plain text as a string value"
            )

    def get_preferred_width(self) -> int:
        """
        Get the preferred width for generic/JSON input.

        Generic inputs use the maximum width to accommodate
        potentially complex JSON structures.

        Returns:
            Preferred width in pixels.
        """
        return INLINE_WIDGET_MAX_WIDTH

    def get_text(self) -> str:
        """
        Get the raw text from the input widget.

        Useful for debugging or when you need the unparsed input.

        Returns:
            The raw text string from the QLineEdit.
        """
        if self._widget is not None and isinstance(self._widget, QLineEdit):
            return self._widget.text()
        return ""

    def set_text(self, text: str, emit_signal: bool = True) -> None:
        """
        Set the raw text in the input widget.

        This bypasses JSON serialization and sets the text directly.

        Args:
            text: The text to set.
            emit_signal: Whether to emit the value_changed signal.
        """
        if self._widget is not None and isinstance(self._widget, QLineEdit):
            if not emit_signal:
                self._widget.blockSignals(True)
            self._widget.setText(text)
            if not emit_signal:
                self._widget.blockSignals(False)
