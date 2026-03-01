"""
Execution summary panel for displaying node execution statistics.

This module provides a panel widget that displays execution statistics
including success/failure counts, percentages, and overall execution health
after running a visual Python workflow.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize
from PyQt6.QtGui import QColor, QFont, QCursor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QProgressBar,
    QSizePolicy,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
)

if TYPE_CHECKING:
    from visualpython.execution.context import (
        ExecutionContext,
        ExecutionResult,
        NodeExecutionSummary,
    )
    from visualpython.execution.error_report import ErrorReport


class ExecutionPanelState(Enum):
    """
    Represents the current display state of the execution summary panel.

    This enum tracks the panel's state to properly manage UI transitions
    and status messages during the execution lifecycle.
    """

    IDLE = auto()
    """No execution in progress, showing previous results or empty state."""

    RUNNING = auto()
    """Execution is currently in progress."""

    COMPLETED_SUCCESS = auto()
    """Execution completed successfully with no errors."""

    COMPLETED_WITH_ERRORS = auto()
    """Execution completed but some nodes had errors."""

    CANCELLED = auto()
    """Execution was cancelled by the user."""

    NO_NODES = auto()
    """No executable nodes were found in the workflow."""


# Maximum number of errors to display in the list
MAX_DISPLAYED_ERRORS = 100


class ErrorListItem(QListWidgetItem):
    """
    Custom list item for displaying an error entry in the error list.

    Each item stores the node_id and error_index for navigation purposes.
    The item displays the node name, error type, and a truncated error message.

    Attributes:
        node_id: The ID of the node that produced this error.
        error_index: The index of the error within the node's error list.
        node_name: The display name of the node.
        error_message: The full error message.
    """

    def __init__(
        self,
        node_id: str,
        node_name: str,
        error_index: int,
        error_type: str,
        error_message: str,
        parent: Optional[QListWidget] = None,
    ) -> None:
        """
        Initialize the error list item.

        Args:
            node_id: The ID of the node.
            node_name: The display name of the node.
            error_index: The index of this error (0-based).
            error_type: The type/category of the error.
            error_message: The error message.
            parent: Optional parent list widget.
        """
        super().__init__(parent)
        self.node_id = node_id
        self.node_name = node_name
        self.error_index = error_index
        self.error_type = error_type
        self.error_message = error_message

        # Truncate long messages for display
        display_message = error_message
        if len(display_message) > 80:
            display_message = display_message[:77] + "..."

        # Format: "NodeName: ErrorMessage"
        self.setText(f"{node_name}: {display_message}")

        # Set tooltip with full details
        tooltip = (
            f"Node: {node_name}\n"
            f"Type: {error_type}\n"
            f"Error: {error_message}\n\n"
            "Click to navigate to this node"
        )
        self.setToolTip(tooltip)

        # Set icon/decoration for error indicator
        self.setForeground(QColor("#F44747"))



class StatisticWidget(QFrame):
    """
    A compact widget displaying a single statistic with label and value.

    Used to show counts like "Successful: 5" or "Failed: 2" in the
    execution summary panel.
    """

    def __init__(
        self,
        label: str,
        value: int = 0,
        color: QColor = QColor("#D4D4D4"),
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the statistic widget.

        Args:
            label: The label for this statistic (e.g., "Successful").
            value: The initial numeric value.
            color: The color for the value display.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._label = label
        self._value = value
        self._color = color
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget's UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Label
        self._label_widget = QLabel(f"{self._label}:")
        self._label_widget.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._label_widget)

        # Value
        self._value_widget = QLabel(str(self._value))
        self._value_widget.setStyleSheet(
            f"color: {self._color.name()}; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(self._value_widget)

        # Styling
        self.setStyleSheet("""
            StatisticWidget {
                background-color: #2D2D2D;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
            }
        """)

    def set_value(self, value: int) -> None:
        """
        Update the statistic value.

        Args:
            value: The new numeric value.
        """
        self._value = value
        self._value_widget.setText(str(value))

    def set_color(self, color: QColor) -> None:
        """
        Update the value color.

        Args:
            color: The new color for the value.
        """
        self._color = color
        self._value_widget.setStyleSheet(
            f"color: {color.name()}; font-size: 12px; font-weight: bold;"
        )

    @property
    def value(self) -> int:
        """Get the current value."""
        return self._value



class ExecutionSummaryPanel(QWidget):
    """
    Panel widget for displaying execution statistics and results.

    The ExecutionSummaryPanel provides an overview of workflow execution,
    showing:
    - Total nodes executed
    - Successful/failed/skipped node counts
    - Success rate percentage with visual progress bar
    - Total error count
    - Execution time
    - Clickable error list for navigation to failed nodes

    This panel is designed to be used alongside the Output Console as a
    tabbed bottom panel, providing a quick glance at execution health.

    Signals:
        cleared: Emitted when the panel is cleared/reset.
        error_clicked: Emitted when clicking on an error entry.
                       Parameters: (node_id: str, error_index: int)
        node_navigate_requested: Emitted to request navigation to a node.
                                 Parameters: (node_id: str)
    """

    cleared = pyqtSignal()
    error_clicked = pyqtSignal(str, int)  # node_id, error_index
    node_navigate_requested = pyqtSignal(str)  # node_id
    reset_requested = pyqtSignal()  # Request to reset graph node error indicators
    state_changed = pyqtSignal(ExecutionPanelState)  # Emitted when panel state changes

    # Color scheme matching existing panels
    COLOR_SUCCESS = QColor("#4EC9B0")  # Teal for success
    COLOR_FAILURE = QColor("#F44747")  # Red for errors
    COLOR_SKIPPED = QColor("#DCDCAA")  # Yellow for skipped
    COLOR_INFO = QColor("#569CD6")     # Blue for info
    COLOR_TEXT = QColor("#D4D4D4")     # Light gray for text
    COLOR_MUTED = QColor("#808080")    # Gray for muted text

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the execution summary panel.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._node_summaries: Dict[str, NodeExecutionSummary] = {}
        self._total_nodes = 0
        self._successful_count = 0
        self._failed_count = 0
        self._skipped_count = 0
        self._total_errors = 0
        self._execution_time_ms: Optional[float] = None
        self._panel_state: ExecutionPanelState = ExecutionPanelState.IDLE
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget's UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Header with title and clear button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        header_label = QLabel("Execution Summary")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)

        header_layout.addStretch()

        # Clear button
        self._clear_button = QPushButton("Clear")
        self._clear_button.setMaximumWidth(60)
        self._clear_button.setToolTip("Clear execution summary")
        self._clear_button.clicked.connect(self.clear)
        header_layout.addWidget(self._clear_button)

        layout.addLayout(header_layout)

        # Statistics row
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(8)

        # Total nodes
        self._total_stat = StatisticWidget("Total", 0, self.COLOR_INFO)
        stats_layout.addWidget(self._total_stat)

        # Successful nodes
        self._success_stat = StatisticWidget("Successful", 0, self.COLOR_SUCCESS)
        stats_layout.addWidget(self._success_stat)

        # Failed nodes
        self._failed_stat = StatisticWidget("Failed", 0, self.COLOR_FAILURE)
        stats_layout.addWidget(self._failed_stat)

        # Skipped nodes
        self._skipped_stat = StatisticWidget("Skipped", 0, self.COLOR_SKIPPED)
        stats_layout.addWidget(self._skipped_stat)

        stats_layout.addStretch()

        layout.addLayout(stats_layout)

        # Success rate progress bar section
        progress_frame = QFrame()
        progress_frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(8, 8, 8, 8)
        progress_layout.setSpacing(4)

        # Progress bar header
        progress_header = QHBoxLayout()
        self._progress_label = QLabel("Success Rate:")
        self._progress_label.setStyleSheet("color: #D4D4D4; font-size: 11px;")
        progress_header.addWidget(self._progress_label)

        self._percentage_label = QLabel("0%")
        self._percentage_label.setStyleSheet(
            "color: #4EC9B0; font-size: 12px; font-weight: bold;"
        )
        progress_header.addWidget(self._percentage_label)

        progress_header.addStretch()

        # Execution time
        self._time_label = QLabel("")
        self._time_label.setStyleSheet("color: #888; font-size: 11px;")
        progress_header.addWidget(self._time_label)

        progress_layout.addLayout(progress_header)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setMinimumHeight(8)
        self._progress_bar.setMaximumHeight(8)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #3C3C3C;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #4EC9B0;
                border-radius: 4px;
            }
        """)
        progress_layout.addWidget(self._progress_bar)

        layout.addWidget(progress_frame)

        # Error count summary line
        self._error_summary_label = QLabel("")
        self._error_summary_label.setStyleSheet("color: #888; font-size: 11px;")
        self._error_summary_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._error_summary_label)

        # Error list section
        self._error_list_frame = QFrame()
        self._error_list_frame.setStyleSheet("""
            QFrame {
                background-color: #252526;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
            }
        """)
        error_list_layout = QVBoxLayout(self._error_list_frame)
        error_list_layout.setContentsMargins(4, 4, 4, 4)
        error_list_layout.setSpacing(4)

        # Error list header
        error_list_header = QHBoxLayout()
        error_list_header.setContentsMargins(4, 0, 4, 0)
        self._error_list_label = QLabel("Errors (click to navigate)")
        self._error_list_label.setStyleSheet(
            "color: #F44747; font-size: 11px; font-weight: bold;"
        )
        error_list_header.addWidget(self._error_list_label)
        error_list_header.addStretch()

        # Show more / truncation indicator
        self._truncation_label = QLabel("")
        self._truncation_label.setStyleSheet("color: #888; font-size: 10px;")
        error_list_header.addWidget(self._truncation_label)

        error_list_layout.addLayout(error_list_header)

        # Error list widget
        self._error_list = QListWidget()
        self._error_list.setMinimumHeight(60)
        self._error_list.setMaximumHeight(150)
        self._error_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._error_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._error_list.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._error_list.setStyleSheet("""
            QListWidget {
                background-color: #1E1E1E;
                border: none;
                border-radius: 4px;
                color: #D4D4D4;
                font-size: 11px;
                outline: none;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #2D2D2D;
            }
            QListWidget::item:hover {
                background-color: #2D2D2D;
            }
            QListWidget::item:selected {
                background-color: #37373D;
                color: #F44747;
            }
            QScrollBar:vertical {
                background-color: #1E1E1E;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #5A5A5A;
                min-height: 20px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #787878;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Connect click signal
        self._error_list.itemClicked.connect(self._on_error_item_clicked)
        self._error_list.itemDoubleClicked.connect(self._on_error_item_double_clicked)

        error_list_layout.addWidget(self._error_list)

        layout.addWidget(self._error_list_frame)

        # Initially hide the error list frame
        self._error_list_frame.hide()

        # Empty state / status message
        self._status_label = QLabel("No execution data. Run your workflow to see results.")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(
            "color: #888; font-style: italic; padding: 20px;"
        )
        layout.addWidget(self._status_label)

        # Add stretch to push content to top
        layout.addStretch()

        # Set minimum size
        self.setMinimumHeight(150)

        # Initial state
        self._update_display()

    def _on_error_item_clicked(self, item: QListWidgetItem) -> None:
        """
        Handle single-click on an error item.

        Emits the error_clicked signal with the node_id and error_index.

        Args:
            item: The clicked list item.
        """
        if isinstance(item, ErrorListItem):
            self.error_clicked.emit(item.node_id, item.error_index)

    def _on_error_item_double_clicked(self, item: QListWidgetItem) -> None:
        """
        Handle double-click on an error item.

        Emits the node_navigate_requested signal to pan/zoom to the node.

        Args:
            item: The double-clicked list item.
        """
        if isinstance(item, ErrorListItem):
            self.node_navigate_requested.emit(item.node_id)

    def _populate_error_list(self) -> None:
        """
        Populate the error list widget with errors from node summaries.

        Clears and rebuilds the error list based on current node summaries.
        Limits display to MAX_DISPLAYED_ERRORS entries for performance.
        """
        from visualpython.execution.context import NodeExecutionStatus

        self._error_list.clear()

        if not self._node_summaries or self._total_errors == 0:
            self._error_list_frame.hide()
            self._truncation_label.setText("")
            return

        # Collect all errors with their node info
        error_entries: List[Tuple[str, str, int, str, str]] = []

        for node_id, summary in self._node_summaries.items():
            if summary.status == NodeExecutionStatus.FAILED and summary.errors:
                for error_index, error in enumerate(summary.errors):
                    # Get error type/category
                    error_type = error.category.name if error.category else "UNKNOWN"
                    error_message = error.message or "Unknown error"

                    error_entries.append((
                        node_id,
                        summary.node_name,
                        error_index,
                        error_type,
                        error_message,
                    ))

        if not error_entries:
            self._error_list_frame.hide()
            return

        # Check if we need to truncate
        total_errors = len(error_entries)
        displayed_errors = min(total_errors, MAX_DISPLAYED_ERRORS)

        # Add items to the list
        for entry in error_entries[:MAX_DISPLAYED_ERRORS]:
            node_id, node_name, error_index, error_type, error_message = entry
            item = ErrorListItem(
                node_id=node_id,
                node_name=node_name,
                error_index=error_index,
                error_type=error_type,
                error_message=error_message,
            )
            self._error_list.addItem(item)

        # Update truncation label if needed
        if total_errors > MAX_DISPLAYED_ERRORS:
            hidden_count = total_errors - MAX_DISPLAYED_ERRORS
            self._truncation_label.setText(
                f"Showing {displayed_errors} of {total_errors} errors "
                f"({hidden_count} more...)"
            )
        else:
            self._truncation_label.setText(f"{total_errors} error(s)")

        # Show the error list frame
        self._error_list_frame.show()

    def _update_display(self) -> None:
        """Update all display elements based on current statistics."""
        # Update statistics widgets
        self._total_stat.set_value(self._total_nodes)
        self._success_stat.set_value(self._successful_count)
        self._failed_stat.set_value(self._failed_count)
        self._skipped_stat.set_value(self._skipped_count)

        # Calculate success rate
        if self._total_nodes > 0:
            # Calculate success rate based on executed nodes (excluding skipped)
            executed = self._successful_count + self._failed_count
            if executed > 0:
                success_rate = (self._successful_count / executed) * 100
            else:
                success_rate = 0.0

            self._progress_bar.setValue(int(success_rate))
            self._percentage_label.setText(f"{success_rate:.1f}%")

            # Update progress bar color based on success rate
            if success_rate >= 100:
                bar_color = "#4EC9B0"  # Teal for perfect
                text_color = "#4EC9B0"
            elif success_rate >= 75:
                bar_color = "#4EC9B0"  # Teal for good
                text_color = "#4EC9B0"
            elif success_rate >= 50:
                bar_color = "#DCDCAA"  # Yellow for warning
                text_color = "#DCDCAA"
            else:
                bar_color = "#F44747"  # Red for poor
                text_color = "#F44747"

            self._progress_bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: #3C3C3C;
                    border: none;
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background-color: {bar_color};
                    border-radius: 4px;
                }}
            """)
            self._percentage_label.setStyleSheet(
                f"color: {text_color}; font-size: 12px; font-weight: bold;"
            )

            # Hide status message when we have data
            self._status_label.hide()
        else:
            self._progress_bar.setValue(0)
            self._percentage_label.setText("0%")
            self._status_label.show()

        # Update execution time
        if self._execution_time_ms is not None:
            if self._execution_time_ms >= 1000:
                time_str = f"Time: {self._execution_time_ms / 1000:.2f}s"
            else:
                time_str = f"Time: {self._execution_time_ms:.0f}ms"
            self._time_label.setText(time_str)
        else:
            self._time_label.setText("")

        # Update error summary
        if self._total_errors > 0:
            error_text = f"Total errors: {self._total_errors}"
            if self._failed_count > 0:
                error_text += f" across {self._failed_count} node(s)"
            self._error_summary_label.setText(error_text)
            self._error_summary_label.setStyleSheet(
                "color: #F44747; font-size: 11px;"
            )
            self._error_summary_label.show()
        elif self._total_nodes > 0 and self._failed_count == 0:
            self._error_summary_label.setText("All nodes executed successfully")
            self._error_summary_label.setStyleSheet(
                "color: #4EC9B0; font-size: 11px;"
            )
            self._error_summary_label.show()
        else:
            self._error_summary_label.hide()

        # Update error list
        self._populate_error_list()

    @pyqtSlot()
    def clear(self) -> None:
        """
        Clear all execution data and reset the panel to IDLE state.

        This method resets all statistics, clears the error list, and emits
        the 'cleared' signal. Use reset_all() if you also want to request
        graph node error indicator reset.
        """
        self._node_summaries.clear()
        self._total_nodes = 0
        self._successful_count = 0
        self._failed_count = 0
        self._skipped_count = 0
        self._total_errors = 0
        self._execution_time_ms = None
        self._error_list.clear()
        self._error_list_frame.hide()
        self._set_panel_state(ExecutionPanelState.IDLE)
        self._update_display()
        self.cleared.emit()

    @pyqtSlot()
    def reset_all(self) -> None:
        """
        Clear the panel and request reset of graph node error indicators.

        This is more comprehensive than clear() - it also emits the
        reset_requested signal to notify the application to reset node
        error indicators on the graph canvas.
        """
        self.clear()
        self.reset_requested.emit()

    def _set_panel_state(self, state: ExecutionPanelState) -> None:
        """
        Set the panel state and emit state_changed signal if changed.

        Args:
            state: The new panel state.
        """
        if self._panel_state != state:
            self._panel_state = state
            self.state_changed.emit(state)

    @property
    def panel_state(self) -> ExecutionPanelState:
        """Get the current panel state."""
        return self._panel_state

    def set_statistics(
        self,
        total_nodes: int,
        successful: int,
        failed: int,
        skipped: int,
        total_errors: int,
        execution_time_ms: Optional[float] = None,
    ) -> None:
        """
        Set the execution statistics directly.

        Args:
            total_nodes: Total number of nodes in the workflow.
            successful: Number of nodes that executed successfully.
            failed: Number of nodes that failed.
            skipped: Number of nodes that were skipped.
            total_errors: Total number of errors across all nodes.
            execution_time_ms: Optional execution time in milliseconds.
        """
        self._total_nodes = total_nodes
        self._successful_count = successful
        self._failed_count = failed
        self._skipped_count = skipped
        self._total_errors = total_errors
        self._execution_time_ms = execution_time_ms
        self._update_display()

    def update_from_summaries(
        self,
        summaries: Dict[str, "NodeExecutionSummary"],
        execution_time_ms: Optional[float] = None,
    ) -> None:
        """
        Update statistics from a dictionary of node execution summaries.

        This is the primary method for updating the panel after execution
        completes. It calculates all statistics from the provided summaries.

        Args:
            summaries: Dictionary mapping node_id to NodeExecutionSummary.
            execution_time_ms: Optional total execution time in milliseconds.
        """
        from visualpython.execution.context import NodeExecutionStatus

        self._node_summaries = summaries.copy()
        self._execution_time_ms = execution_time_ms

        # Calculate statistics
        self._total_nodes = len(summaries)
        self._successful_count = 0
        self._failed_count = 0
        self._skipped_count = 0
        self._total_errors = 0

        for summary in summaries.values():
            if summary.status == NodeExecutionStatus.SUCCESS:
                self._successful_count += 1
            elif summary.status == NodeExecutionStatus.FAILED:
                self._failed_count += 1
                self._total_errors += summary.error_count
            elif summary.status == NodeExecutionStatus.SKIPPED:
                self._skipped_count += 1

        self._update_display()

    def update_from_context(self, context: "ExecutionContext") -> None:
        """
        Update statistics from an ExecutionContext.

        This method extracts all relevant statistics from the execution
        context after execution completes.

        Args:
            context: The ExecutionContext with execution results.
        """
        from visualpython.execution.context import ExecutionContext

        # Get statistics from context
        stats = context.get_execution_statistics()

        self._total_nodes = stats.get("total_nodes", 0)
        self._successful_count = stats.get("successful", 0)
        self._failed_count = stats.get("failed", 0)
        self._skipped_count = stats.get("skipped", 0)
        self._total_errors = stats.get("total_errors", 0)

        # Get summaries for later use (e.g., error list view)
        self._node_summaries = context.get_all_node_summaries()

        # Get execution time from result
        result = context.get_result()
        self._execution_time_ms = result.execution_time_ms

        self._update_display()

    def update_from_result(self, result: "ExecutionResult") -> None:
        """
        Update statistics from an ExecutionResult.

        This is the most complete method for updating the panel after
        execution completes. It extracts all statistics and summaries
        from the result object.

        Args:
            result: The ExecutionResult from the execution engine.
        """
        from visualpython.execution.context import (
            ExecutionStatus,
            NodeExecutionStatus,
        )

        # Get summaries from result
        self._node_summaries = result.node_summaries.copy()
        self._execution_time_ms = result.execution_time_ms

        # Calculate statistics from summaries
        self._total_nodes = len(self._node_summaries)
        self._successful_count = 0
        self._failed_count = 0
        self._skipped_count = 0
        self._total_errors = 0

        for summary in self._node_summaries.values():
            if summary.status == NodeExecutionStatus.SUCCESS:
                self._successful_count += 1
            elif summary.status == NodeExecutionStatus.FAILED:
                self._failed_count += 1
                self._total_errors += summary.error_count
            elif summary.status == NodeExecutionStatus.SKIPPED:
                self._skipped_count += 1

        # Determine final panel state based on result status
        if result.status == ExecutionStatus.CANCELLED:
            self._set_panel_state(ExecutionPanelState.CANCELLED)
        elif result.status == ExecutionStatus.COMPLETED:
            if self._failed_count > 0 or self._total_errors > 0:
                self._set_panel_state(ExecutionPanelState.COMPLETED_WITH_ERRORS)
            else:
                self._set_panel_state(ExecutionPanelState.COMPLETED_SUCCESS)
        elif result.status == ExecutionStatus.FAILED:
            self._set_panel_state(ExecutionPanelState.COMPLETED_WITH_ERRORS)
        else:
            self._set_panel_state(ExecutionPanelState.IDLE)

        self._update_display()

    def update_node_status(
        self,
        node_id: str,
        summary: "NodeExecutionSummary",
    ) -> None:
        """
        Update the status of a single node during real-time execution.

        This method allows incremental updates during execution, so the
        panel shows progress as each node completes.

        Args:
            node_id: The ID of the node that was just executed.
            summary: The execution summary for the node.
        """
        from visualpython.execution.context import NodeExecutionStatus

        # Store/update the summary
        old_summary = self._node_summaries.get(node_id)
        self._node_summaries[node_id] = summary

        # Update counts based on the change
        if old_summary is None:
            # New node - increment appropriate counter
            self._total_nodes += 1
            if summary.status == NodeExecutionStatus.SUCCESS:
                self._successful_count += 1
            elif summary.status == NodeExecutionStatus.FAILED:
                self._failed_count += 1
                self._total_errors += summary.error_count
            elif summary.status == NodeExecutionStatus.SKIPPED:
                self._skipped_count += 1
        else:
            # Update existing node - adjust counters
            # First, undo the old status
            if old_summary.status == NodeExecutionStatus.SUCCESS:
                self._successful_count -= 1
            elif old_summary.status == NodeExecutionStatus.FAILED:
                self._failed_count -= 1
                self._total_errors -= old_summary.error_count
            elif old_summary.status == NodeExecutionStatus.SKIPPED:
                self._skipped_count -= 1

            # Then, apply the new status
            if summary.status == NodeExecutionStatus.SUCCESS:
                self._successful_count += 1
            elif summary.status == NodeExecutionStatus.FAILED:
                self._failed_count += 1
                self._total_errors += summary.error_count
            elif summary.status == NodeExecutionStatus.SKIPPED:
                self._skipped_count += 1

        # Refresh the display
        self._update_display()

    def set_execution_time(self, time_ms: float) -> None:
        """
        Set the execution time.

        Args:
            time_ms: Execution time in milliseconds.
        """
        self._execution_time_ms = time_ms
        self._update_display()

    @pyqtSlot()
    def execution_started(self) -> None:
        """
        Called when script execution starts.

        Clears previous results and transitions to RUNNING state.
        Shows a "running" status message to indicate execution is in progress.
        """
        # Clear previous results first
        self._node_summaries.clear()
        self._total_nodes = 0
        self._successful_count = 0
        self._failed_count = 0
        self._skipped_count = 0
        self._total_errors = 0
        self._execution_time_ms = None
        self._error_list.clear()
        self._error_list_frame.hide()

        # Transition to RUNNING state
        self._set_panel_state(ExecutionPanelState.RUNNING)

        # Update display to show running state
        self._update_display()
        self._status_label.setText("Execution in progress...")
        self._status_label.setStyleSheet(
            "color: #569CD6; font-style: italic; padding: 20px;"
        )
        self._status_label.show()

    @pyqtSlot(bool, str)
    def execution_finished(self, success: bool, message: str = "") -> None:
        """
        Called when script execution finishes.

        Transitions the panel to the appropriate completion state based on
        whether execution succeeded, failed, or was cancelled.

        Note: For complete statistics, use update_from_result() or
        update_from_summaries() after calling this method.

        Args:
            success: Whether execution was successful overall.
            message: Optional status message (e.g., "Execution stopped by user").
        """
        # Determine the appropriate state based on results
        if self._total_nodes == 0:
            self._set_panel_state(ExecutionPanelState.NO_NODES)
            if message:
                self._status_label.setText(message)
            else:
                self._status_label.setText(
                    "Execution completed. No nodes were executed."
                )
            self._status_label.setStyleSheet(
                "color: #888; font-style: italic; padding: 20px;"
            )
            self._status_label.show()
        elif "stopped" in message.lower() or "cancelled" in message.lower():
            self._set_panel_state(ExecutionPanelState.CANCELLED)
        elif self._failed_count > 0 or self._total_errors > 0:
            self._set_panel_state(ExecutionPanelState.COMPLETED_WITH_ERRORS)
        elif success:
            self._set_panel_state(ExecutionPanelState.COMPLETED_SUCCESS)
        else:
            self._set_panel_state(ExecutionPanelState.COMPLETED_WITH_ERRORS)

    @pyqtSlot()
    def execution_cancelled(self) -> None:
        """
        Called when script execution is cancelled by the user.

        Transitions the panel to CANCELLED state and shows appropriate messaging.
        Partial results (if any) are preserved in the display.
        """
        self._set_panel_state(ExecutionPanelState.CANCELLED)

        # Update status label to show cancellation
        if self._total_nodes == 0:
            self._status_label.setText("Execution cancelled. No nodes were executed.")
        else:
            self._status_label.setText(
                f"Execution cancelled. Partial results: {self._successful_count} succeeded, "
                f"{self._failed_count} failed, {self._skipped_count} skipped."
            )
        self._status_label.setStyleSheet(
            "color: #DCDCAA; font-style: italic; padding: 20px;"
        )
        # Only show the status label if we don't have meaningful statistics to show
        if self._total_nodes == 0:
            self._status_label.show()

    def get_failed_node_ids(self) -> List[str]:
        """
        Get the list of node IDs that failed.

        Returns:
            List of node IDs with failures.
        """
        from visualpython.execution.context import NodeExecutionStatus

        return [
            node_id
            for node_id, summary in self._node_summaries.items()
            if summary.status == NodeExecutionStatus.FAILED
        ]

    def get_node_summary(self, node_id: str) -> Optional["NodeExecutionSummary"]:
        """
        Get the execution summary for a specific node.

        Args:
            node_id: The ID of the node.

        Returns:
            The NodeExecutionSummary if available, None otherwise.
        """
        return self._node_summaries.get(node_id)

    def get_error_at_index(self, index: int) -> Optional[Tuple[str, int]]:
        """
        Get the node_id and error_index for the error at the specified list index.

        Args:
            index: The index in the error list.

        Returns:
            Tuple of (node_id, error_index) if valid, None otherwise.
        """
        if 0 <= index < self._error_list.count():
            item = self._error_list.item(index)
            if isinstance(item, ErrorListItem):
                return (item.node_id, item.error_index)
        return None

    def select_error(self, node_id: str, error_index: int = 0) -> bool:
        """
        Select an error in the list by node_id and error_index.

        Args:
            node_id: The ID of the node.
            error_index: The index of the error (default 0).

        Returns:
            True if the error was found and selected, False otherwise.
        """
        for i in range(self._error_list.count()):
            item = self._error_list.item(i)
            if isinstance(item, ErrorListItem):
                if item.node_id == node_id and item.error_index == error_index:
                    self._error_list.setCurrentItem(item)
                    self._error_list.scrollToItem(item)
                    return True
        return False

    def get_errors_for_node(self, node_id: str) -> List[Tuple[int, str]]:
        """
        Get all errors for a specific node from the error list.

        Args:
            node_id: The ID of the node.

        Returns:
            List of tuples (error_index, error_message) for the node.
        """
        errors: List[Tuple[int, str]] = []
        for i in range(self._error_list.count()):
            item = self._error_list.item(i)
            if isinstance(item, ErrorListItem) and item.node_id == node_id:
                errors.append((item.error_index, item.error_message))
        return errors

    @property
    def error_list_widget(self) -> QListWidget:
        """Get the error list widget for external access."""
        return self._error_list

    @property
    def error_count_in_list(self) -> int:
        """Get the number of errors currently displayed in the list."""
        return self._error_list.count()

    @property
    def total_nodes(self) -> int:
        """Get the total node count."""
        return self._total_nodes

    @property
    def successful_count(self) -> int:
        """Get the successful node count."""
        return self._successful_count

    @property
    def failed_count(self) -> int:
        """Get the failed node count."""
        return self._failed_count

    @property
    def skipped_count(self) -> int:
        """Get the skipped node count."""
        return self._skipped_count

    @property
    def total_errors(self) -> int:
        """Get the total error count."""
        return self._total_errors

    @property
    def success_rate(self) -> float:
        """
        Get the success rate as a percentage.

        Returns:
            Success rate between 0.0 and 100.0.
        """
        executed = self._successful_count + self._failed_count
        if executed > 0:
            return (self._successful_count / executed) * 100
        return 0.0

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return self._total_errors > 0

    @property
    def is_running(self) -> bool:
        """Check if execution is currently running."""
        return self._panel_state == ExecutionPanelState.RUNNING

    @property
    def is_completed(self) -> bool:
        """Check if execution has completed (with or without errors)."""
        return self._panel_state in (
            ExecutionPanelState.COMPLETED_SUCCESS,
            ExecutionPanelState.COMPLETED_WITH_ERRORS,
            ExecutionPanelState.CANCELLED,
        )

    @property
    def is_idle(self) -> bool:
        """Check if panel is in idle state (no execution in progress)."""
        return self._panel_state == ExecutionPanelState.IDLE

    @property
    def was_cancelled(self) -> bool:
        """Check if the last execution was cancelled."""
        return self._panel_state == ExecutionPanelState.CANCELLED

    @property
    def execution_time_ms(self) -> Optional[float]:
        """Get the execution time in milliseconds."""
        return self._execution_time_ms

    def get_state_description(self) -> str:
        """
        Get a human-readable description of the current panel state.

        Returns:
            A string describing the current state.
        """
        state_descriptions = {
            ExecutionPanelState.IDLE: "Ready",
            ExecutionPanelState.RUNNING: "Executing...",
            ExecutionPanelState.COMPLETED_SUCCESS: "Completed successfully",
            ExecutionPanelState.COMPLETED_WITH_ERRORS: "Completed with errors",
            ExecutionPanelState.CANCELLED: "Cancelled",
            ExecutionPanelState.NO_NODES: "No nodes executed",
        }
        return state_descriptions.get(self._panel_state, "Unknown")
