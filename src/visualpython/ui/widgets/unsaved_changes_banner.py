"""
Unsaved changes notification banner for VisualPython.

Displays a thin horizontal bar at the top of the central widget area
when there are unsaved changes, with a quick Save button.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)


class UnsavedChangesBanner(QWidget):
    """
    A notification banner indicating unsaved changes.

    Displays a horizontal bar with a warning message and a Save button.
    Hidden by default; shown/hidden by the parent window based on
    the modification state.

    Signals:
        save_clicked: Emitted when the Save button is clicked.
    """

    save_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("unsaved_changes_banner")
        self._setup_ui()
        self.setVisible(False)

    def _setup_ui(self) -> None:
        """Set up the banner layout and widgets."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        self._message_label = QLabel("\u26a0  You have unsaved changes")
        self._message_label.setObjectName("unsaved_banner_message")
        layout.addWidget(self._message_label)

        layout.addStretch()

        self._save_button = QPushButton("Save")
        self._save_button.setObjectName("unsaved_banner_save_button")
        self._save_button.setMaximumWidth(80)
        self._save_button.setToolTip("Save the current project (Ctrl+S)")
        self._save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_button.clicked.connect(self.save_clicked.emit)
        layout.addWidget(self._save_button)

        self.setStyleSheet("""
            QWidget#unsaved_changes_banner {
                background-color: #3E2723;
                border-bottom: 2px solid #FFA726;
            }
            QLabel#unsaved_banner_message {
                color: #FFA726;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#unsaved_banner_save_button {
                background-color: #FFA726;
                color: #1e1e1e;
                border: none;
                border-radius: 3px;
                padding: 4px 16px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton#unsaved_banner_save_button:hover {
                background-color: #FFB74D;
            }
            QPushButton#unsaved_banner_save_button:pressed {
                background-color: #FF9800;
            }
        """)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(36)
