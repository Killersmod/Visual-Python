"""UI module containing Qt-based user interface components."""

from visualpython.ui.main_window import MainWindow
from visualpython.ui.widgets import (
    CodeEditorWidget,
    PythonSyntaxHighlighter,
    LineNumberArea,
)

__all__ = [
    "MainWindow",
    "CodeEditorWidget",
    "PythonSyntaxHighlighter",
    "LineNumberArea",
]
