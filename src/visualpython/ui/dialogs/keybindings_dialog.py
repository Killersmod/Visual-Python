"""
Keybindings editor dialog for customizing keyboard shortcuts.

Provides a table-based UI where users can view and reassign keyboard
shortcuts for all application actions. Changes persist across restarts.
"""

from __future__ import annotations

from typing import Dict, Optional

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLabel,
    QMessageBox,
    QAbstractItemView,
    QWidget,
    QLineEdit,
)

from visualpython.core.keybindings_manager import (
    KeybindingsManager,
    ACTION_DISPLAY_NAMES,
    ACTION_CATEGORIES,
    DEFAULT_KEYBINDINGS,
)


class ShortcutEditWidget(QLineEdit):
    """
    A line edit that captures key sequences for shortcut editing.

    When focused, captures the next key combination the user presses
    and displays it as a shortcut string.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Press a key combination...")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._captured_sequence = ""

    @property
    def captured_sequence(self) -> str:
        return self._captured_sequence

    def set_sequence(self, seq: str) -> None:
        self._captured_sequence = seq
        self.setText(seq)

    def clear_sequence(self) -> None:
        self._captured_sequence = ""
        self.clear()

    def keyPressEvent(self, event) -> None:
        key = event.key()

        # Ignore bare modifier keys
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return

        # Build the key sequence
        modifiers = event.modifiers()
        key_combo = int(modifiers) | key
        sequence = QKeySequence(key_combo)
        text = sequence.toString()

        if text:
            self._captured_sequence = text
            self.setText(text)


class KeybindingsDialog(QDialog):
    """
    Dialog for viewing and editing keyboard shortcuts.

    Displays all actions grouped by category in a table. Users can
    click on a shortcut cell and press a new key combination to reassign it.
    """

    def __init__(
        self,
        manager: KeybindingsManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._pending_changes: Dict[str, str] = {}

        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(550, 500)
        self.resize(600, 600)

        self._setup_ui()
        self._populate_table()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Click a shortcut, then press a new key combination to reassign it.")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Shortcut capture widget
        capture_layout = QHBoxLayout()
        capture_label = QLabel("New shortcut:")
        self._shortcut_edit = ShortcutEditWidget()
        self._shortcut_edit.setFixedWidth(200)
        self._assign_btn = QPushButton("Assign")
        self._assign_btn.setEnabled(False)
        self._assign_btn.clicked.connect(self._on_assign)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setEnabled(False)
        self._clear_btn.clicked.connect(self._on_clear_shortcut)
        capture_layout.addWidget(capture_label)
        capture_layout.addWidget(self._shortcut_edit)
        capture_layout.addWidget(self._assign_btn)
        capture_layout.addWidget(self._clear_btn)
        capture_layout.addStretch()
        layout.addLayout(capture_layout)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Action", "Shortcut", "Default"])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.currentCellChanged.connect(self._on_cell_changed)
        layout.addWidget(self._table)

        # Buttons
        btn_layout = QHBoxLayout()

        reset_btn = QPushButton("Reset Selected")
        reset_btn.setToolTip("Reset selected action to its default shortcut")
        reset_btn.clicked.connect(self._on_reset_selected)
        btn_layout.addWidget(reset_btn)

        reset_all_btn = QPushButton("Reset All")
        reset_all_btn.setToolTip("Reset all shortcuts to defaults")
        reset_all_btn.clicked.connect(self._on_reset_all)
        btn_layout.addWidget(reset_all_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Save")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

    def _populate_table(self) -> None:
        """Fill the table with all keybindings grouped by category."""
        bindings = self._manager.get_all()

        # Count total rows (categories + actions)
        total_rows = 0
        for category, action_ids in ACTION_CATEGORIES.items():
            total_rows += 1  # category header
            total_rows += len(action_ids)

        self._table.setRowCount(total_rows)
        self._action_id_for_row: Dict[int, str] = {}

        row = 0
        for category, action_ids in ACTION_CATEGORIES.items():
            # Category header row
            cat_item = QTableWidgetItem(category)
            cat_item.setFlags(Qt.ItemFlag.NoItemFlags)
            font = cat_item.font()
            font.setBold(True)
            cat_item.setFont(font)
            self._table.setItem(row, 0, cat_item)
            self._table.setItem(row, 1, QTableWidgetItem(""))
            self._table.setItem(row, 2, QTableWidgetItem(""))
            self._table.setSpan(row, 0, 1, 3)
            row += 1

            # Action rows
            for action_id in action_ids:
                display_name = ACTION_DISPLAY_NAMES.get(action_id, action_id)
                current = self._pending_changes.get(
                    action_id, bindings.get(action_id, "")
                )
                default = DEFAULT_KEYBINDINGS.get(action_id, "")

                name_item = QTableWidgetItem(f"    {display_name}")
                name_item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                )

                shortcut_item = QTableWidgetItem(current)
                shortcut_item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                )
                shortcut_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                default_item = QTableWidgetItem(default)
                default_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                default_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # Highlight modified shortcuts
                if current != default:
                    shortcut_item.setForeground(
                        shortcut_item.foreground().color()
                    )
                    font = shortcut_item.font()
                    font.setBold(True)
                    shortcut_item.setFont(font)

                self._table.setItem(row, 0, name_item)
                self._table.setItem(row, 1, shortcut_item)
                self._table.setItem(row, 2, default_item)
                self._action_id_for_row[row] = action_id
                row += 1

    def _on_cell_changed(self, row: int, col: int, prev_row: int, prev_col: int) -> None:
        action_id = self._action_id_for_row.get(row)
        if action_id:
            self._assign_btn.setEnabled(True)
            self._clear_btn.setEnabled(True)
            # Show current shortcut in the capture widget
            current = self._pending_changes.get(
                action_id, self._manager.get(action_id)
            )
            self._shortcut_edit.set_sequence(current)
        else:
            self._assign_btn.setEnabled(False)
            self._clear_btn.setEnabled(False)
            self._shortcut_edit.clear_sequence()

    def _on_assign(self) -> None:
        row = self._table.currentRow()
        action_id = self._action_id_for_row.get(row)
        if not action_id:
            return

        new_shortcut = self._shortcut_edit.captured_sequence
        if not new_shortcut:
            return

        # Check for conflicts
        conflict_action = self._find_conflict(action_id, new_shortcut)
        if conflict_action:
            conflict_name = ACTION_DISPLAY_NAMES.get(
                conflict_action, conflict_action
            )
            reply = QMessageBox.question(
                self,
                "Shortcut Conflict",
                f'"{new_shortcut}" is already assigned to "{conflict_name}".\n\n'
                f"Reassign it anyway? The conflicting shortcut will be cleared.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            # Clear the conflicting binding
            self._pending_changes[conflict_action] = ""
            self._update_row_for_action(conflict_action)

        self._pending_changes[action_id] = new_shortcut
        self._update_row_for_action(action_id)

    def _on_clear_shortcut(self) -> None:
        row = self._table.currentRow()
        action_id = self._action_id_for_row.get(row)
        if not action_id:
            return

        self._pending_changes[action_id] = ""
        self._shortcut_edit.clear_sequence()
        self._update_row_for_action(action_id)

    def _find_conflict(self, action_id: str, shortcut: str) -> Optional[str]:
        """Find another action that already uses this shortcut."""
        for aid, sc in self._pending_changes.items():
            if aid != action_id and sc == shortcut:
                return aid

        bindings = self._manager.get_all()
        for aid, sc in bindings.items():
            if aid != action_id and aid not in self._pending_changes and sc == shortcut:
                return aid

        return None

    def _update_row_for_action(self, action_id: str) -> None:
        """Update the table row for a given action after a change."""
        for row, aid in self._action_id_for_row.items():
            if aid == action_id:
                new_val = self._pending_changes.get(
                    action_id, self._manager.get(action_id)
                )
                default = DEFAULT_KEYBINDINGS.get(action_id, "")
                item = self._table.item(row, 1)
                if item:
                    item.setText(new_val)
                    font = item.font()
                    font.setBold(new_val != default)
                    item.setFont(font)
                break

    def _on_reset_selected(self) -> None:
        row = self._table.currentRow()
        action_id = self._action_id_for_row.get(row)
        if not action_id:
            return

        default = DEFAULT_KEYBINDINGS.get(action_id, "")
        self._pending_changes[action_id] = default
        self._shortcut_edit.set_sequence(default)
        self._update_row_for_action(action_id)

    def _on_reset_all(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset All Shortcuts",
            "Reset all keyboard shortcuts to their defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for action_id in DEFAULT_KEYBINDINGS:
            self._pending_changes[action_id] = DEFAULT_KEYBINDINGS[action_id]

        # Refresh entire table
        self._table.setRowCount(0)
        self._populate_table()

    def _on_save(self) -> None:
        """Apply changes and save."""
        for action_id, shortcut in self._pending_changes.items():
            self._manager.set(action_id, shortcut)
        self._manager.save()
        self.accept()
