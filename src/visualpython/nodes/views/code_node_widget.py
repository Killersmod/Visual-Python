"""
Code node visual widget with code display section.

This module provides a specialized NodeWidget for CodeNode that displays
the user's Python code within the node body, along with a documentation
header showing how to use inputs, outputs, globals, and case.
"""

from __future__ import annotations

import re
from typing import List, Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QColor,
    QPen,
    QPainter,
    QBrush,
    QFont,
    QFontMetrics,
    QPainterPath,
    QLinearGradient,
    QPolygonF,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsTextItem,
    QStyleOptionGraphicsItem,
    QWidget,
    QGraphicsSceneMouseEvent,
)

from visualpython.nodes.views.node_widget import NodeWidget, EXECUTION_STATE_COLORS, VALIDATION_STATE_COLORS
from visualpython.nodes.views.port_widget import PortWidget

if TYPE_CHECKING:
    from visualpython.nodes.models.code_node import CodeNode


# Documentation content for the collapsible header
DOCUMENTATION_EXAMPLES = [
    ("inputs", "inputs['value']", "Access input port values"),
    ("outputs", "outputs['result'] = x", "Set output port values"),
    ("globals", "globals.get('var')", "Shared state across nodes"),
    ("case", "case.x = value", "Per-execution shared state"),
]

DOCUMENTATION_COLLAPSED_TEXT = "? Usage: inputs, outputs, globals, case"
DOCUMENTATION_EXPANDED_HEADER = "Usage Examples:"


class CodePreviewHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter for Python code in the read-only code preview.

    This highlighter uses colors optimized for dark backgrounds, matching
    the code section's dark theme. It highlights Python keywords, strings,
    comments, numbers, function/class definitions, and built-in functions.

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

        # Decorator format (yellow)
        self._decorator_format = QTextCharFormat()
        self._decorator_format.setForeground(QColor("#d7ba7d"))

        # Self/cls format (light blue, italic)
        self._self_format = QTextCharFormat()
        self._self_format.setForeground(QColor("#9cdcfe"))
        self._self_format.setFontItalic(True)

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

        # Self and cls
        self._highlighting_rules.append(
            (re.compile(r"\b(self|cls)\b"), self._self_format)
        )

        # Function and class definitions
        self._highlighting_rules.append(
            (re.compile(r"\bdef\s+(\w+)"), self._definition_format)
        )
        self._highlighting_rules.append(
            (re.compile(r"\bclass\s+(\w+)"), self._definition_format)
        )

        # Decorators
        self._highlighting_rules.append(
            (re.compile(r"@\w+(\.\w+)*"), self._decorator_format)
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
        # Apply single-line rules
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

        # Handle multi-line strings
        self._handle_multiline_strings(text)

    def _handle_multiline_strings(self, text: str) -> None:
        """
        Handle multi-line string highlighting (triple quotes).

        Args:
            text: The text block to process.
        """
        # State: 0 = normal, 1 = in triple single quote, 2 = in triple double quote
        in_multiline = self.previousBlockState()
        if in_multiline == -1:
            in_multiline = 0

        # Triple quote patterns
        triple_single = "'''"
        triple_double = '"""'

        start = 0

        while start < len(text):
            if in_multiline == 0:
                # Look for start of multi-line string
                single_idx = text.find(triple_single, start)
                double_idx = text.find(triple_double, start)

                if single_idx == -1 and double_idx == -1:
                    break

                if single_idx == -1:
                    start_idx = double_idx
                    in_multiline = 2
                elif double_idx == -1:
                    start_idx = single_idx
                    in_multiline = 1
                elif single_idx < double_idx:
                    start_idx = single_idx
                    in_multiline = 1
                else:
                    start_idx = double_idx
                    in_multiline = 2

                # Look for end on same line
                end_pattern = triple_single if in_multiline == 1 else triple_double
                end_idx = text.find(end_pattern, start_idx + 3)

                if end_idx != -1:
                    # String ends on same line
                    length = end_idx - start_idx + 3
                    self.setFormat(start_idx, length, self._string_format)
                    start = end_idx + 3
                    in_multiline = 0
                else:
                    # String continues to next line
                    self.setFormat(start_idx, len(text) - start_idx, self._string_format)
                    break
            else:
                # We're inside a multi-line string
                end_pattern = triple_single if in_multiline == 1 else triple_double
                end_idx = text.find(end_pattern, start)

                if end_idx != -1:
                    # String ends on this line
                    length = end_idx - start + 3
                    self.setFormat(start, length, self._string_format)
                    start = end_idx + 3
                    in_multiline = 0
                else:
                    # String continues to next line
                    self.setFormat(start, len(text) - start, self._string_format)
                    break

        self.setCurrentBlockState(in_multiline)


class CodeNodeWidget(NodeWidget):
    """
    Specialized visual representation of a CodeNode.

    Extends the base NodeWidget to provide:
    - A code display section showing the user's Python code
    - Python syntax highlighting for the code preview using CodePreviewHighlighter
    - Code truncation for long code snippets (max 5 lines with ellipsis)
    - A collapsible documentation header with usage examples

    The widget renders an additional code section below the title bar,
    displaying the Python code that will be executed by this node. The code
    is displayed with syntax highlighting using a dark theme color scheme
    that matches popular code editors like VS Code.

    Attributes:
        CODE_SECTION_HEIGHT: Height of the code display section in pixels.
        CODE_SECTION_PADDING: Padding within the code section.
        CODE_FONT_SIZE: Font size for code display.
        MAX_CODE_LINES: Maximum number of lines to display (truncation applied).
        DOC_HEADER_COLLAPSED_HEIGHT: Height when documentation is collapsed.
        DOC_HEADER_EXPANDED_HEIGHT: Height when documentation is expanded.
    """

    # Code section layout constants
    CODE_SECTION_HEIGHT = 80
    CODE_SECTION_PADDING = 8
    CODE_FONT_SIZE = 9
    MAX_CODE_LINES = 5

    # Documentation header layout constants
    DOC_HEADER_COLLAPSED_HEIGHT = 20
    DOC_HEADER_EXPANDED_HEIGHT = 90
    DOC_HEADER_PADDING = 6

    # Code section colors
    CODE_BG_COLOR = "#1e1e1e"  # Dark background like code editors
    CODE_TEXT_COLOR = "#d4d4d4"  # Light gray text
    CODE_PLACEHOLDER_COLOR = "#6a6a6a"  # Dimmer text for placeholders

    # Documentation header colors
    DOC_BG_COLOR = "#2d3748"  # Slightly blue-gray background
    DOC_BG_COLOR_HOVER = "#3d4758"  # Lighter on hover
    DOC_TEXT_COLOR = "#a0aec0"  # Muted text color
    DOC_HIGHLIGHT_COLOR = "#68d391"  # Green for keywords
    DOC_DESCRIPTION_COLOR = "#718096"  # Dimmer for descriptions

    def __init__(
        self,
        node: CodeNode,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """
        Initialize a code node widget.

        Args:
            node: The CodeNode model this widget represents.
            parent: Optional parent graphics item.
        """
        # Store typed reference to the code node BEFORE calling super().__init__()
        # because super().__init__() calls _calculate_size() which calls
        # _position_ports() which needs _code_node
        self._code_node: CodeNode = node

        # Documentation header state - must be initialized BEFORE super().__init__()
        # because _calculate_size() -> _position_ports() -> _get_doc_header_height()
        # accesses _doc_expanded during parent initialization
        self._doc_expanded: bool = False
        self._doc_header_hovered: bool = False

        # Initialize code preview text item placeholder - will be created after super().__init__()
        # We need this placeholder because _calculate_size() may be called during parent init
        self._code_text_item: Optional[QGraphicsTextItem] = None
        self._syntax_highlighter: Optional[CodePreviewHighlighter] = None

        # Now call parent __init__ which will trigger _calculate_size()
        super().__init__(node, parent)

        # Enable mouse tracking for hover effects on documentation header
        self.setAcceptHoverEvents(True)

        # Create the code preview text item (read-only) with syntax highlighting
        # This must happen after super().__init__() because we need to be a valid
        # QGraphicsItem for the text item to be our child
        self._code_text_item = self._create_code_text_item()
        self._syntax_highlighter = CodePreviewHighlighter(
            self._code_text_item.document()
        )

        # Now that the text item is created, position and update it
        self._position_code_text_item()
        self._update_code_text_item()

    def _get_doc_header_height(self) -> int:
        """Get the current documentation header height based on expanded state."""
        if self._doc_expanded:
            return self.DOC_HEADER_EXPANDED_HEIGHT
        return self.DOC_HEADER_COLLAPSED_HEIGHT

    def _create_code_text_item(self) -> QGraphicsTextItem:
        """
        Create and configure the QGraphicsTextItem for code preview.

        The text item is configured as read-only and uses a monospace font
        suitable for displaying code. It is positioned within the code section
        area of the node widget.

        Returns:
            A configured QGraphicsTextItem for displaying code.
        """
        text_item = QGraphicsTextItem(self)

        # Configure the text item as read-only
        # Note: QGraphicsTextItem doesn't have a direct read-only flag,
        # but we disable interaction flags to prevent editing
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

        # Set up monospace font for code
        code_font = QFont("Consolas", self.CODE_FONT_SIZE)
        code_font.setStyleHint(QFont.StyleHint.Monospace)
        text_item.setFont(code_font)

        # Set default text color
        text_item.setDefaultTextColor(QColor(self.CODE_TEXT_COLOR))

        # Set text width for wrapping (will be updated in _position_code_text_item)
        text_item.setTextWidth(self._width - self.CODE_SECTION_PADDING * 2)

        return text_item

    def _position_code_text_item(self) -> None:
        """
        Position the code text item within the code section.

        This method calculates the correct position for the code preview
        based on the current documentation header height and positions
        the QGraphicsTextItem accordingly.

        Note:
            This method is a no-op if the code text item hasn't been created
            yet (during initial parent __init__ call).
        """
        # Skip if text item not yet created (during parent __init__)
        if self._code_text_item is None:
            return

        doc_header_height = self._get_doc_header_height()
        code_section_y = self.TITLE_HEIGHT + doc_header_height

        # Position the text item with padding
        self._code_text_item.setPos(
            self.CODE_SECTION_PADDING,
            code_section_y + self.CODE_SECTION_PADDING
        )

        # Update text width for proper wrapping
        self._code_text_item.setTextWidth(self._width - self.CODE_SECTION_PADDING * 2)

    def _update_code_text_item(self) -> None:
        """
        Update the code text item content and styling.

        This method updates the displayed code text, applying appropriate
        styling for placeholder vs actual code content. Syntax highlighting
        is automatically applied by the CodePreviewHighlighter when the
        document content changes.

        Note:
            This method is a no-op if the code text item hasn't been created
            yet (during initial parent __init__ call).
        """
        # Skip if text item not yet created (during parent __init__)
        if self._code_text_item is None:
            return

        display_code = self._get_display_code()
        is_placeholder = not self._code_node.code.strip()

        # Set the appropriate text color based on whether this is placeholder text
        # For placeholder text, use a dimmed color; for actual code, use the
        # base light gray color (syntax highlighting will override specific tokens)
        if is_placeholder:
            self._code_text_item.setDefaultTextColor(QColor(self.CODE_PLACEHOLDER_COLOR))
        else:
            self._code_text_item.setDefaultTextColor(QColor(self.CODE_TEXT_COLOR))

        # Set the text content as plain text
        # The QSyntaxHighlighter attached to the document will automatically
        # apply syntax highlighting to the text content
        self._code_text_item.setPlainText(display_code)

    def _calculate_size(self) -> None:
        """Calculate the required size including the documentation header and code display section."""
        # Call base calculation first
        super()._calculate_size()

        # Add extra height for the documentation header and code section
        self._height += self._get_doc_header_height() + self.CODE_SECTION_HEIGHT

        # Ensure minimum width for code display and documentation
        self._width = max(self._width, 260)

        # Reposition ports to account for extra sections
        self._position_ports()

        # Position and update the code text item
        self._position_code_text_item()
        self._update_code_text_item()

    def _position_ports(self) -> None:
        """Position all port widgets accounting for the documentation header and code section."""
        # Input ports on the left - below documentation header and code section
        doc_header_height = self._get_doc_header_height()
        y_offset = (
            self.TITLE_HEIGHT
            + doc_header_height
            + self.CODE_SECTION_HEIGHT
            + self.PADDING
            + self.PORT_SPACING / 2
        )
        for i, (name, port_widget) in enumerate(self._input_port_widgets.items()):
            x = 0  # Left edge
            y = y_offset + i * self.PORT_SPACING
            port_widget.setPos(x, y)

            # Update inline widget position if present
            port_widget.update_inline_widget_position()

        # Output ports on the right
        y_offset = (
            self.TITLE_HEIGHT
            + doc_header_height
            + self.CODE_SECTION_HEIGHT
            + self.PADDING
            + self.PORT_SPACING / 2
        )
        for i, (name, port_widget) in enumerate(self._output_port_widgets.items()):
            x = self._width  # Right edge
            y = y_offset + i * self.PORT_SPACING
            port_widget.setPos(x, y)

        # Position labels
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

    def _get_display_code(self) -> str:
        """
        Get the code to display, with truncation if needed.

        Returns:
            The code string to display in the widget.
        """
        code = self._code_node.code.strip()

        if not code:
            return "# Enter Python code here..."

        # Split into lines and truncate if needed
        lines = code.split('\n')
        if len(lines) > self.MAX_CODE_LINES:
            truncated_lines = lines[:self.MAX_CODE_LINES]
            truncated_lines.append("...")
            return '\n'.join(truncated_lines)

        return code

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the code node widget with documentation header and code display section."""
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

        # Draw body background
        body_rect = QRectF(0, 0, self._width, self._height)
        body_path = QPainterPath()
        body_path.addRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(body_color))
        painter.drawPath(body_path)

        # Draw title bar with gradient
        title_path = self._create_title_path()
        gradient = QLinearGradient(0, 0, 0, self.TITLE_HEIGHT)
        gradient.setColorAt(0, self._title_color)
        gradient.setColorAt(1, self._title_color_dark)
        painter.setBrush(QBrush(gradient))
        painter.drawPath(title_path)

        # Draw title text
        painter.setPen(QPen(self._title_text_color))
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(font)
        text_rect = QRectF(self.PADDING, 0, self._width - self.PADDING * 2, self.TITLE_HEIGHT)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._node.name,
        )

        # Draw execution state indicator (small circle in title bar)
        indicator_radius = 5
        indicator_x = self._width - self.PADDING - indicator_radius
        indicator_y = self.TITLE_HEIGHT / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._execution_state_color))
        painter.drawEllipse(
            QPointF(indicator_x, indicator_y), indicator_radius, indicator_radius
        )

        # Draw validation warning indicator if there are syntax errors
        if self._has_validation_errors:
            self._draw_validation_warning(painter, indicator_x, indicator_y)

        # Draw separator line below title
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(
            QPointF(0, self.TITLE_HEIGHT), QPointF(self._width, self.TITLE_HEIGHT)
        )

        # Draw documentation header section
        doc_header_height = self._get_doc_header_height()
        self._draw_documentation_header(painter)

        # Draw separator below documentation header
        doc_header_bottom = self.TITLE_HEIGHT + doc_header_height
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(
            QPointF(0, doc_header_bottom), QPointF(self._width, doc_header_bottom)
        )

        # Draw code section
        self._draw_code_section(painter, doc_header_bottom)

        # Draw separator below code section
        code_section_bottom = doc_header_bottom + self.CODE_SECTION_HEIGHT
        painter.setPen(QPen(self._border_color, 1))
        painter.drawLine(
            QPointF(0, code_section_bottom), QPointF(self._width, code_section_bottom)
        )

        # Draw border around entire node
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # Draw selection corner markers if selected
        if is_selected:
            self._draw_selection_markers(painter)

    def _create_title_path(self) -> QPainterPath:
        """Create the path for the title bar with rounded top corners."""
        title_path = QPainterPath()
        # Create rounded rect for top only
        title_path.moveTo(self.CORNER_RADIUS, 0)
        title_path.lineTo(self._width - self.CORNER_RADIUS, 0)
        title_path.arcTo(
            self._width - self.CORNER_RADIUS * 2,
            0,
            self.CORNER_RADIUS * 2,
            self.CORNER_RADIUS * 2,
            90,
            -90,
        )
        title_path.lineTo(self._width, self.TITLE_HEIGHT)
        title_path.lineTo(0, self.TITLE_HEIGHT)
        title_path.lineTo(0, self.CORNER_RADIUS)
        title_path.arcTo(0, 0, self.CORNER_RADIUS * 2, self.CORNER_RADIUS * 2, 180, -90)
        title_path.closeSubpath()
        return title_path

    def _draw_documentation_header(self, painter: QPainter) -> None:
        """
        Draw the collapsible documentation header section.

        Shows usage examples for inputs, outputs, globals, and case.
        Clickable to expand/collapse.

        Args:
            painter: The QPainter to use for drawing.
        """
        doc_header_height = self._get_doc_header_height()
        doc_rect = QRectF(
            0,
            self.TITLE_HEIGHT,
            self._width,
            doc_header_height
        )

        # Draw background (lighter when hovered)
        bg_color = QColor(self.DOC_BG_COLOR_HOVER if self._doc_header_hovered else self.DOC_BG_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRect(doc_rect)

        # Draw expand/collapse indicator (triangle)
        indicator_size = 8
        indicator_x = self.DOC_HEADER_PADDING
        indicator_y = self.TITLE_HEIGHT + (self.DOC_HEADER_COLLAPSED_HEIGHT - indicator_size) / 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(self.DOC_TEXT_COLOR)))

        if self._doc_expanded:
            # Downward pointing triangle (expanded)
            triangle = QPolygonF([
                QPointF(indicator_x, indicator_y),
                QPointF(indicator_x + indicator_size, indicator_y),
                QPointF(indicator_x + indicator_size / 2, indicator_y + indicator_size),
            ])
        else:
            # Rightward pointing triangle (collapsed)
            triangle = QPolygonF([
                QPointF(indicator_x, indicator_y),
                QPointF(indicator_x + indicator_size, indicator_y + indicator_size / 2),
                QPointF(indicator_x, indicator_y + indicator_size),
            ])
        painter.drawPolygon(triangle)

        # Set up font for documentation text
        doc_font = QFont("Segoe UI", 8)
        painter.setFont(doc_font)
        painter.setPen(QPen(QColor(self.DOC_TEXT_COLOR)))

        if not self._doc_expanded:
            # Draw collapsed header text
            collapsed_text_rect = QRectF(
                indicator_x + indicator_size + 6,
                self.TITLE_HEIGHT,
                self._width - indicator_x - indicator_size - 12,
                self.DOC_HEADER_COLLAPSED_HEIGHT
            )
            painter.drawText(
                collapsed_text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                DOCUMENTATION_COLLAPSED_TEXT
            )
        else:
            # Draw expanded header
            header_text_rect = QRectF(
                indicator_x + indicator_size + 6,
                self.TITLE_HEIGHT,
                self._width - indicator_x - indicator_size - 12,
                self.DOC_HEADER_COLLAPSED_HEIGHT
            )
            painter.setPen(QPen(QColor(self.DOC_TEXT_COLOR)))
            painter.drawText(
                header_text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                DOCUMENTATION_EXPANDED_HEADER
            )

            # Draw usage examples
            example_font = QFont("Consolas", 8)
            example_font.setStyleHint(QFont.StyleHint.Monospace)

            y_offset = self.TITLE_HEIGHT + self.DOC_HEADER_COLLAPSED_HEIGHT + 2
            line_height = 16

            for keyword, example, description in DOCUMENTATION_EXAMPLES:
                # Draw keyword in highlight color
                painter.setFont(example_font)
                painter.setPen(QPen(QColor(self.DOC_HIGHLIGHT_COLOR)))

                keyword_rect = QRectF(
                    self.DOC_HEADER_PADDING + 4,
                    y_offset,
                    self._width - self.DOC_HEADER_PADDING * 2 - 8,
                    line_height
                )
                painter.drawText(
                    keyword_rect,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    example
                )

                # Draw description to the right in dimmer color
                painter.setFont(doc_font)
                painter.setPen(QPen(QColor(self.DOC_DESCRIPTION_COLOR)))

                # Calculate position after example text
                fm = QFontMetrics(example_font)
                example_width = fm.horizontalAdvance(example)
                desc_rect = QRectF(
                    self.DOC_HEADER_PADDING + 4 + example_width + 8,
                    y_offset,
                    self._width - self.DOC_HEADER_PADDING * 2 - example_width - 20,
                    line_height
                )
                painter.drawText(
                    desc_rect,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    f"# {description}"
                )

                y_offset += line_height

    def _draw_code_section(self, painter: QPainter, y_start: float) -> None:
        """
        Draw the code display section background.

        The code text itself is rendered by the QGraphicsTextItem child widget,
        which provides better text rendering and will support syntax highlighting.
        This method only draws the background for the code section.

        Args:
            painter: The QPainter to use for drawing.
            y_start: The y-coordinate where the code section starts.
        """
        # Code section background
        code_rect = QRectF(
            0,
            y_start,
            self._width,
            self.CODE_SECTION_HEIGHT
        )
        code_bg_color = QColor(self.CODE_BG_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(code_bg_color))
        painter.drawRect(code_rect)

        # Note: The code text is rendered by self._code_text_item (QGraphicsTextItem)
        # which is positioned and updated in _position_code_text_item() and
        # _update_code_text_item(). This provides:
        # - Better text rendering and layout
        # - Support for rich text formatting (for syntax highlighting in T005)
        # - Proper clipping within the code section bounds

    def _draw_validation_warning(
        self,
        painter: QPainter,
        indicator_x: float,
        indicator_y: float
    ) -> None:
        """
        Draw the validation warning indicator.

        Args:
            painter: The QPainter to use for drawing.
            indicator_x: X position of the execution state indicator.
            indicator_y: Y position of the execution state indicator.
        """
        # Draw a warning triangle/badge near the execution indicator
        warning_x = indicator_x - 16
        warning_y = indicator_y - 5
        warning_size = 10

        # Draw orange warning background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(VALIDATION_STATE_COLORS["invalid"])))

        # Draw a small warning triangle
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

    def sync_from_model(self) -> None:
        """
        Synchronize the widget state from the node model.

        This method updates the visual representation of the CodeNodeWidget
        to reflect the current state of the underlying CodeNode model. It
        should be called whenever the model's properties change, including:

        - code: Updates the code preview text and re-applies syntax highlighting
        - is_code_valid: Updates the validation warning indicator
        - execution_state: Updates the execution state indicator
        - position: Updates the widget's position on the canvas
        - custom_color: Updates the title bar color scheme

        The method performs the following updates:
        1. Calls parent sync_from_model() which handles common properties
           (position, execution state, port connections, validation state,
           inline widget values, colors)
        2. Updates the code text item content with current code from model
        3. Updates validation error state for the warning indicator
        4. Forces a complete redraw of the widget

        Note:
            This method is typically called by the scene or application
            after a property change command is executed, ensuring the
            visual representation stays in sync with the model.
        """
        # Call parent to handle common properties:
        # - Position (setPos)
        # - Execution state indicator
        # - Port connection states
        # - Validation state (sets _has_validation_errors)
        # - Inline widget values
        # - Colors (title bar gradient)
        super().sync_from_model()

        # Update the code text item content from the model's code property
        # This refreshes the displayed code preview and triggers the
        # syntax highlighter to re-apply highlighting
        self._update_code_text_item()

        # Update validation error state specifically for CodeNode
        # The parent's update_validation_state() already checks is_code_valid
        # but we ensure it's called to update _has_validation_errors
        if hasattr(self._code_node, 'is_code_valid'):
            self._has_validation_errors = not self._code_node.is_code_valid

        # Force redraw to update all visual elements:
        # - Code preview section with new code
        # - Validation warning indicator
        # - Any other visual state changes
        self.update()

    def update_code_display(self) -> None:
        """
        Update the code display section.

        This is a lightweight method that only updates the code preview
        text and validation indicator. Use this method for quick updates
        when you know only the code content has changed (e.g., during
        real-time editing in the properties panel).

        For full model synchronization (including position, port states,
        colors, etc.), use sync_from_model() instead.

        The method performs:
        1. Updates the code text item content from the model
        2. Re-applies syntax highlighting via the attached highlighter
        3. Updates the validation error indicator
        4. Triggers a repaint of the widget

        Example:
            # After changing code in the properties panel
            node.code = new_code_string
            widget.update_code_display()
        """
        # Update the code text content and syntax highlighting
        self._update_code_text_item()

        # Update validation error state if available
        if hasattr(self._code_node, 'is_code_valid'):
            self._has_validation_errors = not self._code_node.is_code_valid

        # Trigger repaint
        self.update()

    def _get_doc_header_rect(self) -> QRectF:
        """Get the bounding rectangle of the documentation header area."""
        return QRectF(
            0,
            self.TITLE_HEIGHT,
            self._width,
            self._get_doc_header_height()
        )

    def _is_point_in_doc_header(self, pos: QPointF) -> bool:
        """Check if a point is within the documentation header area."""
        doc_rect = self._get_doc_header_rect()
        return doc_rect.contains(pos)

    def toggle_documentation(self) -> None:
        """Toggle the expanded/collapsed state of the documentation header."""
        self._doc_expanded = not self._doc_expanded
        # Recalculate size and reposition ports (also repositions code text item)
        self.prepareGeometryChange()
        self._calculate_size()
        self.update()

    @property
    def code_text_item(self) -> QGraphicsTextItem:
        """
        Get the QGraphicsTextItem used for code preview.

        This property provides access to the text item for advanced
        customization.

        Returns:
            The QGraphicsTextItem displaying the code preview.
        """
        return self._code_text_item

    @property
    def syntax_highlighter(self) -> CodePreviewHighlighter:
        """
        Get the syntax highlighter used for the code preview.

        This property provides access to the CodePreviewHighlighter instance
        that applies Python syntax highlighting to the code preview.

        Returns:
            The CodePreviewHighlighter instance.
        """
        return self._syntax_highlighter

    @property
    def is_documentation_expanded(self) -> bool:
        """Check if the documentation header is currently expanded."""
        return self._doc_expanded

    @is_documentation_expanded.setter
    def is_documentation_expanded(self, expanded: bool) -> None:
        """Set the documentation header expanded state."""
        if self._doc_expanded != expanded:
            self._doc_expanded = expanded
            self.prepareGeometryChange()
            self._calculate_size()
            self.update()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Handle mouse press events.

        Toggles the documentation header if clicked in that area.

        Args:
            event: The mouse event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_point_in_doc_header(event.pos()):
                self.toggle_documentation()
                event.accept()
                return
        # Call parent for default handling (selection, dragging, etc.)
        super().mousePressEvent(event)

    def hoverMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Handle hover move events for documentation header hover effects.

        Args:
            event: The hover event.
        """
        was_hovered = self._doc_header_hovered
        self._doc_header_hovered = self._is_point_in_doc_header(event.pos())

        # Update cursor to indicate clickability
        if self._doc_header_hovered:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        # Redraw if hover state changed
        if was_hovered != self._doc_header_hovered:
            self.update()

        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """
        Handle hover leave events.

        Args:
            event: The hover event.
        """
        if self._doc_header_hovered:
            self._doc_header_hovered = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

        super().hoverLeaveEvent(event)
