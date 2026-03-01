"""
Undo/Redo manager for tracking and executing commands.

This module provides the UndoRedoManager class that maintains the history
of commands and handles undo/redo operations.
"""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    from visualpython.commands.command import Command


class UndoRedoManager(QObject):
    """
    Manages the undo/redo command history.

    The manager maintains two stacks:
    - Undo stack: Commands that have been executed and can be undone.
    - Redo stack: Commands that have been undone and can be redone.

    When a new command is executed, the redo stack is cleared.

    Signals:
        can_undo_changed: Emitted when undo availability changes.
        can_redo_changed: Emitted when redo availability changes.
        stack_changed: Emitted when either stack changes.
    """

    can_undo_changed = pyqtSignal(bool)
    can_redo_changed = pyqtSignal(bool)
    stack_changed = pyqtSignal()

    # Default maximum number of commands to keep in history
    DEFAULT_MAX_HISTORY = 100

    def __init__(self, max_history: int = DEFAULT_MAX_HISTORY, parent: Optional[QObject] = None) -> None:
        """
        Initialize the undo/redo manager.

        Args:
            max_history: Maximum number of commands to keep in history.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._undo_stack: List[Command] = []
        self._redo_stack: List[Command] = []
        self._max_history = max_history
        self._is_undoing = False
        self._is_redoing = False

    @property
    def can_undo(self) -> bool:
        """Check if there are commands that can be undone."""
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        """Check if there are commands that can be redone."""
        return len(self._redo_stack) > 0

    @property
    def undo_text(self) -> str:
        """Get description text for the next undo action."""
        if self._undo_stack:
            return f"Undo {self._undo_stack[-1].description}"
        return "Undo"

    @property
    def redo_text(self) -> str:
        """Get description text for the next redo action."""
        if self._redo_stack:
            return f"Redo {self._redo_stack[-1].description}"
        return "Redo"

    @property
    def undo_stack_size(self) -> int:
        """Get the number of commands in the undo stack."""
        return len(self._undo_stack)

    @property
    def redo_stack_size(self) -> int:
        """Get the number of commands in the redo stack."""
        return len(self._redo_stack)

    def execute(self, command: Command) -> bool:
        """
        Execute a command and add it to the undo stack.

        Args:
            command: The command to execute.

        Returns:
            True if the command was executed successfully.
        """
        # Don't record commands while undoing/redoing
        if self._is_undoing or self._is_redoing:
            return command.execute()

        # Execute the command
        if not command.execute():
            return False

        # Check if we can merge with the previous command
        if self._undo_stack and self._undo_stack[-1].can_merge(command):
            if self._undo_stack[-1].merge(command):
                self._emit_changes()
                return True

        # Add to undo stack
        self._undo_stack.append(command)

        # Clear redo stack when new command is executed
        old_can_redo = self.can_redo
        self._redo_stack.clear()

        # Enforce max history limit
        while len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)

        # Emit signals
        self._emit_changes()
        if old_can_redo:
            self.can_redo_changed.emit(False)

        return True

    def undo(self) -> bool:
        """
        Undo the most recent command.

        Returns:
            True if undo was successful.
        """
        if not self.can_undo:
            return False

        self._is_undoing = True
        try:
            command = self._undo_stack.pop()
            if command.undo():
                self._redo_stack.append(command)
                self._emit_changes()
                return True
            else:
                # If undo failed, put command back
                self._undo_stack.append(command)
                return False
        finally:
            self._is_undoing = False

    def redo(self) -> bool:
        """
        Redo the most recently undone command.

        Returns:
            True if redo was successful.
        """
        if not self.can_redo:
            return False

        self._is_redoing = True
        try:
            command = self._redo_stack.pop()
            if command.redo():
                self._undo_stack.append(command)
                self._emit_changes()
                return True
            else:
                # If redo failed, put command back
                self._redo_stack.append(command)
                return False
        finally:
            self._is_redoing = False

    def clear(self) -> None:
        """Clear all command history."""
        old_can_undo = self.can_undo
        old_can_redo = self.can_redo

        self._undo_stack.clear()
        self._redo_stack.clear()

        if old_can_undo:
            self.can_undo_changed.emit(False)
        if old_can_redo:
            self.can_redo_changed.emit(False)
        self.stack_changed.emit()

    def _emit_changes(self) -> None:
        """Emit signals for state changes."""
        self.can_undo_changed.emit(self.can_undo)
        self.can_redo_changed.emit(self.can_redo)
        self.stack_changed.emit()

    def get_undo_history(self, count: int = 10) -> List[str]:
        """
        Get descriptions of recent undo-able commands.

        Args:
            count: Maximum number of descriptions to return.

        Returns:
            List of command descriptions, most recent first.
        """
        return [cmd.description for cmd in reversed(self._undo_stack[-count:])]

    def get_redo_history(self, count: int = 10) -> List[str]:
        """
        Get descriptions of redo-able commands.

        Args:
            count: Maximum number of descriptions to return.

        Returns:
            List of command descriptions, most recent first.
        """
        return [cmd.description for cmd in reversed(self._redo_stack[-count:])]

    def begin_macro(self, description: str = "Multiple Actions") -> None:
        """
        Begin recording a macro (composite command).

        All commands executed after this call will be grouped together
        until end_macro() is called.

        Args:
            description: Description for the grouped commands.
        """
        from visualpython.commands.command import CompositeCommand
        # We need to track the current graph - this will be set by the first command
        self._macro: Optional[CompositeCommand] = None
        self._macro_description = description
        self._recording_macro = True

    def end_macro(self) -> None:
        """
        End recording a macro and add it as a single command.
        """
        if hasattr(self, '_recording_macro') and self._recording_macro:
            self._recording_macro = False
            if hasattr(self, '_macro') and self._macro and not self._macro.is_empty:
                self._undo_stack.append(self._macro)
                self._redo_stack.clear()
                self._emit_changes()
            self._macro = None

    @property
    def is_recording_macro(self) -> bool:
        """Check if currently recording a macro."""
        return getattr(self, '_recording_macro', False)
