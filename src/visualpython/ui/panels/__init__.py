"""
UI panels for VisualPython.

This package contains side panel widgets for the main application,
including the node palette for discovering and adding nodes,
the output console for displaying script output, the node
properties panel for editing selected node properties, the
template browser for using pre-built graph templates, and the
execution summary panel for displaying execution statistics.
"""

from visualpython.ui.panels.node_palette import NodePaletteWidget
from visualpython.ui.panels.output_console import OutputConsoleWidget
from visualpython.ui.panels.node_properties_panel import NodePropertiesPanel
from visualpython.ui.panels.template_browser import TemplateBrowserWidget
from visualpython.ui.panels.execution_summary_panel import ExecutionSummaryPanel

__all__ = [
    "NodePaletteWidget",
    "OutputConsoleWidget",
    "NodePropertiesPanel",
    "TemplateBrowserWidget",
    "ExecutionSummaryPanel",
]
