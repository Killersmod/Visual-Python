"""
Library export dialog for saving selected nodes as a reusable library.

This module provides a dialog for users to configure library metadata
(name, description, author, tags) when exporting a collection of nodes.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QFormLayout,
    QWidget,
    QFileDialog,
    QGroupBox,
)

from visualpython.serialization.library_serializer import LibraryMetadata


class LibraryExportDialog(QDialog):
    """
    A dialog for configuring library export options.

    This dialog allows users to:
    - Set the library name
    - Provide a description
    - Add author information
    - Add tags for categorization
    - Select the output file path
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the library export dialog.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._file_path: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog's UI components."""
        self.setWindowTitle("Export as Node Library")
        self.setMinimumWidth(500)
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
            QLineEdit, QTextEdit {
                background-color: #252526;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                padding: 6px;
            }
            QLineEdit:focus, QTextEdit:focus {
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
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Info label
        info_label = QLabel(
            "Export the selected nodes as a reusable library that can be imported "
            "into other projects."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #808080; font-size: 10pt;")
        main_layout.addWidget(info_label)

        # Metadata group
        metadata_group = QGroupBox("Library Information")
        metadata_layout = QFormLayout(metadata_group)
        metadata_layout.setContentsMargins(12, 16, 12, 12)
        metadata_layout.setSpacing(12)

        # Name field
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("My Node Library")
        metadata_layout.addRow("Name:", self._name_edit)

        # Description field
        self._description_edit = QTextEdit()
        self._description_edit.setPlaceholderText("Describe what this library contains...")
        self._description_edit.setMaximumHeight(80)
        metadata_layout.addRow("Description:", self._description_edit)

        # Author field
        self._author_edit = QLineEdit()
        self._author_edit.setPlaceholderText("Your name")
        metadata_layout.addRow("Author:", self._author_edit)

        # Tags field
        self._tags_edit = QLineEdit()
        self._tags_edit.setPlaceholderText("utilities, helpers, io (comma-separated)")
        metadata_layout.addRow("Tags:", self._tags_edit)

        main_layout.addWidget(metadata_group)

        # File path group
        file_group = QGroupBox("Output File")
        file_layout = QHBoxLayout(file_group)
        file_layout.setContentsMargins(12, 16, 12, 12)

        self._file_path_edit = QLineEdit()
        self._file_path_edit.setPlaceholderText("Select output file...")
        self._file_path_edit.setReadOnly(True)
        file_layout.addWidget(self._file_path_edit)

        browse_button = QPushButton("Browse...")
        browse_button.setStyleSheet("""
            QPushButton {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #5A5A5A;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #4A4A4A;
            }
            QPushButton:pressed {
                background-color: #5A5A5A;
            }
        """)
        browse_button.clicked.connect(self._on_browse)
        file_layout.addWidget(browse_button)

        main_layout.addWidget(file_group)

        # Stretch
        main_layout.addStretch()

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

        self._export_button = QPushButton("Export")
        self._export_button.setDefault(True)
        self._export_button.setEnabled(False)
        self._export_button.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #3C3C3C;
                color: #808080;
            }
        """)
        self._export_button.clicked.connect(self.accept)
        button_layout.addWidget(self._export_button)

        main_layout.addLayout(button_layout)

        # Connect signals
        self._file_path_edit.textChanged.connect(self._update_export_button)

    def _on_browse(self) -> None:
        """Handle Browse button click."""
        # Suggest a default filename based on library name
        default_name = self._name_edit.text().strip()
        if not default_name:
            default_name = "my_library"
        # Clean up filename
        default_name = "".join(c for c in default_name if c.isalnum() or c in "_ -").strip()
        default_name = default_name.replace(" ", "_")
        default_name += ".vnl"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Node Library",
            default_name,
            "VisualPython Libraries (*.vnl);;JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            self._file_path = file_path
            self._file_path_edit.setText(file_path)

    def _update_export_button(self) -> None:
        """Update the Export button enabled state."""
        self._export_button.setEnabled(bool(self._file_path_edit.text().strip()))

    def get_metadata(self) -> LibraryMetadata:
        """
        Get the library metadata from the dialog.

        Returns:
            LibraryMetadata with user-provided values.
        """
        name = self._name_edit.text().strip()
        if not name:
            name = "Untitled Library"

        description = self._description_edit.toPlainText().strip()
        author = self._author_edit.text().strip()

        # Parse tags
        tags_text = self._tags_edit.text().strip()
        if tags_text:
            tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]
        else:
            tags = []

        return LibraryMetadata(
            name=name,
            description=description,
            author=author,
            tags=tags,
        )

    def get_file_path(self) -> str:
        """
        Get the selected file path.

        Returns:
            The file path string.
        """
        return self._file_path

    def set_suggested_name(self, name: str) -> None:
        """
        Set a suggested name for the library.

        Args:
            name: The suggested name.
        """
        self._name_edit.setText(name)
