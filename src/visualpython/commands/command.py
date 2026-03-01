"""
Base command class for the command pattern implementation.

This module provides the abstract Command base class that all graph operations
must inherit from to support undo/redo functionality.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph


class Command(ABC):
    """
    Abstract base class for all undoable commands.

    Commands encapsulate a single operation that can be executed, undone, and redone.
    Each command must capture all necessary state to reverse its operation.

    Subclasses must implement execute(), undo(), and description property.
    """

    def __init__(self, graph: Graph) -> None:
        """
        Initialize the command.

        Args:
            graph: The graph model this command operates on.
        """
        self._graph = graph
        self._executed = False

    @abstractmethod
    def execute(self) -> bool:
        """
        Execute the command.

        Returns:
            True if the command was executed successfully, False otherwise.
        """
        pass

    @abstractmethod
    def undo(self) -> bool:
        """
        Undo the command, reversing its effects.

        Returns:
            True if the undo was successful, False otherwise.
        """
        pass

    def redo(self) -> bool:
        """
        Redo the command after it has been undone.

        By default, this simply re-executes the command.
        Subclasses can override for optimized redo behavior.

        Returns:
            True if the redo was successful, False otherwise.
        """
        return self.execute()

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Get a human-readable description of the command.

        Returns:
            A short description suitable for display in menus (e.g., "Add Node").
        """
        pass

    @property
    def is_executed(self) -> bool:
        """Check if the command has been executed."""
        return self._executed

    def can_merge(self, other: "Command") -> bool:
        """
        Check if this command can be merged with another command.

        Command merging is useful for combining multiple small operations
        (like typing characters or dragging) into a single undoable action.

        Args:
            other: The command to potentially merge with.

        Returns:
            True if the commands can be merged, False otherwise.
        """
        return False

    def merge(self, other: "Command") -> bool:
        """
        Merge another command into this one.

        Args:
            other: The command to merge into this one.

        Returns:
            True if the merge was successful, False otherwise.
        """
        return False


class CompositeCommand(Command):
    """
    A command that groups multiple commands into a single undoable operation.

    Use this to combine multiple related operations (like deleting multiple nodes)
    into a single undo/redo step.
    """

    def __init__(self, graph: Graph, description: str = "Multiple Actions") -> None:
        """
        Initialize the composite command.

        Args:
            graph: The graph model this command operates on.
            description: Human-readable description of the combined operation.
        """
        super().__init__(graph)
        self._commands: List[Command] = []
        self._description = description

    def add_command(self, command: Command) -> None:
        """
        Add a command to the composite.

        Args:
            command: The command to add.
        """
        self._commands.append(command)

    @property
    def commands(self) -> List[Command]:
        """Get the list of commands in this composite."""
        return self._commands.copy()

    @property
    def is_empty(self) -> bool:
        """Check if the composite has no commands."""
        return len(self._commands) == 0

    def execute(self) -> bool:
        """
        Execute all commands in order.

        Returns:
            True if all commands were executed successfully.
        """
        for command in self._commands:
            if not command.execute():
                # Rollback executed commands on failure
                for executed_cmd in reversed(self._commands[:self._commands.index(command)]):
                    executed_cmd.undo()
                return False
        self._executed = True
        return True

    def undo(self) -> bool:
        """
        Undo all commands in reverse order.

        Returns:
            True if all undos were successful.
        """
        for command in reversed(self._commands):
            if not command.undo():
                return False
        self._executed = False
        return True

    def redo(self) -> bool:
        """
        Redo all commands in order.

        Returns:
            True if all redos were successful.
        """
        for command in self._commands:
            if not command.redo():
                return False
        self._executed = True
        return True

    @property
    def description(self) -> str:
        """Get the description of this composite command."""
        return self._description
