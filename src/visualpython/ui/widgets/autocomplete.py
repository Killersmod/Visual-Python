"""
Autocomplete functionality for the Python code editor.

This module provides autocomplete suggestions for Python keywords, built-in
functions, and variables extracted from the current code context.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Set, TYPE_CHECKING

from PyQt6.QtCore import Qt, QStringListModel, QRect, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QTextCursor, QKeyEvent
from PyQt6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QWidget,
    QVBoxLayout,
    QFrame,
    QAbstractItemView,
)

from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class CompletionType(Enum):
    """Type of completion item for styling/categorization."""
    KEYWORD = auto()
    BUILTIN = auto()
    VARIABLE = auto()
    FUNCTION = auto()
    IMPORT = auto()


@dataclass
class CompletionItem:
    """Represents a single autocomplete suggestion."""
    text: str
    completion_type: CompletionType
    description: str = ""

    def __hash__(self) -> int:
        return hash((self.text, self.completion_type))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CompletionItem):
            return False
        return self.text == other.text and self.completion_type == other.completion_type


class PythonCompletionProvider:
    """
    Provides Python code completions from various sources.

    Sources include:
    - Python keywords
    - Built-in functions
    - Variables defined in the current code
    - Common import modules
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

    # Common import modules
    COMMON_IMPORTS = [
        "os", "sys", "re", "json", "math", "random", "datetime", "time",
        "collections", "itertools", "functools", "pathlib", "typing",
        "dataclasses", "enum", "abc", "copy", "io", "pickle", "csv",
    ]

    def __init__(self) -> None:
        """Initialize the completion provider."""
        self._keyword_items = [
            CompletionItem(kw, CompletionType.KEYWORD, "Python keyword")
            for kw in self.KEYWORDS
        ]
        self._builtin_items = [
            CompletionItem(fn, CompletionType.BUILTIN, "Built-in function")
            for fn in self.BUILTINS
        ]
        self._import_items = [
            CompletionItem(mod, CompletionType.IMPORT, "Python module")
            for mod in self.COMMON_IMPORTS
        ]

    def get_completions(
        self,
        code: str,
        prefix: str,
        line: int,
        column: int,
    ) -> List[CompletionItem]:
        """
        Get completion suggestions for the given context.

        Args:
            code: The full code content.
            prefix: The current prefix being typed.
            line: Current cursor line (1-based).
            column: Current cursor column (1-based).

        Returns:
            List of matching completion items, sorted by relevance.
        """
        if not prefix:
            return []

        prefix_lower = prefix.lower()
        completions: List[CompletionItem] = []
        seen_texts: Set[str] = set()

        # Check if we're in an import context
        current_line = self._get_line_at(code, line)
        in_import = self._is_import_context(current_line, column)

        if in_import:
            # Only suggest modules in import context
            for item in self._import_items:
                if item.text.lower().startswith(prefix_lower) and item.text not in seen_texts:
                    completions.append(item)
                    seen_texts.add(item.text)
        else:
            # Extract variables from current code
            variables = self._extract_variables(code)
            variable_items = [
                CompletionItem(var, CompletionType.VARIABLE, "Variable")
                for var in variables
            ]

            # Collect all matching items
            all_items = (
                variable_items +  # Variables first (most relevant)
                self._builtin_items +
                self._keyword_items
            )

            for item in all_items:
                if item.text.lower().startswith(prefix_lower) and item.text not in seen_texts:
                    completions.append(item)
                    seen_texts.add(item.text)

        # Sort: exact prefix match first, then by length, then alphabetically
        completions.sort(key=lambda x: (
            not x.text.startswith(prefix),  # Exact case match first
            len(x.text),  # Shorter names first
            x.text.lower(),  # Then alphabetically
        ))

        return completions[:20]  # Limit to 20 suggestions

    def _get_line_at(self, code: str, line: int) -> str:
        """Get the line of code at the specified line number (1-based)."""
        lines = code.split('\n')
        if 1 <= line <= len(lines):
            return lines[line - 1]
        return ""

    def _is_import_context(self, line: str, column: int) -> bool:
        """Check if the cursor is in an import statement context."""
        # Check for 'import ' or 'from ' at the start of the line
        stripped = line.lstrip()
        return (
            stripped.startswith('import ') or
            stripped.startswith('from ') and ' import ' not in stripped[:column]
        )

    def _extract_variables(self, code: str) -> Set[str]:
        """
        Extract variable names defined in the code using AST parsing.

        Args:
            code: The Python code to analyze.

        Returns:
            Set of variable names found in the code.
        """
        variables: Set[str] = set()

        try:
            tree = ast.parse(code)
        except SyntaxError:
            # If code has syntax errors, fall back to regex-based extraction
            logger.debug("AST parse failed, falling back to regex", exc_info=True)
            return self._extract_variables_regex(code)

        for node in ast.walk(tree):
            # Assignment targets
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self._collect_names(target, variables)
            # Annotated assignments
            elif isinstance(node, ast.AnnAssign) and node.target:
                self._collect_names(node.target, variables)
            # For loop targets
            elif isinstance(node, ast.For):
                self._collect_names(node.target, variables)
            # Function definitions
            elif isinstance(node, ast.FunctionDef):
                variables.add(node.name)
                # Add function parameters
                for arg in node.args.args:
                    variables.add(arg.arg)
                for arg in node.args.kwonlyargs:
                    variables.add(arg.arg)
                if node.args.vararg:
                    variables.add(node.args.vararg.arg)
                if node.args.kwarg:
                    variables.add(node.args.kwarg.arg)
            # Class definitions
            elif isinstance(node, ast.ClassDef):
                variables.add(node.name)
            # With statement targets
            elif isinstance(node, ast.With):
                for item in node.items:
                    if item.optional_vars:
                        self._collect_names(item.optional_vars, variables)
            # Exception handler names
            elif isinstance(node, ast.ExceptHandler) and node.name:
                variables.add(node.name)
            # Comprehension targets
            elif isinstance(node, ast.comprehension):
                self._collect_names(node.target, variables)

        return variables

    def _collect_names(self, node: ast.AST, variables: Set[str]) -> None:
        """Recursively collect variable names from an AST node."""
        if isinstance(node, ast.Name):
            variables.add(node.id)
        elif isinstance(node, ast.Tuple) or isinstance(node, ast.List):
            for elt in node.elts:
                self._collect_names(elt, variables)
        elif isinstance(node, ast.Starred):
            self._collect_names(node.value, variables)

    def _extract_variables_regex(self, code: str) -> Set[str]:
        """
        Fallback regex-based variable extraction for code with syntax errors.

        Args:
            code: The Python code to analyze.

        Returns:
            Set of likely variable names found in the code.
        """
        variables: Set[str] = set()

        # Match simple assignments: var = ...
        assignment_pattern = r'^[ \t]*([a-zA-Z_][a-zA-Z0-9_]*)\s*='
        for match in re.finditer(assignment_pattern, code, re.MULTILINE):
            name = match.group(1)
            if name not in self.KEYWORDS:
                variables.add(name)

        # Match for loop targets: for var in ...
        for_pattern = r'\bfor\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+in\b'
        for match in re.finditer(for_pattern, code):
            variables.add(match.group(1))

        # Match function definitions: def func_name(...)
        def_pattern = r'\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        for match in re.finditer(def_pattern, code):
            variables.add(match.group(1))

        # Match class definitions: class ClassName...
        class_pattern = r'\bclass\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        for match in re.finditer(class_pattern, code):
            variables.add(match.group(1))

        return variables


class AutocompletePopup(QFrame):
    """
    Popup widget displaying autocomplete suggestions.

    Shows a filterable list of completions near the cursor position.

    Signals:
        completion_selected: Emitted when a completion is selected.
    """

    completion_selected = pyqtSignal(str)  # The selected completion text

    # Visual settings
    MAX_VISIBLE_ITEMS = 8
    ITEM_HEIGHT = 22
    MIN_WIDTH = 200
    MAX_WIDTH = 400

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the autocomplete popup.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        # Set frame style
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self.setLineWidth(1)

        # Configure window flags for popup behavior
        # Use Tool window instead of Popup to avoid grabbing input events
        # This allows typing to continue while the autocomplete is visible
        self.setWindowFlags(
            Qt.WindowType.Tool |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        # Prevent the popup from taking focus from the editor
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Make sure the widget doesn't accept focus
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Style the popup
        self.setStyleSheet("""
            AutocompletePopup {
                background-color: #FFFFFF;
                border: 1px solid #CCCCCC;
            }
            QListWidget {
                background-color: #FFFFFF;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 2px 8px;
                border: none;
            }
            QListWidget::item:selected {
                background-color: #0078D4;
                color: white;
            }
            QListWidget::item:hover:!selected {
                background-color: #E5F3FF;
            }
        """)

        # Setup layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create the list widget
        self._list_widget = QListWidget()
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Set font
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._list_widget.setFont(font)

        # Connect signals
        self._list_widget.itemActivated.connect(self._on_item_activated)
        self._list_widget.itemClicked.connect(self._on_item_activated)

        layout.addWidget(self._list_widget)

        # Store current items
        self._items: List[CompletionItem] = []

    def set_completions(self, items: List[CompletionItem]) -> None:
        """
        Set the completion items to display.

        Args:
            items: List of completion items.
        """
        self._items = items
        self._list_widget.clear()

        if not items:
            self.hide()
            return

        for item in items:
            list_item = QListWidgetItem(self._format_item(item))
            list_item.setData(Qt.ItemDataRole.UserRole, item.text)

            # Set different colors based on completion type
            if item.completion_type == CompletionType.KEYWORD:
                list_item.setForeground(Qt.GlobalColor.blue)
            elif item.completion_type == CompletionType.BUILTIN:
                list_item.setForeground(Qt.GlobalColor.darkCyan)
            elif item.completion_type == CompletionType.IMPORT:
                list_item.setForeground(Qt.GlobalColor.darkGreen)

            self._list_widget.addItem(list_item)

        # Select first item
        if self._list_widget.count() > 0:
            self._list_widget.setCurrentRow(0)

        # Update size
        self._update_size()

    def _format_item(self, item: CompletionItem) -> str:
        """Format a completion item for display."""
        type_indicator = {
            CompletionType.KEYWORD: "kw",
            CompletionType.BUILTIN: "fn",
            CompletionType.VARIABLE: "var",
            CompletionType.FUNCTION: "fn",
            CompletionType.IMPORT: "mod",
        }.get(item.completion_type, "")

        return f"{item.text}  [{type_indicator}]"

    def _update_size(self) -> None:
        """Update the popup size based on content."""
        count = min(self._list_widget.count(), self.MAX_VISIBLE_ITEMS)

        if count == 0:
            return

        # Calculate width based on longest item
        max_width = self.MIN_WIDTH
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item:
                width = self._list_widget.fontMetrics().horizontalAdvance(item.text()) + 30
                max_width = max(max_width, width)

        max_width = min(max_width, self.MAX_WIDTH)
        height = count * self.ITEM_HEIGHT + 4  # Add padding

        self.setFixedSize(max_width, height)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        """Handle item activation (double-click or Enter)."""
        if item:
            text = item.data(Qt.ItemDataRole.UserRole)
            self.completion_selected.emit(text)
            self.hide()

    def select_next(self) -> None:
        """Select the next item in the list."""
        current = self._list_widget.currentRow()
        if current < self._list_widget.count() - 1:
            self._list_widget.setCurrentRow(current + 1)

    def select_previous(self) -> None:
        """Select the previous item in the list."""
        current = self._list_widget.currentRow()
        if current > 0:
            self._list_widget.setCurrentRow(current - 1)

    def get_selected_completion(self) -> Optional[str]:
        """Get the currently selected completion text."""
        item = self._list_widget.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def has_selection(self) -> bool:
        """Check if there is a selected item."""
        return self._list_widget.currentItem() is not None

    @property
    def is_visible(self) -> bool:
        """Check if the popup is currently visible."""
        return self.isVisible()
