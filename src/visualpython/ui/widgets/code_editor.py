"""
Syntax-highlighted Python code editor widget for Code nodes.

This module provides a code editor widget with Python syntax highlighting,
line numbers, real-time syntax validation, and other features for a proper
development experience when writing Python code within nodes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, QRect, QSize, pyqtSignal, QTimer, QPoint
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QFocusEvent,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
    QTextCursor,
    QPen,
    QTextBlockUserData,
)
from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit, QToolTip

from visualpython.ui.widgets.autocomplete import (
    AutocompletePopup,
    PythonCompletionProvider,
)

if TYPE_CHECKING:
    from PyQt6.QtGui import QResizeEvent, QPaintEvent, QKeyEvent


@dataclass
class SyntaxError:
    """Represents a syntax error found during validation."""
    line: int  # 1-based line number
    column: Optional[int]  # 1-based column number
    message: str
    end_line: Optional[int] = None
    end_column: Optional[int] = None


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """
    Syntax highlighter for Python code.

    Provides syntax highlighting for Python keywords, strings, comments,
    numbers, function definitions, class definitions, and built-in functions.

    Attributes:
        highlighting_rules: List of (pattern, format) tuples for highlighting.
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
        Initialize the Python syntax highlighter.

        Args:
            document: The QTextDocument to apply highlighting to.
        """
        super().__init__(document)
        self._highlighting_rules: List[tuple[re.Pattern, QTextCharFormat]] = []
        self._setup_formats()
        self._setup_rules()

    def _setup_formats(self) -> None:
        """Set up the text formats for different syntax elements."""
        # Keyword format (blue, bold)
        self._keyword_format = QTextCharFormat()
        self._keyword_format.setForeground(QColor("#0000FF"))
        self._keyword_format.setFontWeight(QFont.Weight.Bold)

        # Built-in function format (dark cyan)
        self._builtin_format = QTextCharFormat()
        self._builtin_format.setForeground(QColor("#008080"))

        # String format (dark green)
        self._string_format = QTextCharFormat()
        self._string_format.setForeground(QColor("#008000"))

        # Comment format (gray, italic)
        self._comment_format = QTextCharFormat()
        self._comment_format.setForeground(QColor("#808080"))
        self._comment_format.setFontItalic(True)

        # Number format (dark red)
        self._number_format = QTextCharFormat()
        self._number_format.setForeground(QColor("#800000"))

        # Function/class definition format (dark magenta, bold)
        self._definition_format = QTextCharFormat()
        self._definition_format.setForeground(QColor("#800080"))
        self._definition_format.setFontWeight(QFont.Weight.Bold)

        # Decorator format (dark yellow)
        self._decorator_format = QTextCharFormat()
        self._decorator_format.setForeground(QColor("#AA5500"))

        # Self/cls format (dark blue, italic)
        self._self_format = QTextCharFormat()
        self._self_format.setForeground(QColor("#000080"))
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


class ErrorBlockData(QTextBlockUserData):
    """User data attached to text blocks to store error information."""

    def __init__(self, error: Optional[SyntaxError] = None) -> None:
        super().__init__()
        self.error = error


class LineNumberArea(QWidget):
    """
    Widget for displaying line numbers and error indicators in the code editor.

    This is a helper widget that paints line numbers alongside
    the code editor content, and shows error markers for lines with errors.
    """

    def __init__(self, editor: "CodeEditorWidget") -> None:
        """
        Initialize the line number area.

        Args:
            editor: The code editor widget this area belongs to.
        """
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        """Return the preferred size for the line number area."""
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event: "QPaintEvent") -> None:
        """Paint the line numbers."""
        self._editor.paint_line_numbers(event)

    def mouseMoveEvent(self, event) -> None:
        """Show error tooltip on hover."""
        self._editor.show_error_tooltip_at_position(event.pos())


class CodeEditorWidget(QPlainTextEdit):
    """
    A syntax-highlighted Python code editor widget with real-time validation.

    Provides a proper development experience for writing Python code
    with features including:
    - Python syntax highlighting
    - Line numbers
    - Current line highlighting
    - Tab handling (converts tabs to spaces)
    - Auto-indentation
    - Real-time syntax error detection
    - Inline error indicators and tooltips
    - Autocomplete suggestions for Python keywords, builtins, and variables

    Signals:
        code_changed: Emitted when the code content changes.
        validation_changed: Emitted when validation state changes.

    Attributes:
        DEFAULT_FONT_FAMILY: Default monospace font family.
        DEFAULT_FONT_SIZE: Default font size in points.
        TAB_SPACES: Number of spaces per tab.
        VALIDATION_DELAY_MS: Delay before validation triggers (debounce).
        AUTOCOMPLETE_DELAY_MS: Delay before autocomplete triggers.
        AUTOCOMPLETE_MIN_CHARS: Minimum characters before autocomplete shows.
    """

    DEFAULT_FONT_FAMILY = "Consolas"
    DEFAULT_FONT_SIZE = 10
    TAB_SPACES = 4
    VALIDATION_DELAY_MS = 300  # Debounce delay for validation
    AUTOCOMPLETE_DELAY_MS = 150  # Debounce delay for autocomplete
    AUTOCOMPLETE_MIN_CHARS = 2  # Minimum characters to trigger autocomplete

    code_changed = pyqtSignal(str)
    """Signal emitted when the code content changes."""

    validation_changed = pyqtSignal(bool, list)
    """Signal emitted when validation state changes (is_valid, errors)."""

    def __init__(self, parent: Optional[QWidget] = None, enable_validation: bool = True) -> None:
        """
        Initialize the code editor widget.

        Args:
            parent: Optional parent widget.
            enable_validation: Whether to enable real-time syntax validation.
        """
        super().__init__(parent)

        # Validation state
        self._enable_validation = enable_validation
        self._syntax_errors: List[SyntaxError] = []
        self._is_valid = True
        self._error_lines: set = set()

        # Autocomplete state
        self._enable_autocomplete = True
        self._completion_provider = PythonCompletionProvider()
        self._autocomplete_popup: Optional[AutocompletePopup] = None
        self._completion_prefix = ""
        self._completion_prefix_start = 0

        # Set up font
        font = QFont(self.DEFAULT_FONT_FAMILY, self.DEFAULT_FONT_SIZE)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

        # Set tab stop width
        font_metrics = QFontMetrics(font)
        self.setTabStopDistance(font_metrics.horizontalAdvance(" ") * self.TAB_SPACES)

        # Create line number area
        self._line_number_area = LineNumberArea(self)
        self._line_number_area.setMouseTracking(True)

        # Create syntax highlighter
        self._highlighter = PythonSyntaxHighlighter(self.document())

        # Validation debounce timer
        self._validation_timer = QTimer(self)
        self._validation_timer.setSingleShot(True)
        self._validation_timer.timeout.connect(self._perform_validation)

        # Autocomplete debounce timer
        self._autocomplete_timer = QTimer(self)
        self._autocomplete_timer.setSingleShot(True)
        self._autocomplete_timer.timeout.connect(self._show_autocomplete)

        # Connect signals
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.textChanged.connect(self._on_text_changed)

        # Initial setup
        self._update_line_number_area_width(0)
        self._highlight_current_line()

        # Enable mouse tracking for tooltips
        self.setMouseTracking(True)

        # Set placeholder text
        self.setPlaceholderText("# Enter Python code here...")

    @property
    def code(self) -> str:
        """Get the current code content."""
        return self.toPlainText()

    @code.setter
    def code(self, value: str) -> None:
        """
        Set the code content.

        Args:
            value: The Python code to set.
        """
        self.setPlainText(value)

    def line_number_area_width(self) -> int:
        """
        Calculate the width needed for the line number area.

        Returns:
            Width in pixels for the line number area.
        """
        digits = 1
        max_block = max(1, self.blockCount())
        while max_block >= 10:
            max_block //= 10
            digits += 1

        # Add padding for error indicator (12px) + line numbers + padding
        error_indicator_space = 12 if self._enable_validation else 0
        space = error_indicator_space + 3 + self.fontMetrics().horizontalAdvance("9") * digits + 3
        return space

    def _update_line_number_area_width(self, _: int) -> None:
        """Update the viewport margins to accommodate line numbers."""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        """
        Update the line number area when scrolling or resizing.

        Args:
            rect: The rectangle that needs updating.
            dy: The vertical scroll amount.
        """
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )

        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event: "QResizeEvent") -> None:
        """Handle resize events to adjust line number area."""
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event: "QPaintEvent") -> None:
        """
        Paint the line numbers and error indicators in the line number area.

        Args:
            event: The paint event.
        """
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor("#F0F0F0"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        # Calculate error indicator position (left side of line number area)
        error_indicator_size = 8
        error_indicator_x = 2

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                line_number = block_number + 1
                number = str(line_number)

                # Check if this line has an error
                has_error = line_number in self._error_lines

                if has_error:
                    # Draw red error indicator circle
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor("#FF4444"))
                    error_y = top + (self.fontMetrics().height() - error_indicator_size) // 2
                    painter.drawEllipse(
                        error_indicator_x,
                        error_y,
                        error_indicator_size,
                        error_indicator_size
                    )
                    # Draw line number in red
                    painter.setPen(QColor("#CC0000"))
                else:
                    painter.setPen(QColor("#808080"))

                painter.drawText(
                    error_indicator_size + 4, top,
                    self._line_number_area.width() - error_indicator_size - 7,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, number
                )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

        painter.end()

    def _highlight_current_line(self) -> None:
        """Highlight the line containing the cursor."""
        # Use the combined highlighting that includes both current line and errors
        self._update_error_highlighting()

    def _on_text_changed(self) -> None:
        """Handle text changes and emit the code_changed signal."""
        self.code_changed.emit(self.toPlainText())

        # Trigger debounced validation
        if self._enable_validation:
            self._validation_timer.stop()
            self._validation_timer.start(self.VALIDATION_DELAY_MS)

        # Trigger debounced autocomplete
        if self._enable_autocomplete:
            self._autocomplete_timer.stop()
            self._autocomplete_timer.start(self.AUTOCOMPLETE_DELAY_MS)

    def _perform_validation(self) -> None:
        """Perform syntax validation on the current code."""
        from visualpython.compiler.ast_validator import validate_user_code

        code = self.toPlainText()

        # Clear previous errors
        old_is_valid = self._is_valid
        old_errors = self._syntax_errors.copy()

        self._syntax_errors.clear()
        self._error_lines.clear()

        # Skip validation if empty (allow empty code)
        if not code.strip():
            self._is_valid = True
            self._update_error_highlighting()
            if old_is_valid != self._is_valid or old_errors != self._syntax_errors:
                self.validation_changed.emit(self._is_valid, self._syntax_errors)
            return

        # Validate using AST validator
        result = validate_user_code(code)

        if result.valid:
            self._is_valid = True
        else:
            self._is_valid = False
            for error in result.errors:
                syntax_error = SyntaxError(
                    line=error.line or 1,
                    column=error.column,
                    message=error.message,
                    end_line=error.end_line,
                    end_column=error.end_column,
                )
                self._syntax_errors.append(syntax_error)
                if error.line:
                    self._error_lines.add(error.line)

        # Update visual highlighting
        self._update_error_highlighting()

        # Emit validation changed signal if state changed
        if old_is_valid != self._is_valid or old_errors != self._syntax_errors:
            self.validation_changed.emit(self._is_valid, self._syntax_errors)

    def _update_error_highlighting(self) -> None:
        """Update the error underline highlighting in the editor."""
        extra_selections: List[QTextEdit.ExtraSelection] = []

        # Add current line highlight
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#2A2A3A")  # Dark blue-gray for better visibility in dark theme
            selection.format.setBackground(line_color)
            selection.format.setProperty(
                QTextCharFormat.Property.FullWidthSelection, True
            )
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        # Add error underlines
        for error in self._syntax_errors:
            if error.line:
                selection = QTextEdit.ExtraSelection()

                # Red wavy underline effect
                error_format = QTextCharFormat()
                error_format.setUnderlineColor(QColor("#FF0000"))
                error_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
                # Light red background for error line
                error_format.setBackground(QColor(255, 200, 200, 50))

                selection.format = error_format

                # Move cursor to error line
                block = self.document().findBlockByLineNumber(error.line - 1)
                if block.isValid():
                    cursor = QTextCursor(block)

                    # Calculate start position
                    start_col = (error.column - 1) if error.column and error.column > 0 else 0
                    cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                    cursor.movePosition(
                        QTextCursor.MoveOperation.Right,
                        QTextCursor.MoveMode.MoveAnchor,
                        min(start_col, len(block.text()))
                    )

                    # Calculate end position - underline rest of line or to end_column
                    if error.end_column and error.end_line == error.line:
                        end_col = min(error.end_column, len(block.text()))
                        cursor.movePosition(
                            QTextCursor.MoveOperation.Right,
                            QTextCursor.MoveMode.KeepAnchor,
                            end_col - start_col
                        )
                    else:
                        # Underline to end of line
                        cursor.movePosition(
                            QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor
                        )

                    selection.cursor = cursor
                    extra_selections.append(selection)

        self.setExtraSelections(extra_selections)

        # Update line number area to show error markers
        self._line_number_area.update()

    def get_error_at_line(self, line: int) -> Optional[SyntaxError]:
        """Get the error at a specific line number (1-based)."""
        for error in self._syntax_errors:
            if error.line == line:
                return error
        return None

    def show_error_tooltip_at_position(self, pos) -> None:
        """Show error tooltip when hovering over error indicator in line number area."""
        # Calculate which line the mouse is over
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()

        while block.isValid():
            block_top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
            block_bottom = block_top + self.blockBoundingRect(block).height()

            if block_top <= pos.y() < block_bottom:
                line_number = block.blockNumber() + 1
                error = self.get_error_at_line(line_number)
                if error:
                    # Show tooltip with error message
                    global_pos = self._line_number_area.mapToGlobal(pos)
                    QToolTip.showText(global_pos, f"Syntax Error: {error.message}")
                else:
                    QToolTip.hideText()
                return

            block = block.next()

        QToolTip.hideText()

    @property
    def is_valid(self) -> bool:
        """Check if the current code has no syntax errors."""
        return self._is_valid

    @property
    def syntax_errors(self) -> List[SyntaxError]:
        """Get the list of current syntax errors."""
        return self._syntax_errors.copy()

    @property
    def enable_validation(self) -> bool:
        """Get whether validation is enabled."""
        return self._enable_validation

    @enable_validation.setter
    def enable_validation(self, value: bool) -> None:
        """Set whether validation is enabled."""
        self._enable_validation = value
        if value:
            # Trigger immediate validation
            self._perform_validation()
        else:
            # Clear errors
            self._syntax_errors.clear()
            self._error_lines.clear()
            self._is_valid = True
            self._update_error_highlighting()

    def validate_now(self) -> bool:
        """Force immediate validation and return result."""
        self._validation_timer.stop()
        self._perform_validation()
        return self._is_valid

    # ===== Autocomplete Methods =====

    def _get_autocomplete_popup(self) -> AutocompletePopup:
        """Get or create the autocomplete popup."""
        if self._autocomplete_popup is None:
            self._autocomplete_popup = AutocompletePopup()
            self._autocomplete_popup.completion_selected.connect(self._insert_completion)
        return self._autocomplete_popup

    def _show_autocomplete(self) -> None:
        """Show autocomplete suggestions based on current cursor position."""
        if not self._enable_autocomplete:
            return

        # Get current word/prefix
        prefix, prefix_start = self._get_current_prefix()

        if len(prefix) < self.AUTOCOMPLETE_MIN_CHARS:
            self._hide_autocomplete()
            return

        self._completion_prefix = prefix
        self._completion_prefix_start = prefix_start

        # Get cursor position for popup placement
        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        column = cursor.positionInBlock() + 1

        # Get completions
        completions = self._completion_provider.get_completions(
            self.toPlainText(),
            prefix,
            line,
            column,
        )

        if not completions:
            self._hide_autocomplete()
            return

        # Show popup
        popup = self._get_autocomplete_popup()
        popup.set_completions(completions)

        # Position the popup below the current cursor position
        cursor_rect = self.cursorRect()
        global_pos = self.mapToGlobal(cursor_rect.bottomLeft())

        # Adjust if popup would go off screen
        popup.move(global_pos)
        popup.show()

    def _hide_autocomplete(self) -> None:
        """Hide the autocomplete popup."""
        if self._autocomplete_popup and self._autocomplete_popup.isVisible():
            self._autocomplete_popup.hide()

    def _get_current_prefix(self) -> tuple[str, int]:
        """
        Get the current word prefix being typed.

        Returns:
            Tuple of (prefix string, start position in block).
        """
        cursor = self.textCursor()
        block_text = cursor.block().text()
        column = cursor.positionInBlock()

        # Find the start of the current identifier
        prefix_start = column
        while prefix_start > 0:
            char = block_text[prefix_start - 1]
            if not (char.isalnum() or char == '_'):
                break
            prefix_start -= 1

        prefix = block_text[prefix_start:column]
        return prefix, prefix_start

    def _insert_completion(self, completion: str) -> None:
        """
        Insert the selected completion text.

        Args:
            completion: The completion text to insert.
        """
        cursor = self.textCursor()

        # Select and replace the prefix
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.MoveAnchor,
            self._completion_prefix_start
        )
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.KeepAnchor,
            len(self._completion_prefix)
        )

        cursor.insertText(completion)
        self.setTextCursor(cursor)
        self._hide_autocomplete()

    def trigger_autocomplete(self) -> None:
        """Manually trigger autocomplete (e.g., via Ctrl+Space)."""
        self._autocomplete_timer.stop()
        self._show_autocomplete()

    @property
    def enable_autocomplete(self) -> bool:
        """Get whether autocomplete is enabled."""
        return self._enable_autocomplete

    @enable_autocomplete.setter
    def enable_autocomplete(self, value: bool) -> None:
        """Set whether autocomplete is enabled."""
        self._enable_autocomplete = value
        if not value:
            self._hide_autocomplete()

    def _is_autocomplete_visible(self) -> bool:
        """Check if the autocomplete popup is visible."""
        return self._autocomplete_popup is not None and self._autocomplete_popup.isVisible()

    def keyPressEvent(self, event: "QKeyEvent") -> None:
        """
        Handle key press events for auto-indentation, tab handling, and autocomplete.

        Args:
            event: The key event.
        """
        # Handle autocomplete navigation when popup is visible
        if self._is_autocomplete_visible():
            popup = self._get_autocomplete_popup()

            if event.key() == Qt.Key.Key_Escape:
                self._hide_autocomplete()
                return

            if event.key() == Qt.Key.Key_Down:
                popup.select_next()
                return

            if event.key() == Qt.Key.Key_Up:
                popup.select_previous()
                return

            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                completion = popup.get_selected_completion()
                if completion:
                    self._insert_completion(completion)
                    return

            # For all other keys (including typing), allow them to pass through
            # The autocomplete will update via the text changed event

        # Trigger autocomplete with Ctrl+Space
        if (event.key() == Qt.Key.Key_Space and
                event.modifiers() == Qt.KeyboardModifier.ControlModifier):
            self.trigger_autocomplete()
            return

        if event.key() == Qt.Key.Key_Tab:
            # Insert spaces instead of tab
            cursor = self.textCursor()
            cursor.insertText(" " * self.TAB_SPACES)
            return

        if event.key() == Qt.Key.Key_Backtab:
            # Remove one level of indentation
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
            cursor.movePosition(
                QTextCursor.MoveOperation.Right,
                QTextCursor.MoveMode.KeepAnchor,
                self.TAB_SPACES
            )
            selected = cursor.selectedText()
            if selected == " " * self.TAB_SPACES:
                cursor.removeSelectedText()
            return

        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # Auto-indent on new line
            cursor = self.textCursor()
            current_line = cursor.block().text()

            # Calculate current indentation
            indent = ""
            for char in current_line:
                if char in (" ", "\t"):
                    indent += char
                else:
                    break

            # Check if line ends with colon (increase indent)
            stripped = current_line.rstrip()
            if stripped.endswith(":"):
                indent += " " * self.TAB_SPACES

            # Insert newline with indentation
            super().keyPressEvent(event)
            cursor = self.textCursor()
            cursor.insertText(indent)
            return

        # Hide autocomplete on certain keys
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End):
            self._hide_autocomplete()

        super().keyPressEvent(event)

    def focusOutEvent(self, event: "QFocusEvent") -> None:
        """
        Handle focus out events.

        Args:
            event: The focus event.
        """
        # Hide autocomplete when editor loses focus
        self._hide_autocomplete()
        super().focusOutEvent(event)

    def set_font_size(self, size: int) -> None:
        """
        Set the font size.

        Args:
            size: Font size in points.
        """
        font = self.font()
        font.setPointSize(size)
        self.setFont(font)
        self.setTabStopDistance(
            self.fontMetrics().horizontalAdvance(" ") * self.TAB_SPACES
        )

    def set_tab_spaces(self, spaces: int) -> None:
        """
        Set the number of spaces per tab.

        Args:
            spaces: Number of spaces per tab.
        """
        self.TAB_SPACES = spaces
        self.setTabStopDistance(
            self.fontMetrics().horizontalAdvance(" ") * self.TAB_SPACES
        )
