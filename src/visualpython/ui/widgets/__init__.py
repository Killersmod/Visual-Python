"""Custom Qt widgets for the VisualPython interface."""

from visualpython.ui.widgets.code_editor import (
    CodeEditorWidget,
    PythonSyntaxHighlighter,
    LineNumberArea,
)
from visualpython.ui.widgets.execution_state_indicator import (
    ExecutionStateIndicator,
    StateIndicatorCircle,
)
from visualpython.ui.widgets.autocomplete import (
    AutocompletePopup,
    PythonCompletionProvider,
    CompletionItem,
    CompletionType,
)
from visualpython.ui.widgets.minimap import MinimapWidget
from visualpython.ui.widgets.unsaved_changes_banner import UnsavedChangesBanner

__all__ = [
    "CodeEditorWidget",
    "PythonSyntaxHighlighter",
    "LineNumberArea",
    "ExecutionStateIndicator",
    "StateIndicatorCircle",
    "AutocompletePopup",
    "PythonCompletionProvider",
    "CompletionItem",
    "CompletionType",
    "MinimapWidget",
    "UnsavedChangesBanner",
]
