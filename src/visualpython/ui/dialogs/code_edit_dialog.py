"""
Code edit dialog for editing Python code in Code nodes.

This module provides a modal dialog for editing Python code with syntax highlighting,
allowing users to edit code in Code node instances from the graph canvas or edit
default code templates from the nodes panel.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
    QFrame,
    QMessageBox,
)

from visualpython.ui.widgets.code_editor import CodeEditorWidget


class CodeEditDialog(QDialog):
    """
    A modal dialog for editing Python code in Code nodes.

    This dialog provides:
    - A header showing the node name/context
    - A full-featured code editor with Python syntax highlighting
    - Real-time syntax validation with error indicators
    - Autocomplete for Python keywords, builtins, and variables
    - Line numbers and current line highlighting
    - Save and Cancel buttons with keyboard shortcuts
    - Dark theme styling consistent with the application
    - Unsaved changes detection with confirmation dialog

    The dialog can be used for:
    - Editing code in existing Code node instances on the graph
    - Editing default code templates for new Code nodes from the nodes panel

    When the user attempts to close the dialog (via Cancel button, Escape key,
    or window X button) with unsaved changes, a confirmation dialog is shown
    with options to Save, Discard, or Cancel the close operation.
    """

    def __init__(
        self,
        title: str = "Edit Code",
        initial_code: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Initialize the code edit dialog.

        Args:
            title: The dialog title (e.g., "Edit Code - MyNode").
            initial_code: The initial code to display in the editor.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._initial_code = initial_code
        self._title = title
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog's UI components."""
        self.setWindowTitle(self._title)
        self.setMinimumSize(700, 500)
        self.resize(900, 650)
        self.setModal(True)

        # Apply dark theme styling consistent with other dialogs
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QLabel {
                color: #D4D4D4;
            }
            QFrame#header_frame {
                background-color: #252526;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
                padding: 8px;
            }
            QFrame#editor_container {
                background-color: #1E1E1E;
                border: 1px solid #3C3C3C;
                border-radius: 4px;
            }
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
                selection-background-color: #264F78;
                selection-color: #FFFFFF;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header section with title and context info
        header_frame = QFrame()
        header_frame.setObjectName("header_frame")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(4)

        # Title label
        self._title_label = QLabel(self._title)
        self._title_label.setStyleSheet("""
            QLabel {
                font-size: 12pt;
                font-weight: bold;
                color: #FFFFFF;
            }
        """)
        header_layout.addWidget(self._title_label)

        # Info/hint label
        info_label = QLabel(
            "Edit the Python code below. Use Ctrl+S to save or Escape to cancel."
        )
        info_label.setStyleSheet("color: #808080; font-size: 9pt;")
        header_layout.addWidget(info_label)

        main_layout.addWidget(header_frame)

        # Editor container with CodeEditorWidget
        self._editor_container = QFrame()
        self._editor_container.setObjectName("editor_container")
        self._editor_layout = QVBoxLayout(self._editor_container)
        self._editor_layout.setContentsMargins(1, 1, 1, 1)
        self._editor_layout.setSpacing(0)

        # Create the code editor widget with syntax highlighting and validation
        self._code_editor = CodeEditorWidget(
            parent=self._editor_container,
            enable_validation=True,
        )
        self._code_editor.setPlaceholderText("# Enter Python code here...")
        self._code_editor.setMinimumHeight(300)

        # Apply dark theme styling to the code editor
        self._code_editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
                selection-background-color: #264F78;
                selection-color: #FFFFFF;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 10pt;
            }
        """)

        # Set the initial code
        if self._initial_code:
            self._code_editor.setPlainText(self._initial_code)

        self._editor_layout.addWidget(self._code_editor)

        main_layout.addWidget(self._editor_container, 1)  # Stretch factor 1

        # Button bar
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # Cancel button
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setToolTip("Discard changes and close (Escape)")
        self._cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #5A5A5A;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 10pt;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #4A4A4A;
            }
            QPushButton:pressed {
                background-color: #5A5A5A;
            }
        """)
        self._cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self._cancel_button)

        # Save button
        self._save_button = QPushButton("Save")
        self._save_button.setDefault(True)
        self._save_button.setToolTip("Save changes and close (Ctrl+S)")
        self._save_button.setStyleSheet("""
            QPushButton {
                background-color: #0E639C;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 8px 24px;
                font-size: 10pt;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:pressed {
                background-color: #0D5289;
            }
        """)
        self._save_button.clicked.connect(self.accept)
        button_layout.addWidget(self._save_button)

        main_layout.addLayout(button_layout)

        # Set up keyboard shortcuts
        self._setup_shortcuts()

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts for the dialog."""
        # Ctrl+S to save and close
        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(self.accept)

        # Escape to cancel and close (already handled by QDialog by default,
        # but we explicitly add it for clarity and to ensure consistent behavior)
        cancel_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        cancel_shortcut.activated.connect(self._handle_cancel)

    def has_unsaved_changes(self) -> bool:
        """
        Check if the code has been modified since the dialog was opened.

        Returns:
            True if there are unsaved changes, False otherwise.
        """
        return self._code_editor.toPlainText() != self._initial_code

    def mark_as_saved(self) -> None:
        """
        Mark the current code as saved.

        This resets the baseline used for unsaved changes detection to the
        current editor content. Call this after successfully saving the code
        to prevent the unsaved changes dialog from appearing.
        """
        self._initial_code = self._code_editor.toPlainText()

    def _show_unsaved_changes_dialog(self) -> QMessageBox.StandardButton:
        """
        Show a confirmation dialog when there are unsaved changes.

        Returns:
            The button that was clicked (Save, Discard, or Cancel).
        """
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Unsaved Changes")
        msg_box.setText("You have unsaved changes.")
        msg_box.setInformativeText("Do you want to save your changes before closing?")
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Save)
        msg_box.setIcon(QMessageBox.Icon.Warning)

        # Apply dark theme styling to the message box
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #1E1E1E;
                color: #D4D4D4;
            }
            QMessageBox QLabel {
                color: #D4D4D4;
            }
            QPushButton {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #5A5A5A;
                border-radius: 4px;
                padding: 6px 14px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #4A4A4A;
            }
            QPushButton:pressed {
                background-color: #5A5A5A;
            }
            QPushButton:default {
                background-color: #0E639C;
                color: #FFFFFF;
                border: none;
            }
            QPushButton:default:hover {
                background-color: #1177BB;
            }
        """)

        return QMessageBox.StandardButton(msg_box.exec())

    def _handle_cancel(self) -> None:
        """Handle the cancel action with unsaved changes check."""
        self.reject()

    def reject(self) -> None:
        """
        Override reject to show confirmation dialog if there are unsaved changes.

        This is called when the user clicks Cancel or presses Escape.
        """
        if self.has_unsaved_changes():
            result = self._show_unsaved_changes_dialog()

            if result == QMessageBox.StandardButton.Save:
                # Save and close
                self.accept()
            elif result == QMessageBox.StandardButton.Discard:
                # Discard changes and close
                super().reject()
            # else Cancel - do nothing, keep dialog open
        else:
            # No changes, just close
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Override closeEvent to show confirmation dialog if there are unsaved changes.

        This is called when the user clicks the X button on the window.

        Args:
            event: The close event to handle.
        """
        if self.has_unsaved_changes():
            result = self._show_unsaved_changes_dialog()

            if result == QMessageBox.StandardButton.Save:
                # Save and close
                event.accept()
                self.accept()
            elif result == QMessageBox.StandardButton.Discard:
                # Discard changes and close
                event.accept()
                super().reject()
            else:
                # Cancel - keep dialog open
                event.ignore()
        else:
            # No changes, just close
            event.accept()

    def set_title(self, title: str) -> None:
        """
        Update the dialog title.

        Args:
            title: The new title to display.
        """
        self._title = title
        self.setWindowTitle(title)
        self._title_label.setText(title)

    def get_code(self) -> str:
        """
        Get the current code from the editor.

        Returns:
            The current code in the editor.
        """
        return self._code_editor.toPlainText()

    def set_code(self, code: str) -> None:
        """
        Set the code in the editor.

        Args:
            code: The code to display in the editor.
        """
        self._initial_code = code
        self._code_editor.setPlainText(code)

    @property
    def code_editor(self) -> CodeEditorWidget:
        """
        Get the underlying code editor widget.

        Returns:
            The CodeEditorWidget instance used in this dialog.
        """
        return self._code_editor

    def is_code_valid(self) -> bool:
        """
        Check if the current code has no syntax errors.

        Returns:
            True if the code is valid, False otherwise.
        """
        return self._code_editor.is_valid

    def validate_code(self) -> bool:
        """
        Force immediate validation and return the result.

        Returns:
            True if the code is valid, False otherwise.
        """
        return self._code_editor.validate_now()

    @staticmethod
    def edit_code(
        parent: Optional[QWidget],
        title: str = "Edit Code",
        initial_code: str = "",
    ) -> tuple[bool, str]:
        """
        Static convenience method to open the code editor dialog.

        Args:
            parent: Parent widget for the dialog.
            title: The dialog title.
            initial_code: The initial code to display.

        Returns:
            A tuple of (accepted, code) where accepted is True if the user
            clicked Save, and code is the final code content.
        """
        dialog = CodeEditDialog(title=title, initial_code=initial_code, parent=parent)
        result = dialog.exec()
        accepted = result == QDialog.DialogCode.Accepted
        return accepted, dialog.get_code()
