"""
Node properties panel for viewing and editing selected node properties.

This module provides a side panel that displays properties of selected nodes
and allows users to edit them. It dynamically builds property editors based
on the selected node type.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QTextEdit,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QGroupBox,
    QPushButton,
    QColorDialog,
)

from visualpython.ui.widgets.code_editor import CodeEditorWidget
from visualpython.utils.logging import get_logger

if TYPE_CHECKING:
    from visualpython.nodes.models.base_node import BaseNode
    from visualpython.graph.graph import Graph

logger = get_logger(__name__)


class PropertyEditor(QWidget):
    """
    Base class for property editors.

    Provides a common interface for different property type editors.

    Signals:
        value_changed: Emitted when the property value changes.
    """

    value_changed = pyqtSignal(str, object)  # property_name, new_value

    def __init__(
        self,
        property_name: str,
        initial_value: Any,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the property editor.

        Args:
            property_name: Name of the property being edited.
            initial_value: Initial value of the property.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._property_name = property_name
        self._initial_value = initial_value

    @property
    def property_name(self) -> str:
        """Get the property name."""
        return self._property_name

    def get_value(self) -> Any:
        """Get the current value from the editor."""
        raise NotImplementedError

    def set_value(self, value: Any) -> None:
        """Set the value in the editor."""
        raise NotImplementedError


class StringPropertyEditor(PropertyEditor):
    """Editor for string properties using a single-line text input."""

    def __init__(
        self,
        property_name: str,
        initial_value: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(property_name, initial_value, parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._line_edit = QLineEdit()
        self._line_edit.setText(str(initial_value) if initial_value else "")
        self._line_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._line_edit)

    def _on_text_changed(self, text: str) -> None:
        """Handle text change."""
        self.value_changed.emit(self._property_name, text)

    def get_value(self) -> str:
        return self._line_edit.text()

    def set_value(self, value: Any) -> None:
        self._line_edit.setText(str(value) if value else "")


class MultilineStringPropertyEditor(PropertyEditor):
    """Editor for multiline string properties using a text area."""

    def __init__(
        self,
        property_name: str,
        initial_value: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(property_name, initial_value, parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._text_edit = QTextEdit()
        self._text_edit.setPlainText(str(initial_value) if initial_value else "")
        self._text_edit.setMinimumHeight(100)
        self._text_edit.setMaximumHeight(200)
        self._text_edit.textChanged.connect(self._on_text_changed)

        # Use monospace font for code
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._text_edit.setFont(font)

        layout.addWidget(self._text_edit)

    def _on_text_changed(self) -> None:
        """Handle text change."""
        self.value_changed.emit(self._property_name, self._text_edit.toPlainText())

    def get_value(self) -> str:
        return self._text_edit.toPlainText()

    def set_value(self, value: Any) -> None:
        self._text_edit.setPlainText(str(value) if value else "")


class CodePropertyEditor(PropertyEditor):
    """
    Editor for Python code properties with real-time syntax checking.

    Provides a full-featured code editor with:
    - Python syntax highlighting
    - Line numbers
    - Real-time syntax error detection
    - Inline error indicators and underlines

    Signals:
        validation_state_changed: Emitted when code validation state changes.
    """

    validation_state_changed = pyqtSignal(bool, list)  # is_valid, errors

    def __init__(
        self,
        property_name: str,
        initial_value: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(property_name, initial_value, parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Create the code editor with validation enabled
        self._code_editor = CodeEditorWidget(enable_validation=True)
        self._code_editor.setPlainText(str(initial_value) if initial_value else "")
        self._code_editor.setMinimumHeight(150)
        self._code_editor.setMaximumHeight(300)

        # Connect signals
        self._code_editor.code_changed.connect(self._on_code_changed)
        self._code_editor.validation_changed.connect(self._on_validation_changed)

        layout.addWidget(self._code_editor)

        # Error status label
        self._error_label = QLabel()
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("""
            QLabel {
                color: #CC0000;
                font-size: 10px;
                padding: 4px;
                background-color: #FFF0F0;
                border: 1px solid #FFCCCC;
                border-radius: 3px;
            }
        """)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # Trigger initial validation
        if initial_value:
            self._code_editor.validate_now()

    def _on_code_changed(self, code: str) -> None:
        """Handle code change."""
        self.value_changed.emit(self._property_name, code)

    def _on_validation_changed(self, is_valid: bool, errors: list) -> None:
        """Handle validation state change."""
        if is_valid or not errors:
            self._error_label.hide()
        else:
            # Show first error in the label
            error = errors[0]
            error_text = f"Line {error.line}: {error.message}"
            if len(errors) > 1:
                error_text += f" (+{len(errors) - 1} more)"
            self._error_label.setText(error_text)
            self._error_label.show()

        self.validation_state_changed.emit(is_valid, errors)

    def get_value(self) -> str:
        return self._code_editor.code

    def set_value(self, value: Any) -> None:
        self._code_editor.code = str(value) if value else ""

    @property
    def is_valid(self) -> bool:
        """Check if the current code is valid."""
        return self._code_editor.is_valid

    @property
    def code_editor(self) -> CodeEditorWidget:
        """Get the underlying code editor widget."""
        return self._code_editor


class IntPropertyEditor(PropertyEditor):
    """Editor for integer properties using a spin box."""

    def __init__(
        self,
        property_name: str,
        initial_value: int,
        min_value: int = -999999,
        max_value: int = 999999,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(property_name, initial_value, parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._spin_box = QSpinBox()
        self._spin_box.setRange(min_value, max_value)
        self._spin_box.setValue(int(initial_value) if initial_value else 0)
        self._spin_box.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._spin_box)

    def _on_value_changed(self, value: int) -> None:
        """Handle value change."""
        self.value_changed.emit(self._property_name, value)

    def get_value(self) -> int:
        return self._spin_box.value()

    def set_value(self, value: Any) -> None:
        self._spin_box.setValue(int(value) if value else 0)


class FloatPropertyEditor(PropertyEditor):
    """Editor for float properties using a double spin box."""

    def __init__(
        self,
        property_name: str,
        initial_value: float,
        min_value: float = -999999.0,
        max_value: float = 999999.0,
        decimals: int = 2,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(property_name, initial_value, parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._spin_box = QDoubleSpinBox()
        self._spin_box.setRange(min_value, max_value)
        self._spin_box.setDecimals(decimals)
        self._spin_box.setValue(float(initial_value) if initial_value else 0.0)
        self._spin_box.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self._spin_box)

    def _on_value_changed(self, value: float) -> None:
        """Handle value change."""
        self.value_changed.emit(self._property_name, value)

    def get_value(self) -> float:
        return self._spin_box.value()

    def set_value(self, value: Any) -> None:
        self._spin_box.setValue(float(value) if value else 0.0)


class BoolPropertyEditor(PropertyEditor):
    """Editor for boolean properties using a checkbox."""

    def __init__(
        self,
        property_name: str,
        initial_value: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(property_name, initial_value, parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._checkbox = QCheckBox()
        self._checkbox.setChecked(bool(initial_value) if initial_value else False)
        self._checkbox.stateChanged.connect(self._on_state_changed)
        layout.addWidget(self._checkbox)

    def _on_state_changed(self, state: int) -> None:
        """Handle state change."""
        self.value_changed.emit(
            self._property_name,
            state == Qt.CheckState.Checked.value
        )

    def get_value(self) -> bool:
        return self._checkbox.isChecked()

    def set_value(self, value: Any) -> None:
        self._checkbox.setChecked(bool(value) if value else False)


class ColorPropertyEditor(PropertyEditor):
    """Editor for color properties using a color picker button.

    Displays a colored button that shows the current color. Clicking it
    opens a color picker dialog. A reset button allows returning to
    the default color.
    """

    def __init__(
        self,
        property_name: str,
        initial_value: Optional[str],
        default_color: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the color property editor.

        Args:
            property_name: Name of the property being edited.
            initial_value: Current custom color (hex string) or None for default.
            default_color: The default color (hex string) to reset to.
            parent: Optional parent widget.
        """
        super().__init__(property_name, initial_value, parent)
        self._default_color = default_color
        self._current_color = initial_value if initial_value else default_color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Color picker button
        self._color_button = QPushButton()
        self._color_button.setFixedSize(60, 24)
        self._color_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_button.clicked.connect(self._on_color_button_clicked)
        self._update_button_style()
        layout.addWidget(self._color_button)

        # Reset button (only visible when custom color is set)
        self._reset_button = QPushButton("Reset")
        self._reset_button.setFixedWidth(50)
        self._reset_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_button.clicked.connect(self._on_reset_clicked)
        self._reset_button.setVisible(initial_value is not None)
        layout.addWidget(self._reset_button)

        layout.addStretch()

    def _update_button_style(self) -> None:
        """Update the color button's background to show current color."""
        # Calculate contrasting text color
        color = QColor(self._current_color)
        brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
        text_color = "#000000" if brightness > 128 else "#FFFFFF"

        self._color_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._current_color};
                color: {text_color};
                border: 1px solid #555;
                border-radius: 3px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                border: 1px solid #888;
            }}
        """)
        self._color_button.setText(self._current_color.upper())

    def _on_color_button_clicked(self) -> None:
        """Handle color button click - show color picker dialog."""
        current = QColor(self._current_color)
        color = QColorDialog.getColor(current, self, "Choose Node Color")

        if color.isValid():
            self._current_color = color.name()
            self._update_button_style()
            self._reset_button.setVisible(True)
            self.value_changed.emit(self._property_name, self._current_color)

    def _on_reset_clicked(self) -> None:
        """Handle reset button click - revert to default color."""
        self._current_color = self._default_color
        self._update_button_style()
        self._reset_button.setVisible(False)
        # Emit None to indicate reset to default
        self.value_changed.emit(self._property_name, None)

    def get_value(self) -> Optional[str]:
        """Get the current custom color, or None if using default."""
        if self._current_color == self._default_color:
            return None
        return self._current_color

    def set_value(self, value: Any) -> None:
        """Set the color value."""
        if value is None:
            self._current_color = self._default_color
            self._reset_button.setVisible(False)
        else:
            self._current_color = str(value)
            self._reset_button.setVisible(True)
        self._update_button_style()


class NodePropertiesPanel(QWidget):
    """
    Side panel widget for viewing and editing node properties.

    The NodePropertiesPanel displays properties of the currently selected
    node(s) and allows users to edit them. When multiple nodes are selected,
    it shows a summary. When a single node is selected, it shows all
    editable properties with appropriate editors.

    Signals:
        property_changed: Emitted when a property value is changed.
                         Parameters: (node_id: str, property_name: str, new_value: Any)
        node_name_changed: Emitted when the node name is changed.
                          Parameters: (node_id: str, new_name: str)
    """

    property_changed = pyqtSignal(str, str, object)  # node_id, property_name, value
    node_name_changed = pyqtSignal(str, str)  # node_id, new_name
    node_color_changed = pyqtSignal(str, object)  # node_id, new_color (str or None)

    # Properties that are multiline (require text area instead of line edit)
    MULTILINE_PROPERTIES = {"code"}

    # Properties that require the code editor with syntax checking
    CODE_PROPERTIES = {"code"}

    # Properties to exclude from the panel (handled specially or internal)
    EXCLUDED_PROPERTIES = set()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the node properties panel.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._current_node: Optional[BaseNode] = None
        self._current_node_id: Optional[str] = None
        self._property_editors: Dict[str, PropertyEditor] = {}
        self._graph: Optional[Graph] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget's UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Properties")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Scroll area for properties
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        # Content widget inside scroll area
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        self._content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll_area.setWidget(self._content_widget)
        main_layout.addWidget(scroll_area)

        # Status label for when no node is selected
        self._no_selection_label = QLabel("No node selected")
        self._no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_selection_label.setStyleSheet("color: #888; font-style: italic;")
        self._content_layout.addWidget(self._no_selection_label)

        # Multi-selection label
        self._multi_selection_label = QLabel()
        self._multi_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._multi_selection_label.setStyleSheet("color: #888; font-style: italic;")
        self._multi_selection_label.hide()
        self._content_layout.addWidget(self._multi_selection_label)

        # Properties container (will be populated dynamically)
        self._properties_container = QWidget()
        self._properties_layout = QVBoxLayout(self._properties_container)
        self._properties_layout.setContentsMargins(0, 0, 0, 0)
        self._properties_layout.setSpacing(8)
        self._properties_container.hide()
        self._content_layout.addWidget(self._properties_container)

        # Add stretch at bottom
        self._content_layout.addStretch()

        # Set minimum width
        self.setMinimumWidth(200)

    def set_graph(self, graph: "Graph") -> None:
        """
        Set the graph reference for node lookups.

        Args:
            graph: The graph containing the nodes.
        """
        self._graph = graph

    @pyqtSlot(list)
    def on_selection_changed(self, selected_node_ids: List[str]) -> None:
        """
        Handle selection change from the graph view.

        Args:
            selected_node_ids: List of selected node IDs.
        """
        if not selected_node_ids:
            self._show_no_selection()
        elif len(selected_node_ids) == 1:
            self._show_node_properties(selected_node_ids[0])
        else:
            self._show_multi_selection(len(selected_node_ids))

    def _show_no_selection(self) -> None:
        """Show the no selection state."""
        self._current_node = None
        self._current_node_id = None
        self._clear_property_editors()

        self._no_selection_label.show()
        self._multi_selection_label.hide()
        self._properties_container.hide()

    def _show_multi_selection(self, count: int) -> None:
        """
        Show the multi-selection state.

        Args:
            count: Number of selected nodes.
        """
        self._current_node = None
        self._current_node_id = None
        self._clear_property_editors()

        self._no_selection_label.hide()
        self._multi_selection_label.setText(f"{count} nodes selected")
        self._multi_selection_label.show()
        self._properties_container.hide()

    def _show_node_properties(self, node_id: str) -> None:
        """
        Show properties for a single selected node.

        Args:
            node_id: The ID of the selected node.
        """
        if self._graph is None:
            return

        node = self._graph.get_node(node_id)
        if node is None:
            self._show_no_selection()
            return

        self._current_node = node
        self._current_node_id = node_id

        # Hide status labels
        self._no_selection_label.hide()
        self._multi_selection_label.hide()

        # Clear existing property editors
        self._clear_property_editors()

        # Build property editors for this node
        self._build_property_editors(node)

        # Show properties container
        self._properties_container.show()

    def _clear_property_editors(self) -> None:
        """Clear all property editors."""
        self._property_editors.clear()

        # Remove all widgets from the properties layout
        while self._properties_layout.count():
            item = self._properties_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_property_editors(self, node: "BaseNode") -> None:
        """
        Build property editors for a node.

        Args:
            node: The node to build editors for.
        """
        # Node info section
        info_group = QGroupBox("Node Info")
        info_layout = QFormLayout(info_group)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_layout.setSpacing(4)

        # Node type (read-only)
        type_label = QLabel(node.node_type)
        type_label.setStyleSheet("color: #888;")
        info_layout.addRow("Type:", type_label)

        # Node ID (read-only, truncated)
        id_label = QLabel(node.id[:8] + "...")
        id_label.setStyleSheet("color: #888; font-family: Consolas;")
        id_label.setToolTip(node.id)
        info_layout.addRow("ID:", id_label)

        # Node name (editable)
        name_editor = StringPropertyEditor("name", node.name)
        name_editor.value_changed.connect(self._on_name_changed)
        info_layout.addRow("Name:", name_editor)
        self._property_editors["name"] = name_editor

        # Node color (editable with color picker)
        color_editor = ColorPropertyEditor(
            "custom_color",
            node.custom_color,
            node.node_color,  # Default color for this node type
        )
        color_editor.value_changed.connect(self._on_color_changed)
        info_layout.addRow("Color:", color_editor)
        self._property_editors["custom_color"] = color_editor

        self._properties_layout.addWidget(info_group)

        # Position section
        position_group = QGroupBox("Position")
        position_layout = QFormLayout(position_group)
        position_layout.setContentsMargins(8, 8, 8, 8)
        position_layout.setSpacing(4)

        # X position
        x_editor = FloatPropertyEditor("position_x", node.position.x, decimals=1)
        x_editor.value_changed.connect(self._on_position_changed)
        position_layout.addRow("X:", x_editor)
        self._property_editors["position_x"] = x_editor

        # Y position
        y_editor = FloatPropertyEditor("position_y", node.position.y, decimals=1)
        y_editor.value_changed.connect(self._on_position_changed)
        position_layout.addRow("Y:", y_editor)
        self._property_editors["position_y"] = y_editor

        self._properties_layout.addWidget(position_group)

        # Comment/Notes section
        comment_group = QGroupBox("Comment")
        comment_layout = QFormLayout(comment_group)
        comment_layout.setContentsMargins(8, 8, 8, 8)
        comment_layout.setSpacing(4)

        # Comment editor (multiline text area)
        comment_editor = MultilineStringPropertyEditor("comment", node.comment)
        comment_editor.value_changed.connect(self._on_comment_changed)
        comment_layout.addRow(comment_editor)
        self._property_editors["comment"] = comment_editor

        self._properties_layout.addWidget(comment_group)

        # Custom properties section (from _get_serializable_properties)
        custom_props = node._get_serializable_properties()
        if custom_props:
            props_group = QGroupBox("Properties")
            props_layout = QFormLayout(props_group)
            props_layout.setContentsMargins(8, 8, 8, 8)
            props_layout.setSpacing(4)

            for prop_name, prop_value in custom_props.items():
                if prop_name in self.EXCLUDED_PROPERTIES:
                    continue

                # Create appropriate editor based on value type
                editor = self._create_property_editor(prop_name, prop_value)
                if editor:
                    editor.value_changed.connect(self._on_property_changed)

                    # Format the label nicely
                    label = self._format_property_label(prop_name)
                    props_layout.addRow(f"{label}:", editor)
                    self._property_editors[prop_name] = editor

            self._properties_layout.addWidget(props_group)

    def _create_property_editor(
        self,
        property_name: str,
        value: Any,
    ) -> Optional[PropertyEditor]:
        """
        Create an appropriate property editor for a value.

        Args:
            property_name: Name of the property.
            value: Current value of the property.

        Returns:
            A PropertyEditor instance or None if type is not supported.
        """
        # Check for code properties first (with real-time syntax checking)
        if property_name in self.CODE_PROPERTIES:
            editor = CodePropertyEditor(property_name, value)
            # Connect validation state changes to update node
            editor.validation_state_changed.connect(
                lambda is_valid, errors: self._on_code_validation_changed(
                    property_name, is_valid, errors
                )
            )
            return editor

        # Check for other multiline properties
        if property_name in self.MULTILINE_PROPERTIES:
            return MultilineStringPropertyEditor(property_name, value)

        # Determine editor type based on value type
        if isinstance(value, bool):
            return BoolPropertyEditor(property_name, value)
        elif isinstance(value, int):
            return IntPropertyEditor(property_name, value)
        elif isinstance(value, float):
            return FloatPropertyEditor(property_name, value)
        elif isinstance(value, str):
            # Check if it looks like multiline content
            if "\n" in str(value) or len(str(value)) > 100:
                return MultilineStringPropertyEditor(property_name, value)
            return StringPropertyEditor(property_name, value)
        else:
            # Default to string editor for unknown types
            return StringPropertyEditor(property_name, str(value) if value else "")

    def _format_property_label(self, property_name: str) -> str:
        """
        Format a property name into a display label.

        Args:
            property_name: The property name to format.

        Returns:
            Formatted label string.
        """
        # Convert snake_case to Title Case
        return property_name.replace("_", " ").title()

    def _on_name_changed(self, property_name: str, value: Any) -> None:
        """Handle node name change."""
        if self._current_node and self._current_node_id:
            self._current_node.name = value
            self.node_name_changed.emit(self._current_node_id, value)

    def _on_position_changed(self, property_name: str, value: Any) -> None:
        """Handle position property change."""
        if self._current_node and self._current_node_id:
            if property_name == "position_x":
                self._current_node.position.x = float(value)
            elif property_name == "position_y":
                self._current_node.position.y = float(value)

            self.property_changed.emit(
                self._current_node_id,
                property_name,
                value
            )

    def _on_comment_changed(self, property_name: str, value: Any) -> None:
        """Handle comment property change."""
        if self._current_node and self._current_node_id:
            self._current_node.comment = value
            self.property_changed.emit(
                self._current_node_id,
                "comment",
                value
            )

    def _on_color_changed(self, property_name: str, value: Any) -> None:
        """Handle node color change.

        Args:
            property_name: Should be 'custom_color'.
            value: New color as hex string, or None to reset to default.
        """
        if self._current_node and self._current_node_id:
            self._current_node.custom_color = value
            self.node_color_changed.emit(self._current_node_id, value)

    def _on_property_changed(self, property_name: str, value: Any) -> None:
        """Handle property value change."""
        if self._current_node and self._current_node_id:
            # Try to set the property using the setter if available
            if hasattr(self._current_node, property_name):
                try:
                    setattr(self._current_node, property_name, value)
                except AttributeError:
                    # Property might be read-only or have no setter
                    logger.debug("Property panel attribute error", exc_info=True)
                    pass

            self.property_changed.emit(
                self._current_node_id,
                property_name,
                value
            )

    def _on_code_validation_changed(
        self,
        property_name: str,
        is_valid: bool,
        errors: list
    ) -> None:
        """Handle code validation state changes.

        Updates the node's validation state when code syntax is checked.

        Args:
            property_name: Name of the code property.
            is_valid: Whether the code passed validation.
            errors: List of validation errors if any.
        """
        if self._current_node and self._current_node_id:
            # Update node validation state if supported
            if hasattr(self._current_node, 'set_validation_state'):
                self._current_node.set_validation_state(is_valid, errors)
            elif hasattr(self._current_node, '_validation_errors'):
                self._current_node._validation_errors = errors
                self._current_node._is_code_valid = is_valid

    def refresh(self) -> None:
        """Refresh the property panel with current node values."""
        if self._current_node_id:
            self._show_node_properties(self._current_node_id)
        else:
            self._show_no_selection()

    def get_current_node_id(self) -> Optional[str]:
        """Get the ID of the currently displayed node."""
        return self._current_node_id
