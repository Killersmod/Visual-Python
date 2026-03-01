"""
Node visual widget for the visual programming canvas.

This module provides the QGraphicsItem-based visual representation of nodes,
including their title bar, body, ports, and execution state indicators.
Nodes that implement get_code_preview() will display a read-only code preview
section showing the equivalent Python code.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject
from PyQt6.QtGui import (
    QColor,
    QPen,
    QPainter,
    QBrush,
    QFont,
    QFontMetrics,
    QPainterPath,
    QLinearGradient,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
    QApplication,
    QGraphicsProxyWidget,
    QLineEdit,
)

from visualpython.nodes.views.port_widget import PortWidget, PortLabelWidget, create_inline_widget_for_port

if TYPE_CHECKING:
    from visualpython.nodes.models.base_node import BaseNode, ExecutionState
    from visualpython.nodes.models.port import InputPort, OutputPort


# Execution state colors
EXECUTION_STATE_COLORS: dict[str, str] = {
    "IDLE": "#808080",
    "PENDING": "#FFC107",  # Amber
    "RUNNING": "#2196F3",  # Blue
    "COMPLETED": "#4CAF50",  # Green
    "ERROR": "#F44336",  # Red
    "SKIPPED": "#9E9E9E",  # Gray
}

# Validation state colors
VALIDATION_STATE_COLORS: dict[str, str] = {
    "valid": "#4CAF50",      # Green
    "invalid": "#FF9800",    # Orange/amber for syntax errors
    "unknown": "#808080",    # Gray for unknown state
}

# Selection indicator colors
SELECTION_COLORS: dict[str, str] = {
    "border": "#00AAFF",           # Bright cyan-blue for selected border
    "border_multi": "#00DDFF",     # Slightly different for multi-select
    "glow": "#00AAFF",             # Glow color for selection
    "corner_marker": "#FFFFFF",    # White corner markers
}


class NodeWidgetSignals(QObject):
    """Signals for node widget events."""

    position_changed = pyqtSignal(str, float, float)  # node_id, x, y
    move_finished = pyqtSignal(str, float, float, float, float)  # node_id, old_x, old_y, new_x, new_y
    selected_changed = pyqtSignal(str, bool)  # node_id, selected
    double_clicked = pyqtSignal(str)  # node_id
    delete_requested = pyqtSignal(str)  # node_id
    color_changed = pyqtSignal(str, str)  # node_id, new_color (hex string or empty for reset)
    inline_value_changed = pyqtSignal(str, str, object, object)  # node_id, port_name, old_value, new_value
    error_indicator_clicked = pyqtSignal(str)  # node_id - emitted when error indicator button is clicked
    name_changed = pyqtSignal(str, str, str)  # node_id, old_name, new_name - emitted when node name is edited


class CodePreviewSyntaxHighlighter(QSyntaxHighlighter):
    """
    Lightweight Python syntax highlighter for code preview in NodeWidget.

    This highlighter provides basic Python syntax highlighting optimized for
    displaying small code previews within node widgets. It highlights keywords,
    strings, comments, numbers, and built-in functions using a dark theme
    color scheme.

    Attributes:
        KEYWORDS: List of Python keywords to highlight.
        BUILTINS: List of Python built-in functions to highlight.
    """

    # Python keywords
    KEYWORDS = [
        "and", "as", "assert", "async", "await", "break", "class", "continue",
        "def", "del", "elif", "else", "except", "False", "finally", "for",
        "from", "global", "if", "import", "in", "is", "lambda", "None",
        "nonlocal", "not", "or", "pass", "raise", "return", "True", "try",
        "while", "with", "yield",
    ]

    # Python built-in functions
    BUILTINS = [
        "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
        "callable", "chr", "classmethod", "compile", "complex", "delattr",
        "dict", "dir", "divmod", "enumerate", "eval", "exec", "filter",
        "float", "format", "frozenset", "getattr", "globals", "hasattr",
        "hash", "help", "hex", "id", "input", "int", "isinstance", "issubclass",
        "iter", "len", "list", "locals", "map", "max", "memoryview", "min",
        "next", "object", "oct", "open", "ord", "pow", "print", "property",
        "range", "repr", "reversed", "round", "set", "setattr", "slice",
        "sorted", "staticmethod", "str", "sum", "super", "tuple", "type",
        "vars", "zip", "__import__",
    ]

    def __init__(self, document: QTextDocument) -> None:
        """
        Initialize the code preview syntax highlighter.

        Args:
            document: The QTextDocument to apply highlighting to.
        """
        super().__init__(document)
        self._highlighting_rules: List[tuple[re.Pattern, QTextCharFormat]] = []
        self._setup_formats()
        self._setup_rules()

    def _setup_formats(self) -> None:
        """Set up the text formats for different syntax elements with dark-theme colors."""
        # Keyword format (blue - VS Code style for dark theme)
        self._keyword_format = QTextCharFormat()
        self._keyword_format.setForeground(QColor("#569cd6"))
        self._keyword_format.setFontWeight(QFont.Weight.Bold)

        # Built-in function format (cyan)
        self._builtin_format = QTextCharFormat()
        self._builtin_format.setForeground(QColor("#4ec9b0"))

        # String format (orange/brown)
        self._string_format = QTextCharFormat()
        self._string_format.setForeground(QColor("#ce9178"))

        # Comment format (green, italic)
        self._comment_format = QTextCharFormat()
        self._comment_format.setForeground(QColor("#6a9955"))
        self._comment_format.setFontItalic(True)

        # Number format (light green)
        self._number_format = QTextCharFormat()
        self._number_format.setForeground(QColor("#b5cea8"))

        # Function/class definition format (yellow/gold)
        self._definition_format = QTextCharFormat()
        self._definition_format.setForeground(QColor("#dcdcaa"))
        self._definition_format.setFontWeight(QFont.Weight.Bold)

    def _setup_rules(self) -> None:
        """Set up the highlighting rules with regex patterns."""
        # Keywords
        keyword_pattern = r"\b(" + "|".join(self.KEYWORDS) + r")\b"
        self._highlighting_rules.append(
            (re.compile(keyword_pattern), self._keyword_format)
        )

        # Built-in functions
        builtin_pattern = r"\b(" + "|".join(self.BUILTINS) + r")\b"
        self._highlighting_rules.append(
            (re.compile(builtin_pattern), self._builtin_format)
        )

        # Function and class definitions
        self._highlighting_rules.append(
            (re.compile(r"\bdef\s+(\w+)"), self._definition_format)
        )
        self._highlighting_rules.append(
            (re.compile(r"\bclass\s+(\w+)"), self._definition_format)
        )

        # Numbers (integers, floats, hex, octal, binary)
        self._highlighting_rules.append(
            (re.compile(r"\b0[xX][0-9a-fA-F]+\b"), self._number_format)
        )
        self._highlighting_rules.append(
            (re.compile(r"\b0[oO][0-7]+\b"), self._number_format)
        )
        self._highlighting_rules.append(
            (re.compile(r"\b0[bB][01]+\b"), self._number_format)
        )
        self._highlighting_rules.append(
            (re.compile(r"\b\d+\.?\d*([eE][+-]?\d+)?\b"), self._number_format)
        )

        # Single-line strings (single and double quotes)
        self._highlighting_rules.append(
            (re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"), self._string_format)
        )
        self._highlighting_rules.append(
            (re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), self._string_format)
        )

        # Single-line comments
        self._highlighting_rules.append(
            (re.compile(r"#[^\n]*"), self._comment_format)
        )

    def highlightBlock(self, text: str) -> None:
        """
        Apply syntax highlighting to a block of text.

        Args:
            text: The text block to highlight.
        """
        for pattern, text_format in self._highlighting_rules:
            for match in pattern.finditer(text):
                # For function/class definitions, highlight only the name
                if pattern.pattern.startswith(r"\bdef\s+") or pattern.pattern.startswith(r"\bclass\s+"):
                    if match.lastindex and match.lastindex >= 1:
                        start = match.start(1)
                        length = match.end(1) - start
                        self.setFormat(start, length, text_format)
                else:
                    start = match.start()
                    length = match.end() - start
                    self.setFormat(start, length, text_format)


class NodeWidget(QGraphicsItem):
    """
    Visual representation of a node on the graph canvas.

    Provides a complete graphical representation of a node including:
    - Rounded rectangle body with customizable color
    - Title bar with node name
    - Input and output ports with labels
    - Visual feedback for execution state
    - Selection highlighting
    - Drag-to-move functionality
    - Optional code preview section for nodes with get_code_preview()

    Attributes:
        MIN_WIDTH: Minimum node width in pixels.
        TITLE_HEIGHT: Height of the title bar.
        PORT_SPACING: Vertical spacing between ports.
        PADDING: Internal padding.
        CORNER_RADIUS: Radius of rounded corners.
        CODE_PREVIEW_HEIGHT: Height of the code preview section.
        CODE_PREVIEW_PADDING: Padding within the code preview section.
        CODE_PREVIEW_FONT_SIZE: Font size for code preview text.
        MAX_CODE_PREVIEW_LINES: Maximum lines to display in code preview.
    """

    MIN_WIDTH = 150
    TITLE_HEIGHT = 28
    PORT_SPACING = 24
    PADDING = 10
    CORNER_RADIUS = 8

    # Code preview section layout constants
    CODE_PREVIEW_HEIGHT = 50
    CODE_PREVIEW_PADDING = 6
    CODE_PREVIEW_FONT_SIZE = 8
    MAX_CODE_PREVIEW_LINES = 5

    # Code preview section colors
    CODE_PREVIEW_BG_COLOR = "#1e1e1e"  # Dark background like code editors
    CODE_PREVIEW_TEXT_COLOR = "#d4d4d4"  # Light gray text

    # Error indicator button constants
    ERROR_INDICATOR_SIZE = 18  # Size of the error indicator button
    ERROR_INDICATOR_MARGIN = 4  # Margin from the node edge
    ERROR_INDICATOR_COLOR = "#F44336"  # Red background
    ERROR_INDICATOR_HOVER_COLOR = "#EF5350"  # Lighter red on hover
    ERROR_INDICATOR_ICON_COLOR = "#FFFFFF"  # White icon

    def __init__(
        self,
        node: BaseNode,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """
        Initialize a node widget.

        Args:
            node: The node model this widget represents.
            parent: Optional parent graphics item.
        """
        super().__init__(parent)

        self._node = node
        self._width = self.MIN_WIDTH
        self._height = self.TITLE_HEIGHT + self.PADDING * 2

        # Port widget collections
        self._input_port_widgets: Dict[str, PortWidget] = {}
        self._output_port_widgets: Dict[str, PortWidget] = {}
        self._port_labels: List[PortLabelWidget] = []

        # Visual state
        self._is_selected = False
        self._execution_state_color = QColor(EXECUTION_STATE_COLORS["IDLE"])
        self._has_validation_errors = False

        # Code preview state (for nodes with get_code_preview)
        self._has_code_preview = False
        self._code_preview_text_item: Optional[QGraphicsTextItem] = None
        self._code_preview_highlighter: Optional[CodePreviewSyntaxHighlighter] = None

        # Error indicator state
        self._error_indicator_hovered = False
        self._error_indicator_rect: Optional[QRectF] = None

        # Glow effect state (painted manually, not via QGraphicsEffect)
        self._glow_color: Optional[QColor] = None
        self._glow_radius: int = 0

        # Name editing state
        self._is_editing_name = False
        self._is_finishing_name_edit = False  # Secondary guard to prevent reentrant calls
        self._pending_name_value: Optional[str] = None  # Captured text value for safety
        self._name_edit_proxy: Optional[QGraphicsProxyWidget] = None
        self._name_edit_widget: Optional[QLineEdit] = None

        # Signals
        self.signals = NodeWidgetSignals()

        # Inline value tracking for undo/redo (port_name -> last known value)
        self._inline_old_values: Dict[str, object] = {}

        # Configure item
        self._setup_item()
        self._setup_colors()
        self._create_port_widgets()

        # Set up code preview if node supports it
        self._setup_code_preview()

        self._calculate_size()

        # Set initial position from node model
        self.setPos(node.position.x, node.position.y)

    def _setup_item(self) -> None:
        """Configure the graphics item flags and behavior."""
        # Enable selection and movement
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

        # Enable hover effects
        self.setAcceptHoverEvents(True)

        # Set cursor
        self.setCursor(Qt.CursorShape.SizeAllCursor)

        # Set Z-value (nodes above grid)
        self.setZValue(1)

        # Shadow parameters (painted manually to avoid QGraphicsDropShadowEffect
        # which breaks QGraphicsScene.items() hit-testing via BSP tree corruption)
        self._shadow_offset_x = 3
        self._shadow_offset_y = 3
        self._shadow_color = QColor(0, 0, 0, 60)

    def _setup_colors(self) -> None:
        """Set up the color scheme based on node type or custom color."""
        # Get display color (custom color if set, otherwise node type default)
        node_color = QColor(self._node.display_color)

        # Title bar gradient
        self._title_color = node_color
        self._title_color_dark = node_color.darker(130)

        # Body colors
        self._body_color = QColor("#2d2d2d")
        self._body_color_selected = QColor("#3a3a3a")

        # Border colors
        self._border_color = QColor("#555555")
        self._border_color_selected = QColor(SELECTION_COLORS["border"])

        # Selection glow color
        self._selection_glow_color = QColor(SELECTION_COLORS["glow"])

        # Text colors
        self._title_text_color = QColor("#FFFFFF")
        self._body_text_color = QColor("#CCCCCC")

    def _create_port_widgets(self) -> None:
        """Create port widgets for all input and output ports.

        For input ports (non-FLOW type), inline value widgets are created
        and attached to allow users to enter literal values directly when
        the port is not connected. The inline widgets are connected to
        handlers that update the port model and emit change signals.
        """
        # Create input port widgets
        for port in self._node.input_ports:
            port_widget = PortWidget(port, is_input=True, parent_node=self)
            self._input_port_widgets[port.name] = port_widget

            # Create label
            label = PortLabelWidget(port, is_input=True, parent=self)
            self._port_labels.append(label)

            # Update connected state
            port_widget.is_connected = port.is_connected()

            # Create inline widget for non-FLOW input ports
            inline_widget = create_inline_widget_for_port(port)
            if inline_widget is not None:
                port_widget.set_inline_widget(inline_widget)
                # Connect inline widget value changes to port model updates
                self._connect_inline_widget_signals(port.name, inline_widget)

        # Create output port widgets
        for port in self._node.output_ports:
            port_widget = PortWidget(port, is_input=False, parent_node=self)
            self._output_port_widgets[port.name] = port_widget

            # Create label
            label = PortLabelWidget(port, is_input=False, parent=self)
            self._port_labels.append(label)

            # Update connected state
            port_widget.is_connected = port.is_connected()

    def _setup_code_preview(self) -> None:
        """
        Set up the code preview section if the node supports it.

        Checks if the node has a get_code_preview() method that returns
        a non-None value and creates the necessary UI elements for
        displaying the code preview.
        """
        # Check if the node has a get_code_preview method and returns content
        if hasattr(self._node, 'get_code_preview'):
            code_preview = self._node.get_code_preview()
            if code_preview is not None:
                self._has_code_preview = True
                self._create_code_preview_text_item()

    def _create_code_preview_text_item(self) -> None:
        """
        Create and configure the QGraphicsTextItem for code preview.

        The text item is configured as read-only and uses a monospace font
        suitable for displaying code. It is positioned within the code preview
        section of the node widget.
        """
        self._code_preview_text_item = QGraphicsTextItem(self)

        # Configure the text item as read-only
        self._code_preview_text_item.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False
        )
        self._code_preview_text_item.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False
        )

        # Set up monospace font for code
        code_font = QFont("Consolas", self.CODE_PREVIEW_FONT_SIZE)
        code_font.setStyleHint(QFont.StyleHint.Monospace)
        self._code_preview_text_item.setFont(code_font)

        # Set default text color
        self._code_preview_text_item.setDefaultTextColor(
            QColor(self.CODE_PREVIEW_TEXT_COLOR)
        )

        # Set text width for wrapping
        self._code_preview_text_item.setTextWidth(
            self._width - self.CODE_PREVIEW_PADDING * 2
        )

        # Create syntax highlighter for the text document
        self._code_preview_highlighter = CodePreviewSyntaxHighlighter(
            self._code_preview_text_item.document()
        )

    def _position_code_preview_text_item(self) -> None:
        """
        Position the code preview text item within the code preview section.

        This method calculates the correct position for the code preview
        based on the title bar height and positions the QGraphicsTextItem.
        """
        if self._code_preview_text_item is None:
            return

        code_section_y = self.TITLE_HEIGHT

        # Position the text item with padding
        self._code_preview_text_item.setPos(
            self.CODE_PREVIEW_PADDING,
            code_section_y + self.CODE_PREVIEW_PADDING
        )

        # Update text width for proper wrapping
        self._code_preview_text_item.setTextWidth(
            self._width - self.CODE_PREVIEW_PADDING * 2
        )

    def _update_code_preview_text_item(self) -> None:
        """
        Update the code preview text item content.

        This method updates the displayed code text from the node's
        get_code_preview() method. Syntax highlighting is automatically
        applied by the CodePreviewSyntaxHighlighter when the document
        content changes.
        """
        if self._code_preview_text_item is None:
            return

        # Get the code preview from the node
        code_preview = self._node.get_code_preview()
        if code_preview is None:
            return

        # Apply truncation if needed
        display_code = self._get_truncated_code_preview(code_preview)

        # Set the text content as plain text
        # The QSyntaxHighlighter will automatically apply highlighting
        self._code_preview_text_item.setPlainText(display_code)

    def _get_truncated_code_preview(self, code: str) -> str:
        """
        Get the code preview with truncation if it exceeds max lines.

        Args:
            code: The full code preview string.

        Returns:
            The code string, truncated to MAX_CODE_PREVIEW_LINES if needed.
        """
        lines = code.split('\n')
        if len(lines) > self.MAX_CODE_PREVIEW_LINES:
            truncated_lines = lines[:self.MAX_CODE_PREVIEW_LINES]
            truncated_lines.append("...")
            return '\n'.join(truncated_lines)
        return code

    def _calculate_size(self) -> None:
        """Calculate the required size based on ports, content, and inline widgets.

        This method calculates the minimum dimensions required to display all
        node content including:
        - Title bar with node name
        - Optional code preview section (for nodes with get_code_preview)
        - Port circles and labels for both input and output ports
        - Inline value widgets for input ports (when present)

        The width calculation accounts for:
        - Title text width
        - Input port column: port circle + inline widget + label
        - Output port column: label + port circle
        - Padding and spacing between elements

        The height calculation is based on the maximum number of ports
        on either side of the node, plus the code preview section if present.
        """
        # Calculate width based on title and port labels
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        font_metrics = QFontMetrics(font)
        title_width = font_metrics.horizontalAdvance(self._node.name) + self.PADDING * 4

        # Calculate width needed for port labels
        port_font = QFont("Segoe UI", 9)
        port_metrics = QFontMetrics(port_font)

        max_input_width = 0
        max_output_width = 0
        max_inline_widget_width = 0

        for port in self._node.input_ports:
            display_name = port.name.replace("_", " ").title()
            label_width = port_metrics.horizontalAdvance(display_name)
            max_input_width = max(max_input_width, label_width)

            # Check if this port has an inline widget and get its width
            port_widget = self._input_port_widgets.get(port.name)
            if port_widget is not None:
                inline_width = port_widget.get_inline_widget_width()
                max_inline_widget_width = max(max_inline_widget_width, inline_width)

        for port in self._node.output_ports:
            display_name = port.name.replace("_", " ").title()
            width = port_metrics.horizontalAdvance(display_name)
            max_output_width = max(max_output_width, width)

        # Total width needs to fit both columns with spacing
        # Layout: [port circle][inline widget][input label]...[output label][port circle]
        # Include inline widget width in the calculation
        port_width = (
            PortWidget.PORT_RADIUS * 2  # Input port circle
            + max_inline_widget_width  # Inline widget width (includes offset)
            + max_input_width  # Input label
            + self.PADDING * 4  # Central spacing and padding
            + max_output_width  # Output label
            + PortWidget.PORT_RADIUS * 2  # Output port circle
        )

        self._width = max(self.MIN_WIDTH, title_width, port_width)

        # Calculate height based on number of ports
        num_input_ports = len(self._node.input_ports)
        num_output_ports = len(self._node.output_ports)
        max_ports = max(num_input_ports, num_output_ports, 1)

        body_height = max_ports * self.PORT_SPACING + self.PADDING
        self._height = self.TITLE_HEIGHT + body_height

        # Add height for code preview section if present
        if self._has_code_preview:
            self._height += self.CODE_PREVIEW_HEIGHT

        # Position port widgets
        self._position_ports()

        # Position and update code preview text item if present
        if self._has_code_preview:
            self._position_code_preview_text_item()
            self._update_code_preview_text_item()

    def _position_ports(self) -> None:
        """Position all port widgets, inline widgets, and their labels.

        This method positions:
        1. Input port circles on the left edge of the node
        2. Output port circles on the right edge of the node
        3. Inline value widgets for input ports (to the right of port circles)
        4. Port labels (accounting for inline widget widths)

        If a code preview section is present, ports are positioned below it.
        """
        # Calculate the starting y offset (below title and optional code preview)
        base_y_offset = self.TITLE_HEIGHT
        if self._has_code_preview:
            base_y_offset += self.CODE_PREVIEW_HEIGHT

        # Position input ports on the left
        y_offset = base_y_offset + self.PADDING + self.PORT_SPACING / 2
        for i, (name, port_widget) in enumerate(self._input_port_widgets.items()):
            x = 0  # Left edge
            y = y_offset + i * self.PORT_SPACING
            port_widget.setPos(x, y)

            # Update inline widget position if present
            port_widget.update_inline_widget_position()

        # Position output ports on the right
        y_offset = base_y_offset + self.PADDING + self.PORT_SPACING / 2
        for i, (name, port_widget) in enumerate(self._output_port_widgets.items()):
            x = self._width  # Right edge
            y = y_offset + i * self.PORT_SPACING
            port_widget.setPos(x, y)

        # Position labels, accounting for inline widgets on input ports
        for label in self._port_labels:
            port_name = label.port.name
            if label.is_input and port_name in self._input_port_widgets:
                port_widget = self._input_port_widgets[port_name]
                has_inline = port_widget.has_inline_widget
                inline_width = port_widget.get_inline_widget_width() if has_inline else 0
                label.adjust_position(
                    port_widget,
                    self._width,
                    has_inline_widget=has_inline,
                    inline_widget_width=inline_width
                )
            elif not label.is_input and port_name in self._output_port_widgets:
                label.adjust_position(self._output_port_widgets[port_name], self._width)

    @property
    def node(self) -> BaseNode:
        """Get the node model."""
        return self._node

    @property
    def node_id(self) -> str:
        """Get the node ID."""
        return self._node.id

    @property
    def width(self) -> float:
        """Get the node width."""
        return self._width

    @property
    def height(self) -> float:
        """Get the node height."""
        return self._height

    @property
    def has_code_preview(self) -> bool:
        """Check if this node widget has a code preview section."""
        return self._has_code_preview

    @property
    def has_execution_errors(self) -> bool:
        """Check if this node has any execution errors.

        Returns:
            True if the node model has execution errors, False otherwise.
        """
        return self._node.has_execution_errors()

    def _get_error_indicator_rect(self) -> QRectF:
        """Calculate and return the error indicator button rectangle.

        The error indicator is positioned at the bottom-right corner of the node,
        inside the node bounds, with a small margin from the edge.

        Returns:
            QRectF representing the error indicator button bounds.
        """
        size = self.ERROR_INDICATOR_SIZE
        margin = self.ERROR_INDICATOR_MARGIN
        x = self._width - size - margin
        y = self._height - size - margin
        return QRectF(x, y, size, size)

    def _draw_error_indicator(self, painter: QPainter) -> None:
        """Draw the error indicator button if the node has execution errors.

        The error indicator is a small circular button with an exclamation mark
        icon, positioned at the bottom-right corner of the node. It appears only
        when the node has execution errors and can be clicked to show error details.

        Args:
            painter: The QPainter to use for drawing.
        """
        if not self.has_execution_errors:
            return

        # Calculate the error indicator rectangle
        self._error_indicator_rect = self._get_error_indicator_rect()
        rect = self._error_indicator_rect

        # Determine background color (lighter on hover)
        if self._error_indicator_hovered:
            bg_color = QColor(self.ERROR_INDICATOR_HOVER_COLOR)
        else:
            bg_color = QColor(self.ERROR_INDICATOR_COLOR)

        # Draw circular background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        center = rect.center()
        radius = rect.width() / 2
        painter.drawEllipse(center, radius, radius)

        # Draw border for better visibility
        painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius - 1, radius - 1)

        # Draw exclamation mark icon
        icon_color = QColor(self.ERROR_INDICATOR_ICON_COLOR)
        painter.setPen(QPen(icon_color, 2))

        # Calculate icon dimensions relative to button size
        icon_center_x = center.x()
        icon_top = center.y() - radius * 0.45
        icon_bottom = center.y() + radius * 0.45

        # Draw the exclamation line (top part)
        painter.drawLine(
            QPointF(icon_center_x, icon_top),
            QPointF(icon_center_x, center.y() + radius * 0.1)
        )

        # Draw the exclamation dot (bottom part)
        dot_y = icon_bottom - 1
        painter.setBrush(QBrush(icon_color))
        painter.drawEllipse(QPointF(icon_center_x, dot_y), 1.5, 1.5)

    def _is_point_in_error_indicator(self, pos: QPointF) -> bool:
        """Check if a point is within the error indicator button bounds.

        Args:
            pos: The point to check, in local coordinates.

        Returns:
            True if the point is within the error indicator button, False otherwise.
        """
        if not self.has_execution_errors or self._error_indicator_rect is None:
            return False
        return self._error_indicator_rect.contains(pos)

    def update_code_preview(self) -> None:
        """
        Update the code preview display.

        Call this method when the node's properties change in a way that
        affects the generated code preview. The code preview text will be
        refreshed from the node's get_code_preview() method.
        """
        if self._has_code_preview:
            self._update_code_preview_text_item()
            self.update()

    def get_input_port_widget(self, port_name: str) -> Optional[PortWidget]:
        """Get an input port widget by name."""
        return self._input_port_widgets.get(port_name)

    def get_output_port_widget(self, port_name: str) -> Optional[PortWidget]:
        """Get an output port widget by name."""
        return self._output_port_widgets.get(port_name)

    def get_all_port_widgets(self) -> List[PortWidget]:
        """Get all port widgets."""
        return list(self._input_port_widgets.values()) + list(self._output_port_widgets.values())

    def update_execution_state(self) -> None:
        """Update the visual appearance based on execution state.

        This method updates the execution state indicator color and applies
        a glowing shadow effect when the node is in RUNNING state to provide
        clear visual feedback during script execution.
        """
        state_name = self._node.execution_state.name
        self._execution_state_color = QColor(EXECUTION_STATE_COLORS.get(state_name, "#808080"))

        # Apply glowing effect based on execution state
        self._update_glow_effect(state_name)

        self.update()
        # Process events to ensure immediate visual update
        QApplication.processEvents()

    def _update_glow_effect(self, state_name: str) -> None:
        """Update the glow parameters based on execution state and selection.

        Stores glow colour/size so paint() can render it manually.
        This avoids QGraphicsDropShadowEffect which breaks
        QGraphicsScene.items() hit-testing (BSP tree corruption).

        Args:
            state_name: The name of the current execution state.
        """
        if state_name == "RUNNING":
            self._glow_color = QColor(33, 150, 243, 100)
            self._glow_radius = 10
        elif state_name == "ERROR":
            self._glow_color = QColor(244, 67, 54, 90)
            self._glow_radius = 8
        elif state_name == "COMPLETED":
            self._glow_color = QColor(76, 175, 80, 90)
            self._glow_radius = 8
        elif self._is_selected:
            self._glow_color = QColor(0, 170, 255, 70)
            self._glow_radius = 8
        else:
            self._glow_color = None
            self._glow_radius = 0

        self.prepareGeometryChange()

    def _draw_selection_markers(self, painter: QPainter) -> None:
        """Draw corner selection markers for the node.

        Args:
            painter: The QPainter to use for drawing.
        """
        marker_size = 6
        marker_color = QColor(SELECTION_COLORS["corner_marker"])

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(marker_color))

        # Top-left corner marker
        painter.drawRect(QRectF(-2, -2, marker_size, marker_size))

        # Top-right corner marker
        painter.drawRect(QRectF(self._width - marker_size + 2, -2, marker_size, marker_size))

        # Bottom-left corner marker
        painter.drawRect(QRectF(-2, self._height - marker_size + 2, marker_size, marker_size))

        # Bottom-right corner marker
        painter.drawRect(QRectF(
            self._width - marker_size + 2,
            self._height - marker_size + 2,
            marker_size,
            marker_size
        ))

    def _draw_code_preview_section(self, painter: QPainter) -> None:
        """
        Draw the code preview section background.

        The code text itself is rendered by the QGraphicsTextItem child widget,
        which provides better text rendering and supports syntax highlighting.
        This method only draws the background for the code preview section.

        Args:
            painter: The QPainter to use for drawing.
        """
        # Code preview section background (below title bar)
        code_rect = QRectF(
            0,
            self.TITLE_HEIGHT,
            self._width,
            self.CODE_PREVIEW_HEIGHT
        )
        code_bg_color = QColor(self.CODE_PREVIEW_BG_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(code_bg_color))
        painter.drawRect(code_rect)

        # Draw separator line below code preview section
        separator_y = self.TITLE_HEIGHT + self.CODE_PREVIEW_HEIGHT
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(QPointF(0, separator_y), QPointF(self._width, separator_y))

    def update_port_connections(self) -> None:
        """Update the visual state of all ports based on their connection status."""
        for port in self._node.input_ports:
            if port.name in self._input_port_widgets:
                self._input_port_widgets[port.name].is_connected = port.is_connected()

        for port in self._node.output_ports:
            if port.name in self._output_port_widgets:
                self._output_port_widgets[port.name].is_connected = port.is_connected()

    def recalculate_size(self) -> None:
        """Recalculate and update the node size to accommodate all content.

        Call this method when the node's content changes in a way that
        affects its size, such as:
        - Adding or removing inline widgets
        - Changing port labels
        - Any other dynamic content changes

        This method will:
        1. Notify the scene that the geometry is about to change
        2. Recalculate the width and height
        3. Reposition all ports and inline widgets
        4. Update the visual display
        """
        self.prepareGeometryChange()
        self._calculate_size()
        self.update()

    def update_validation_state(self) -> None:
        """Update the visual appearance based on code validation state.

        Checks if the node has validation state properties (like CodeNode)
        and updates the visual indicator accordingly.
        """
        # Check if node supports validation state
        if hasattr(self._node, 'is_code_valid'):
            self._has_validation_errors = not self._node.is_code_valid
        else:
            self._has_validation_errors = False

        self.update()

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle of the node."""
        # Include port radius, shadow offset, and glow radius in bounds
        glow = self._glow_radius
        pad = max(PortWidget.PORT_RADIUS + 2, glow)
        return QRectF(
            -pad,
            -pad,
            self._width + pad + max(PortWidget.PORT_RADIUS + 2, self._shadow_offset_x) + pad,
            self._height + pad + max(2, self._shadow_offset_y) + pad,
        )

    def shape(self) -> QPainterPath:
        """Return the shape for collision detection."""
        path = QPainterPath()
        path.addRoundedRect(
            0, 0, self._width, self._height,
            self.CORNER_RADIUS, self.CORNER_RADIUS
        )
        return path

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the node widget."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Determine colors based on selection and execution state
        is_selected = self.isSelected()
        body_color = self._body_color_selected if is_selected else self._body_color

        # Determine border color based on execution state
        state_name = self._node.execution_state.name
        if state_name == "RUNNING":
            border_color = QColor(33, 150, 243)  # Bright blue for running
            border_width = 3
        elif state_name == "ERROR":
            border_color = QColor(244, 67, 54)  # Red for error
            border_width = 3
        elif state_name == "COMPLETED":
            border_color = QColor(76, 175, 80)  # Green for completed
            border_width = 2
        elif is_selected:
            border_color = self._border_color_selected
            border_width = 2
        else:
            border_color = self._border_color
            border_width = 1

        # Draw manual drop shadow (replaces QGraphicsDropShadowEffect)
        shadow_rect = QRectF(
            self._shadow_offset_x,
            self._shadow_offset_y,
            self._width,
            self._height,
        )
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._shadow_color))
        painter.drawPath(shadow_path)

        # Draw glow effect for execution state / selection
        if self._glow_color and self._glow_radius > 0:
            glow_r = self._glow_radius
            for i in range(3, 0, -1):
                spread = glow_r * i / 3
                c = QColor(self._glow_color)
                c.setAlpha(self._glow_color.alpha() // i)
                glow_rect = QRectF(
                    -spread, -spread,
                    self._width + spread * 2,
                    self._height + spread * 2,
                )
                glow_path = QPainterPath()
                glow_path.addRoundedRect(
                    glow_rect,
                    self.CORNER_RADIUS + spread,
                    self.CORNER_RADIUS + spread,
                )
                painter.setBrush(QBrush(c))
                painter.drawPath(glow_path)

        # Draw body background
        body_rect = QRectF(0, 0, self._width, self._height)
        body_path = QPainterPath()
        body_path.addRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(body_color))
        painter.drawPath(body_path)

        # Draw title bar with gradient
        title_rect = QRectF(0, 0, self._width, self.TITLE_HEIGHT)
        title_path = QPainterPath()
        # Create rounded rect for top only
        title_path.moveTo(self.CORNER_RADIUS, 0)
        title_path.lineTo(self._width - self.CORNER_RADIUS, 0)
        title_path.arcTo(
            self._width - self.CORNER_RADIUS * 2, 0,
            self.CORNER_RADIUS * 2, self.CORNER_RADIUS * 2,
            90, -90
        )
        title_path.lineTo(self._width, self.TITLE_HEIGHT)
        title_path.lineTo(0, self.TITLE_HEIGHT)
        title_path.lineTo(0, self.CORNER_RADIUS)
        title_path.arcTo(0, 0, self.CORNER_RADIUS * 2, self.CORNER_RADIUS * 2, 180, -90)
        title_path.closeSubpath()

        # Create gradient for title
        gradient = QLinearGradient(0, 0, 0, self.TITLE_HEIGHT)
        gradient.setColorAt(0, self._title_color)
        gradient.setColorAt(1, self._title_color_dark)

        painter.setBrush(QBrush(gradient))
        painter.drawPath(title_path)

        # Draw title text (only if not currently editing name)
        if not self._is_editing_name:
            painter.setPen(QPen(self._title_text_color))
            font = QFont("Segoe UI", 11, QFont.Weight.Bold)
            painter.setFont(font)
            text_rect = QRectF(self.PADDING, 0, self._width - self.PADDING * 2, self.TITLE_HEIGHT)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._node.name)

        # Draw execution state indicator (small circle in title bar)
        indicator_radius = 5
        indicator_x = self._width - self.PADDING - indicator_radius
        indicator_y = self.TITLE_HEIGHT / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._execution_state_color))
        painter.drawEllipse(
            QPointF(indicator_x, indicator_y),
            indicator_radius, indicator_radius
        )

        # Draw validation warning indicator if there are syntax errors
        if self._has_validation_errors:
            # Draw a warning triangle/badge near the execution indicator
            warning_x = indicator_x - 16
            warning_y = indicator_y - 5
            warning_size = 10

            # Draw orange warning background
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(VALIDATION_STATE_COLORS["invalid"])))

            # Draw a small warning triangle
            from PyQt6.QtGui import QPolygonF
            triangle = QPolygonF([
                QPointF(warning_x, warning_y + warning_size),
                QPointF(warning_x + warning_size / 2, warning_y),
                QPointF(warning_x + warning_size, warning_y + warning_size),
            ])
            painter.drawPolygon(triangle)

            # Draw exclamation mark
            painter.setPen(QPen(QColor("#FFFFFF"), 1.5))
            painter.drawLine(
                QPointF(warning_x + warning_size / 2, warning_y + 3),
                QPointF(warning_x + warning_size / 2, warning_y + 6)
            )
            painter.drawPoint(QPointF(warning_x + warning_size / 2, warning_y + 8))

        # Draw separator line below title
        separator_y = self.TITLE_HEIGHT
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(QPointF(0, separator_y), QPointF(self._width, separator_y))

        # Draw code preview section if present
        if self._has_code_preview:
            self._draw_code_preview_section(painter)

        # Draw border
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # Draw selection corner markers if selected
        if is_selected:
            self._draw_selection_markers(painter)

        # Draw error indicator button if node has execution errors
        self._draw_error_indicator(painter)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:
        """Handle item changes such as position or selection."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Snap to grid if enabled (before position is applied)
            pos = value
            scene = self.scene()
            if scene is not None and hasattr(scene, 'snap_to_grid_enabled'):
                if scene.snap_to_grid_enabled:
                    snapped_x, snapped_y = scene.snap_to_grid(pos.x(), pos.y())
                    return QPointF(snapped_x, snapped_y)

        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Update node model position
            pos = value
            self._node.position.x = pos.x()
            self._node.position.y = pos.y()
            # Emit signal
            self.signals.position_changed.emit(self._node.id, pos.x(), pos.y())

        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._is_selected = bool(value)
            self.signals.selected_changed.emit(self._node.id, self._is_selected)
            # Update glow effect to show selection state
            state_name = self._node.execution_state.name
            self._update_glow_effect(state_name)
            self.update()

        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event: object) -> None:
        """Handle double-click to edit node name (if on title) or open node editor."""
        # Check if the double-click is on the title bar area
        click_pos = event.pos()
        if click_pos.y() < self.TITLE_HEIGHT:
            # Double-click on title bar - start name editing
            self._start_name_editing()
            event.accept()
            return

        # Double-click elsewhere - emit signal for node editor
        self.signals.double_clicked.emit(self._node.id)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: object) -> None:
        """Handle mouse press events.

        Checks if the click is on the error indicator button and emits
        the error_indicator_clicked signal if so. Otherwise, delegates
        to the parent class for normal selection/drag behavior.
        Records the position at press time for move tracking.
        """
        if self._is_point_in_error_indicator(event.pos()):
            # Emit signal to show error popup
            self.signals.error_indicator_clicked.emit(self._node.id)
            event.accept()
            return
        # Record position before drag starts
        self._drag_start_x = self.x()
        self._drag_start_y = self.y()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:
        """Handle mouse release events.

        If the node was dragged to a new position, emits the move_finished
        signal with old and new coordinates for undo/redo support.
        """
        super().mouseReleaseEvent(event)
        # Check if position changed during drag
        if hasattr(self, '_drag_start_x'):
            new_x = self.x()
            new_y = self.y()
            if new_x != self._drag_start_x or new_y != self._drag_start_y:
                self.signals.move_finished.emit(
                    self._node.id,
                    self._drag_start_x, self._drag_start_y,
                    new_x, new_y,
                )

    def hoverMoveEvent(self, event: object) -> None:
        """Handle hover move events for cursor changes over error indicator.

        Updates the hover state and cursor when moving over the error indicator
        button to provide visual feedback that it's clickable.
        """
        if self._is_point_in_error_indicator(event.pos()):
            if not self._error_indicator_hovered:
                self._error_indicator_hovered = True
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                self.update()  # Redraw with hover state
        else:
            if self._error_indicator_hovered:
                self._error_indicator_hovered = False
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                self.update()  # Redraw without hover state
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: object) -> None:
        """Handle hover leave events to reset error indicator hover state."""
        if self._error_indicator_hovered:
            self._error_indicator_hovered = False
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self.update()
        super().hoverLeaveEvent(event)

    def keyPressEvent(self, event: object) -> None:
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape and self._is_editing_name:
            # Cancel name editing on Escape
            self.cancel_name_editing()
            event.accept()
        elif event.key() == Qt.Key.Key_Delete:
            self.signals.delete_requested.emit(self._node.id)
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event: object) -> None:
        """Handle right-click context menu."""
        from PyQt6.QtWidgets import QMenu, QColorDialog
        from PyQt6.QtGui import QAction

        menu = QMenu()

        # Change color action
        change_color_action = QAction("Change Color...", menu)
        change_color_action.triggered.connect(self._show_color_picker)
        menu.addAction(change_color_action)

        # Reset color action (only show if custom color is set)
        if self._node.custom_color:
            reset_color_action = QAction("Reset to Default Color", menu)
            reset_color_action.triggered.connect(self._reset_color)
            menu.addAction(reset_color_action)

        menu.addSeparator()

        # Delete action
        delete_action = QAction("Delete", menu)
        delete_action.setShortcut("Delete")
        delete_action.triggered.connect(lambda: self.signals.delete_requested.emit(self._node.id))
        menu.addAction(delete_action)

        # Show menu at cursor position
        menu.exec(event.screenPos())

    def _show_color_picker(self) -> None:
        """Show a color picker dialog to change the node's color."""
        from PyQt6.QtWidgets import QColorDialog

        # Get current color
        current_color = QColor(self._node.display_color)

        # Show color picker dialog
        color = QColorDialog.getColor(
            current_color,
            None,
            f"Choose Color for {self._node.name}"
        )

        if color.isValid():
            # Set the custom color on the node
            self._node.custom_color = color.name()
            # Update the visual appearance
            self.update_color()
            # Emit signal to notify about the color change
            self.signals.color_changed.emit(self._node.id, color.name())

    def _reset_color(self) -> None:
        """Reset the node's color to the default for its type."""
        self._node.custom_color = None
        self.update_color()
        # Emit signal to notify about the color change (empty string = reset)
        self.signals.color_changed.emit(self._node.id, "")

    def update_color(self) -> None:
        """Update the visual colors from the node model.

        Call this method after changing the node's custom_color property
        to refresh the title bar gradient.
        """
        self._setup_colors()
        self.update()

    def sync_from_model(self) -> None:
        """Synchronize the widget state from the node model."""
        # Update position
        self.setPos(self._node.position.x, self._node.position.y)
        # Update execution state
        self.update_execution_state()
        # Rebuild port widgets if the model's ports have changed
        self._rebuild_port_widgets_if_needed()
        # Update port connections
        self.update_port_connections()
        # Update validation state
        self.update_validation_state()
        # Update inline widget values from port model
        self.sync_inline_widgets_from_ports()
        # Update colors (in case custom_color changed)
        self._setup_colors()
        # Update code preview if present
        if self._has_code_preview:
            self._update_code_preview_text_item()
        # Redraw
        self.update()

    def _rebuild_port_widgets_if_needed(self) -> None:
        """Rebuild port widgets if the node model's ports don't match the current widgets."""
        model_input_names = {p.name for p in self._node.input_ports}
        model_output_names = {p.name for p in self._node.output_ports}
        widget_input_names = set(self._input_port_widgets.keys())
        widget_output_names = set(self._output_port_widgets.keys())

        if model_input_names == widget_input_names and model_output_names == widget_output_names:
            return

        self.prepareGeometryChange()

        # Remove old port widgets and labels
        for pw in self._input_port_widgets.values():
            if pw.scene():
                pw.scene().removeItem(pw)
        for pw in self._output_port_widgets.values():
            if pw.scene():
                pw.scene().removeItem(pw)
        for label in self._port_labels:
            if label.scene():
                label.scene().removeItem(label)

        self._input_port_widgets.clear()
        self._output_port_widgets.clear()
        self._port_labels.clear()

        # Recreate port widgets from current model
        self._create_port_widgets()
        self._calculate_size()

    def sync_inline_widgets_from_ports(self) -> None:
        """
        Synchronize all inline widget values from port models.

        Call this method after deserializing a node or when port inline_value
        properties have been changed externally to update the widget displays.
        """
        for port_name, port_widget in self._input_port_widgets.items():
            if port_widget.has_inline_widget:
                port_widget.sync_inline_widget_from_port()

    def _connect_inline_widget_signals(
        self,
        port_name: str,
        inline_widget: object,
    ) -> None:
        """
        Connect inline widget signals to node-level handlers.

        This method connects the inline value widget's signals to handlers
        that will emit node-level signals when values change. The port
        model is automatically updated by the InlineValueWidget itself.

        Args:
            port_name: The name of the port this widget is attached to.
            inline_widget: The InlineValueWidget instance to connect.
        """
        from visualpython.nodes.views.inline_value_widget import InlineValueWidget

        if not isinstance(inline_widget, InlineValueWidget):
            return

        # Capture initial value for undo tracking
        port = self._node.get_input_port(port_name)
        if port is not None:
            self._inline_old_values[port_name] = port.inline_value

        # Connect value_changed signal to emit node-level signal
        # Use a closure to capture the port_name
        def on_value_changed(new_value: object) -> None:
            self._on_inline_value_changed(port_name, new_value)

        inline_widget.signals.value_changed.connect(on_value_changed)

    def _on_inline_value_changed(self, port_name: str, new_value: object) -> None:
        """
        Handle inline widget value change.

        This method is called when an inline widget's value changes. The
        port model has already been updated by the InlineValueWidget, so
        this method only emits the node-level signal to notify external
        listeners (such as the graph editor or undo/redo system).

        Args:
            port_name: The name of the port whose value changed.
            new_value: The new value from the inline widget.
        """
        old_value = self._inline_old_values.get(port_name)
        self._inline_old_values[port_name] = new_value

        # Emit signal to notify external listeners
        self.signals.inline_value_changed.emit(
            self._node.id,
            port_name,
            old_value,
            new_value,
        )

    # Node Name Editing

    def _start_name_editing(self) -> None:
        """
        Start inline editing of the node name.

        Creates a QLineEdit widget positioned over the title bar for the user
        to edit the node name directly in the graph.
        """
        if self._is_editing_name:
            return

        self._is_editing_name = True

        # Create the line edit widget
        self._name_edit_widget = QLineEdit()
        self._name_edit_widget.setText(self._node.name)
        self._name_edit_widget.selectAll()

        # Style the line edit to match the node title bar
        self._name_edit_widget.setStyleSheet("""
            QLineEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 2px solid #0E639C;
                border-radius: 4px;
                padding: 2px 6px;
                font-family: "Segoe UI";
                font-size: 11pt;
                font-weight: bold;
            }
            QLineEdit:focus {
                border: 2px solid #007ACC;
            }
        """)

        # Set fixed size based on title bar dimensions
        edit_width = self._width - self.PADDING * 2 - 20  # Leave space for execution indicator
        self._name_edit_widget.setFixedSize(int(edit_width), int(self.TITLE_HEIGHT - 4))

        # Create proxy widget to embed in the graphics scene
        self._name_edit_proxy = QGraphicsProxyWidget(self)
        self._name_edit_proxy.setWidget(self._name_edit_widget)
        self._name_edit_proxy.setPos(self.PADDING, 2)
        self._name_edit_proxy.setZValue(100)  # Above everything else

        # Connect signals
        # Note: We only connect editingFinished, not returnPressed, because:
        # 1. editingFinished fires when Enter is pressed (after returnPressed)
        # 2. editingFinished fires when the widget loses focus
        # Connecting both would cause _finish_name_editing to be called twice on Enter
        self._name_edit_widget.editingFinished.connect(self._finish_name_editing)

        # Focus the edit widget
        self._name_edit_widget.setFocus()

        # Temporarily disable node movement while editing
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        self.update()

    def _finish_name_editing(self) -> None:
        """
        Finish inline editing of the node name.

        Applies the new name to the node model and cleans up the edit widget.
        Emits name_changed signal if the name actually changed.

        This method uses a secondary guard (_is_finishing_name_edit) to prevent
        reentrant calls that can occur when editingFinished fires multiple times
        during widget cleanup.

        The text value is captured immediately at the start (before any guards)
        and stored in _pending_name_value to ensure we have the value even if
        the widget gets destroyed during cleanup.
        """
        # Capture text value immediately before any guards or cleanup
        # This ensures we have the value even if widget state becomes inconsistent
        if self._name_edit_widget is not None:
            self._pending_name_value = self._name_edit_widget.text().strip()

        if not self._is_editing_name:
            return

        # Secondary guard to prevent reentrant calls during cleanup
        if self._is_finishing_name_edit:
            return
        self._is_finishing_name_edit = True

        # Use the captured value (already stored in _pending_name_value above)
        new_name = self._pending_name_value if self._pending_name_value is not None else ""
        old_name = self._node.name

        # Clean up the edit widget
        self._is_editing_name = False

        if self._name_edit_proxy is not None:
            self._name_edit_proxy.setWidget(None)
            self.scene().removeItem(self._name_edit_proxy)
            self._name_edit_proxy = None

        if self._name_edit_widget is not None:
            self._name_edit_widget.deleteLater()
            self._name_edit_widget = None

        # Re-enable node movement
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        # Apply new name if changed and not empty
        if new_name and new_name != old_name:
            self._node.name = new_name
            # Emit signal to notify about the name change
            self.signals.name_changed.emit(self._node.id, old_name, new_name)
            # Recalculate size in case name width changed
            self.prepareGeometryChange()
            self._calculate_size()

        # Reset the guard flags and captured value
        self._is_finishing_name_edit = False
        self._pending_name_value = None

        self.update()

    def cancel_name_editing(self) -> None:
        """
        Cancel inline editing of the node name without applying changes.
        """
        if not self._is_editing_name:
            return

        self._is_editing_name = False
        self._pending_name_value = None  # Clear any captured value

        # Clean up the edit widget
        if self._name_edit_proxy is not None:
            self._name_edit_proxy.setWidget(None)
            self.scene().removeItem(self._name_edit_proxy)
            self._name_edit_proxy = None

        if self._name_edit_widget is not None:
            self._name_edit_widget.deleteLater()
            self._name_edit_widget = None

        # Re-enable node movement
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        self.update()

    @property
    def is_editing_name(self) -> bool:
        """Check if the node is currently in name editing mode."""
        return self._is_editing_name

    def __repr__(self) -> str:
        """String representation."""
        return f"NodeWidget(id='{self._node.id[:8]}...', name='{self._node.name}')"

    # View Mode Support

    def set_edit_mode(self, enabled: bool) -> None:
        """
        Set the widget to edit mode.

        In edit mode, the widget is fully interactive and editable.

        Args:
            enabled: Whether to enable edit mode.
        """
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, enabled)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, enabled)
        self.setAcceptHoverEvents(enabled)

        # Enable/disable inline widgets
        for port_widget in self._input_port_widgets.values():
            if port_widget.has_inline_widget:
                port_widget.set_inline_widget_enabled(enabled)

    def set_run_mode(self, enabled: bool) -> None:
        """
        Set the widget to run/debug mode.

        In run mode, the widget shows execution state prominently.

        Args:
            enabled: Whether to enable run mode.
        """
        if enabled:
            # Disable editing
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            # Keep selectable for inspection
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            # Disable inline widgets
            for port_widget in self._input_port_widgets.values():
                if port_widget.has_inline_widget:
                    port_widget.set_inline_widget_enabled(False)
        else:
            # Restore normal edit mode
            self.set_edit_mode(True)

        self.update()

    def set_collapsed_view(self, collapsed: bool) -> None:
        """
        Set the collapsed view state for subgraph nodes.

        This method is primarily used by subgraph nodes to toggle
        between showing full details and a compact representation.

        Args:
            collapsed: Whether to show collapsed view.
        """
        # Base implementation does nothing - subclasses can override
        pass
