"""
Node naming dialog for customizing node names when creating workflows from selection.

This module provides a dialog that allows users to set custom names for each node
when saving a selection as a workflow.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFormLayout,
    QWidget,
    QScrollArea,
    QGroupBox,
)


class NodeNamingDialog(QDialog):
    """
    A dialog for customizing node names in a workflow.

    This dialog allows users to:
    - Set custom names for each selected node
    - Set custom names for input/output ports
    - Preview the workflow structure
    """

    def __init__(
        self,
        nodes: List[Dict[str, str]],
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the node naming dialog.

        Args:
            nodes: List of node dictionaries with 'id', 'name', and 'type' keys.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._nodes = nodes
        self._name_edits: Dict[str, QLineEdit] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog's UI components."""
        self.setWindowTitle("Customize Node Names")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        self.setModal(True)

        # Apply dark theme styling
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QLabel {
                color: #D4D4D4;
            }
            QLineEdit {
                background-color: #252526;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                padding: 6px;
            }
            QLineEdit:focus {
                border: 1px solid #0E639C;
            }
            QGroupBox {
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: #D4D4D4;
            }
            QScrollArea {
                background-color: #1E1E1E;
                border: none;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Info label
        info_label = QLabel(
            "Customize the names for each node in the workflow. "
            "These names will be used when the workflow is saved to the library."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #808080; font-size: 10pt;")
        main_layout.addWidget(info_label)

        # Scroll area for nodes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(8)

        # Group nodes by type
        regular_nodes = [n for n in self._nodes if n['type'] not in ['subgraph_input', 'subgraph_output']]
        input_nodes = [n for n in self._nodes if n['type'] == 'subgraph_input']
        output_nodes = [n for n in self._nodes if n['type'] == 'subgraph_output']

        # Regular nodes section
        if regular_nodes:
            nodes_group = QGroupBox("Workflow Nodes")
            nodes_layout = QFormLayout(nodes_group)
            nodes_layout.setContentsMargins(12, 16, 12, 12)
            nodes_layout.setSpacing(12)

            for node in regular_nodes:
                label = QLabel(f"{node['name']} ({node['type']}):")
                label.setStyleSheet("color: #D4D4D4;")

                name_edit = QLineEdit()
                name_edit.setText(node['name'])
                name_edit.setPlaceholderText(node['name'])
                self._name_edits[node['id']] = name_edit

                nodes_layout.addRow(label, name_edit)

            scroll_layout.addWidget(nodes_group)

        # Input ports section
        if input_nodes:
            inputs_group = QGroupBox("Input Ports")
            inputs_layout = QFormLayout(inputs_group)
            inputs_layout.setContentsMargins(12, 16, 12, 12)
            inputs_layout.setSpacing(12)

            for node in input_nodes:
                label = QLabel(f"Input Port:")
                label.setStyleSheet("color: #D4D4D4;")

                name_edit = QLineEdit()
                name_edit.setText(node['name'])
                name_edit.setPlaceholderText(node['name'])
                self._name_edits[node['id']] = name_edit

                inputs_layout.addRow(label, name_edit)

            scroll_layout.addWidget(inputs_group)

        # Output ports section
        if output_nodes:
            outputs_group = QGroupBox("Output Ports")
            outputs_layout = QFormLayout(outputs_group)
            outputs_layout.setContentsMargins(12, 16, 12, 12)
            outputs_layout.setSpacing(12)

            for node in output_nodes:
                label = QLabel(f"Output Port:")
                label.setStyleSheet("color: #D4D4D4;")

                name_edit = QLineEdit()
                name_edit.setText(node['name'])
                name_edit.setPlaceholderText(node['name'])
                self._name_edits[node['id']] = name_edit

                outputs_layout.addRow(label, name_edit)

            scroll_layout.addWidget(outputs_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        # Button bar
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #5A5A5A;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #4A4A4A;
            }
            QPushButton:pressed {
                background-color: #5A5A5A;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #0E639C;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 8px 24px;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:pressed {
                background-color: #0D5289;
            }
        """)
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)

        main_layout.addLayout(button_layout)

    def get_node_names(self) -> Dict[str, str]:
        """
        Get the custom names for all nodes.

        Returns:
            Dictionary mapping node IDs to their custom names.
        """
        return {
            node_id: edit.text().strip() or edit.placeholderText()
            for node_id, edit in self._name_edits.items()
        }
