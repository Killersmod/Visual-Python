"""
Error reporting module for detailed execution error information.

This module provides classes for capturing and reporting execution errors
with rich context including node location information, execution path,
stack traces, and data flow context to help users debug their visual scripts.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from visualpython.nodes.models.base_node import BaseNode


class ErrorCategory(Enum):
    """Categories of errors that can occur during execution."""

    SYNTAX = auto()
    """Syntax error in code (e.g., invalid Python syntax)."""

    VALIDATION = auto()
    """Validation error (e.g., missing required inputs, invalid configuration)."""

    RUNTIME = auto()
    """Runtime error during code execution (e.g., TypeError, ValueError)."""

    DATA_FLOW = auto()
    """Data flow error (e.g., missing input data, type mismatch between ports)."""

    GRAPH_STRUCTURE = auto()
    """Graph structure error (e.g., cycles, missing start node)."""

    INTERNAL = auto()
    """Internal error in the execution engine."""

    UNKNOWN = auto()
    """Unknown or unclassified error."""


@dataclass
class NodeLocation:
    """
    Location information for a node on the visual canvas.

    This provides the visual position of a node, helping users locate
    the source of an error in their visual script.

    Attributes:
        node_id: Unique identifier of the node.
        node_name: Display name of the node.
        node_type: Type of the node (e.g., 'code', 'if', 'for_loop').
        x: X coordinate on the canvas.
        y: Y coordinate on the canvas.
    """

    node_id: str
    node_name: str
    node_type: str
    x: float = 0.0
    y: float = 0.0

    @classmethod
    def from_node(cls, node: BaseNode) -> NodeLocation:
        """
        Create a NodeLocation from a BaseNode instance.

        Args:
            node: The node to extract location information from.

        Returns:
            NodeLocation with the node's position information.
        """
        return cls(
            node_id=node.id,
            node_name=node.name,
            node_type=node.node_type,
            x=node.position.x,
            y=node.position.y,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert location to dictionary for serialization."""
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_type": self.node_type,
            "x": self.x,
            "y": self.y,
        }


@dataclass
class ErrorReport:
    """
    Comprehensive error report with detailed context information.

    This class captures all relevant information about an execution error,
    including the node location, execution path, stack trace, and data
    context, providing users with everything they need to debug their
    visual scripts.

    Attributes:
        error_id: Unique identifier for this error report.
        category: Classification of the error type.
        message: Human-readable error message.
        location: Location of the node where the error occurred.
        timestamp: When the error occurred.
        original_exception_type: The type name of the original exception.
        stack_trace: Full Python stack trace if available.
        execution_path: List of node IDs executed before the error.
        input_values: Input values that were provided to the failing node.
        suggestions: List of possible fixes or debugging hints.
    """

    error_id: str
    category: ErrorCategory
    message: str
    location: Optional[NodeLocation] = None
    timestamp: datetime = field(default_factory=datetime.now)
    original_exception_type: Optional[str] = None
    stack_trace: Optional[str] = None
    execution_path: List[str] = field(default_factory=list)
    input_values: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)

    @classmethod
    def from_exception(
        cls,
        exception: Exception,
        node: Optional[BaseNode] = None,
        execution_path: Optional[List[str]] = None,
        input_values: Optional[Dict[str, Any]] = None,
    ) -> ErrorReport:
        """
        Create an ErrorReport from an exception.

        Args:
            exception: The exception that was raised.
            node: Optional node where the error occurred.
            execution_path: Optional list of node IDs executed before error.
            input_values: Optional input values for the failing node.

        Returns:
            ErrorReport with detailed error information.
        """
        import uuid

        # Classify the error
        category = cls._classify_exception(exception)

        # Get the error message
        message = str(exception)

        # Get location if node is provided
        location = NodeLocation.from_node(node) if node else None

        # Capture stack trace
        stack_trace = "".join(traceback.format_exception(
            type(exception), exception, exception.__traceback__
        ))

        # Generate suggestions based on error type
        suggestions = cls._generate_suggestions(exception, category)

        return cls(
            error_id=str(uuid.uuid4()),
            category=category,
            message=message,
            location=location,
            original_exception_type=type(exception).__name__,
            stack_trace=stack_trace,
            execution_path=execution_path or [],
            input_values=input_values or {},
            suggestions=suggestions,
        )

    @staticmethod
    def _classify_exception(exception: Exception) -> ErrorCategory:
        """
        Classify an exception into an error category.

        Args:
            exception: The exception to classify.

        Returns:
            The appropriate ErrorCategory for this exception.
        """
        exception_type = type(exception).__name__

        # Syntax errors
        if isinstance(exception, SyntaxError):
            return ErrorCategory.SYNTAX

        # Common runtime errors
        runtime_types = {
            "TypeError", "ValueError", "AttributeError", "KeyError",
            "IndexError", "ZeroDivisionError", "NameError", "RuntimeError",
            "AssertionError", "StopIteration", "RecursionError",
        }
        if exception_type in runtime_types:
            return ErrorCategory.RUNTIME

        # Import errors often indicate missing dependencies
        if isinstance(exception, (ImportError, ModuleNotFoundError)):
            return ErrorCategory.RUNTIME

        # File-related errors
        if isinstance(exception, (FileNotFoundError, PermissionError, IOError)):
            return ErrorCategory.RUNTIME

        # Check for validation-related messages
        error_msg = str(exception).lower()
        if any(word in error_msg for word in ["required", "missing", "invalid", "validation"]):
            return ErrorCategory.VALIDATION

        # Check for data flow issues
        if any(word in error_msg for word in ["input", "output", "port", "connection"]):
            return ErrorCategory.DATA_FLOW

        return ErrorCategory.UNKNOWN

    @staticmethod
    def _generate_suggestions(
        exception: Exception,
        category: ErrorCategory,
    ) -> List[str]:
        """
        Generate debugging suggestions based on the error.

        Args:
            exception: The exception that occurred.
            category: The classified error category.

        Returns:
            List of helpful suggestions for debugging.
        """
        suggestions: List[str] = []
        error_msg = str(exception).lower()

        if category == ErrorCategory.SYNTAX:
            suggestions.append("Check for typos or missing colons, parentheses, or brackets")
            suggestions.append("Ensure proper indentation in your code")
            if "unexpected indent" in error_msg:
                suggestions.append("Remove extra spaces at the beginning of the line")
            if "expected" in error_msg:
                suggestions.append("Review the syntax near the indicated line number")

        elif category == ErrorCategory.RUNTIME:
            if isinstance(exception, TypeError):
                suggestions.append("Check that you're using the correct data types")
                suggestions.append("Verify that input values are the expected type")
                if "nonetype" in error_msg:
                    suggestions.append("An input value may be None - add a check for None values")
            elif isinstance(exception, (KeyError, AttributeError)):
                suggestions.append("Verify the key or attribute name exists")
                suggestions.append("Check for typos in variable or key names")
            elif isinstance(exception, ZeroDivisionError):
                suggestions.append("Add a check to prevent division by zero")
            elif isinstance(exception, NameError):
                suggestions.append("Check that the variable is defined before use")
                suggestions.append("Verify variable names for typos")
            elif isinstance(exception, IndexError):
                suggestions.append("Check that the index is within the list bounds")
                suggestions.append("Verify the list is not empty before accessing elements")

        elif category == ErrorCategory.VALIDATION:
            suggestions.append("Ensure all required inputs are connected")
            suggestions.append("Check that input values match expected formats")

        elif category == ErrorCategory.DATA_FLOW:
            suggestions.append("Verify all required connections are made")
            suggestions.append("Check that upstream nodes are producing expected outputs")

        # Default suggestion
        if not suggestions:
            suggestions.append("Review the error message for specific details")
            suggestions.append("Check the stack trace for the exact location of the error")

        return suggestions

    def to_dict(self) -> Dict[str, Any]:
        """Convert the error report to a dictionary for serialization."""
        return {
            "error_id": self.error_id,
            "category": self.category.name,
            "message": self.message,
            "location": self.location.to_dict() if self.location else None,
            "timestamp": self.timestamp.isoformat(),
            "original_exception_type": self.original_exception_type,
            "stack_trace": self.stack_trace,
            "execution_path": self.execution_path,
            "input_values": self._serialize_input_values(),
            "suggestions": self.suggestions,
        }

    def _serialize_input_values(self) -> Dict[str, Any]:
        """Safely serialize input values, handling non-serializable types."""
        serialized: Dict[str, Any] = {}
        for key, value in self.input_values.items():
            try:
                # Test if value is JSON serializable
                import json
                json.dumps(value)
                serialized[key] = value
            except (TypeError, ValueError):
                # Convert non-serializable values to string representation
                serialized[key] = repr(value)
        return serialized

    def format_user_message(self) -> str:
        """
        Format the error report as a user-friendly message.

        Returns:
            Formatted string suitable for display to the user.
        """
        lines: List[str] = []

        # Error header
        lines.append(f"Error in node: {self.location.node_name if self.location else 'Unknown'}")
        lines.append(f"Type: {self.category.name}")
        lines.append(f"Message: {self.message}")

        # Location info
        if self.location:
            lines.append(f"Node ID: {self.location.node_id}")
            lines.append(f"Node Type: {self.location.node_type}")
            lines.append(f"Position: ({self.location.x:.1f}, {self.location.y:.1f})")

        # Execution path
        if self.execution_path:
            lines.append(f"Execution path: {' -> '.join(self.execution_path[-5:])}")
            if len(self.execution_path) > 5:
                lines.append(f"  (showing last 5 of {len(self.execution_path)} nodes)")

        # Suggestions
        if self.suggestions:
            lines.append("\nSuggestions:")
            for suggestion in self.suggestions:
                lines.append(f"  - {suggestion}")

        return "\n".join(lines)

    def __str__(self) -> str:
        """Get a string representation of the error report."""
        node_info = f" at {self.location.node_name}" if self.location else ""
        return f"ErrorReport({self.category.name}{node_info}: {self.message})"
