"""
Node registry for centralized management of available node types.

This module provides a registry that tracks all available node types,
their metadata, and provides factory methods for creating node instances.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Type, TYPE_CHECKING

from visualpython.utils.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from visualpython.nodes.models.base_node import BaseNode, Position


class NodeTypeInfo:
    """
    Information about a registered node type.

    Attributes:
        node_type: Unique identifier for the node type.
        node_class: The class used to instantiate nodes of this type.
        name: Display name for the node type.
        category: Category for organizing in the UI.
        color: Hex color code for the node.
        description: Brief description of the node's functionality.
        icon: Optional icon identifier for the node.
    """

    def __init__(
        self,
        node_type: str,
        node_class: Type[BaseNode],
        name: str,
        category: str,
        color: str,
        description: str = "",
        icon: Optional[str] = None,
    ) -> None:
        self.node_type = node_type
        self.node_class = node_class
        self.name = name
        self.category = category
        self.color = color
        self.description = description
        self.icon = icon

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "node_type": self.node_type,
            "name": self.name,
            "category": self.category,
            "color": self.color,
            "description": self.description,
            "icon": self.icon,
        }


class NodeRegistry:
    """
    Registry for managing available node types.

    The NodeRegistry serves as a centralized location for registering
    node types and creating node instances. It provides:
    - Registration of node types with metadata
    - Factory method for creating node instances
    - Grouping of node types by category
    - Lookup of node type information

    Example:
        >>> registry = NodeRegistry()
        >>> registry.register_default_nodes()
        >>> node = registry.create_node("code", position=Position(100, 100))
    """

    _instance: Optional[NodeRegistry] = None

    def __new__(cls) -> NodeRegistry:
        """Singleton pattern to ensure one global registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the registry if not already initialized."""
        if self._initialized:
            return
        self._initialized = True
        self._node_types: Dict[str, NodeTypeInfo] = {}
        self._categories: Dict[str, List[str]] = {}

    @classmethod
    def get_instance(cls) -> NodeRegistry:
        """Get the singleton instance of the registry."""
        return cls()

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (mainly for testing)."""
        cls._instance = None

    def register(
        self,
        node_class: Type[BaseNode],
        description: str = "",
        icon: Optional[str] = None,
    ) -> None:
        """
        Register a node type with the registry.

        Args:
            node_class: The node class to register.
            description: Brief description of the node's functionality.
            icon: Optional icon identifier for the node.
        """
        node_type = node_class.node_type
        name = getattr(node_class, 'display_name', None) or node_class.node_type.replace("_", " ").title()
        category = node_class.node_category
        color = node_class.node_color

        info = NodeTypeInfo(
            node_type=node_type,
            node_class=node_class,
            name=name,
            category=category,
            color=color,
            description=description,
            icon=icon,
        )

        self._node_types[node_type] = info

        # Update category grouping
        if category not in self._categories:
            self._categories[category] = []
        if node_type not in self._categories[category]:
            self._categories[category].append(node_type)

    def unregister(self, node_type: str) -> bool:
        """
        Unregister a node type from the registry.

        Args:
            node_type: The type identifier to unregister.

        Returns:
            True if the type was unregistered, False if not found.
        """
        if node_type not in self._node_types:
            return False

        info = self._node_types[node_type]
        del self._node_types[node_type]

        # Update category grouping
        if info.category in self._categories:
            if node_type in self._categories[info.category]:
                self._categories[info.category].remove(node_type)
            if not self._categories[info.category]:
                del self._categories[info.category]

        return True

    def get_node_type(self, node_type: str) -> Optional[NodeTypeInfo]:
        """
        Get information about a registered node type.

        Args:
            node_type: The type identifier to look up.

        Returns:
            NodeTypeInfo if found, None otherwise.
        """
        return self._node_types.get(node_type)

    def get_all_node_types(self) -> List[NodeTypeInfo]:
        """Get all registered node types."""
        return list(self._node_types.values())

    def get_categories(self) -> List[str]:
        """Get all category names in sorted order."""
        return sorted(self._categories.keys())

    def get_node_types_in_category(self, category: str) -> List[NodeTypeInfo]:
        """
        Get all node types in a specific category.

        Args:
            category: The category name.

        Returns:
            List of NodeTypeInfo for nodes in the category.
        """
        node_types = self._categories.get(category, [])
        return [self._node_types[nt] for nt in node_types if nt in self._node_types]

    def get_node_types_by_category(self) -> Dict[str, List[NodeTypeInfo]]:
        """
        Get all node types grouped by category.

        Returns:
            Dictionary mapping category names to lists of NodeTypeInfo.
        """
        result: Dict[str, List[NodeTypeInfo]] = {}
        for category in sorted(self._categories.keys()):
            result[category] = self.get_node_types_in_category(category)
        return result

    def create_node(
        self,
        node_type: str,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        **kwargs: Any,
    ) -> Optional[BaseNode]:
        """
        Create a new node instance of the specified type.

        Args:
            node_type: The type identifier for the node to create.
            node_id: Optional unique ID for the node.
            name: Optional display name for the node.
            position: Optional position on the canvas.
            **kwargs: Additional keyword arguments for the node constructor.

        Returns:
            A new node instance, or None if the type is not registered.
        """
        info = self._node_types.get(node_type)
        if info is None:
            return None

        return info.node_class(
            node_id=node_id,
            name=name,
            position=position,
            **kwargs,
        )

    def is_registered(self, node_type: str) -> bool:
        """Check if a node type is registered."""
        return node_type in self._node_types

    def create_node_from_dict(self, data: Dict[str, Any]) -> Optional[BaseNode]:
        """
        Create a node instance from serialized dictionary data.

        Args:
            data: Dictionary containing serialized node data.
                  Must include 'type' key with the node type identifier.

        Returns:
            A new node instance with restored properties, or None if the type
            is not registered or creation fails.
        """
        node_type = data.get("type")
        if not node_type:
            return None

        info = self._node_types.get(node_type)
        if info is None:
            return None

        try:
            # Use the node class's from_dict method if available
            if hasattr(info.node_class, 'from_dict'):
                return info.node_class.from_dict(data)
            else:
                # Fall back to manual creation
                from visualpython.nodes.models.base_node import Position
                position = Position.from_dict(data.get("position", {}))
                return info.node_class(
                    node_id=data.get("id"),
                    name=data.get("name"),
                    position=position,
                )
        except Exception:
            logger.warning("Failed to create node", exc_info=True)
            return None

    def register_default_nodes(self) -> None:
        """Register all built-in node types."""
        from visualpython.nodes.models.breakpoint_node import BreakpointNode
        from visualpython.nodes.models.code_node import CodeNode
        from visualpython.nodes.models.data_aggregation_node import DataAggregationNode
        from visualpython.nodes.models.database_query_node import DatabaseQueryNode
        from visualpython.nodes.models.end_node import EndNode
        from visualpython.nodes.models.file_read_node import FileReadNode
        from visualpython.nodes.models.file_write_node import FileWriteNode
        from visualpython.nodes.models.for_loop_node import ForLoopNode
        from visualpython.nodes.models.get_variable_node import GetVariableNode
        # Case variable nodes
        from visualpython.nodes.models.case_nodes import GetCaseVariableNode, SetCaseVariableNode
        from visualpython.nodes.models.http_request_node import HTTPRequestNode
        from visualpython.nodes.models.if_node import IfNode
        from visualpython.nodes.models.json_parse_node import JSONParseNode
        from visualpython.nodes.models.json_stringify_node import JSONStringifyNode
        from visualpython.nodes.models.input_node import InputNode
        from visualpython.nodes.models.list_append_node import ListAppendNode
        from visualpython.nodes.models.list_filter_node import ListFilterNode
        from visualpython.nodes.models.list_map_node import ListMapNode
        from visualpython.nodes.models.list_reduce_node import ListReduceNode
        from visualpython.nodes.models.merge_node import MergeNode
        from visualpython.nodes.models.print_node import PrintNode
        from visualpython.nodes.models.set_variable_node import SetVariableNode
        from visualpython.nodes.models.start_node import StartNode
        from visualpython.nodes.models.thread_node import ThreadNode
        from visualpython.nodes.models.thread_join_node import ThreadJoinNode
        from visualpython.nodes.models.try_catch_node import TryCatchNode
        from visualpython.nodes.models.while_loop_node import WhileLoopNode
        # Math operation nodes
        from visualpython.nodes.models.add_node import AddNode
        from visualpython.nodes.models.subtract_node import SubtractNode
        from visualpython.nodes.models.multiply_node import MultiplyNode
        from visualpython.nodes.models.divide_node import DivideNode
        from visualpython.nodes.models.modulo_node import ModuloNode
        from visualpython.nodes.models.power_node import PowerNode
        # Regex nodes
        from visualpython.nodes.models.regex_match_node import RegexMatchNode
        from visualpython.nodes.models.regex_replace_node import RegexReplaceNode
        # String operation nodes
        from visualpython.nodes.models.string_concat_node import StringConcatNode
        from visualpython.nodes.models.string_split_node import StringSplitNode
        from visualpython.nodes.models.string_replace_node import StringReplaceNode
        from visualpython.nodes.models.string_format_node import StringFormatNode
        # Subgraph nodes
        from visualpython.nodes.models.subgraph_node import SubgraphNode
        from visualpython.nodes.models.subgraph_input_node import SubgraphInputNode
        from visualpython.nodes.models.subgraph_output_node import SubgraphOutputNode

        self.register(
            StartNode,
            description="Mark the entry point of script execution. Every graph must have exactly one Start node.",
            icon="play",
        )

        self.register(
            CodeNode,
            description="Execute custom Python code with access to inputs and outputs.",
            icon="code",
        )

        self.register(
            IfNode,
            description="Conditional branching based on a boolean condition.",
            icon="branch",
        )

        self.register(
            ForLoopNode,
            description="Iterate over a collection (list, tuple, range, etc.).",
            icon="loop",
        )

        self.register(
            WhileLoopNode,
            description="Iterate while a condition is true. Enables condition-based iteration.",
            icon="loop",
        )

        self.register(
            EndNode,
            description="Mark the end of an execution path.",
            icon="stop",
        )

        self.register(
            GetVariableNode,
            description="Retrieve a value from a named global variable (persists across executions).",
            icon="variable",
        )

        self.register(
            SetVariableNode,
            description="Set a value to a named global variable (persists across executions).",
            icon="variable",
        )

        self.register(
            GetCaseVariableNode,
            description="Retrieve a value from a named variable (per-execution scope).",
            icon="variable",
        )

        self.register(
            SetCaseVariableNode,
            description="Set a value to a named variable (per-execution scope).",
            icon="variable",
        )

        self.register(
            FileReadNode,
            description="Read content from a file with configurable path and encoding.",
            icon="file-read",
        )

        self.register(
            FileWriteNode,
            description="Write content to a file with configurable path and append mode.",
            icon="file-write",
        )

        self.register(
            HTTPRequestNode,
            description="Make HTTP requests with configurable URL, method, headers, and body.",
            icon="network",
        )

        self.register(
            InputNode,
            description="Prompt for user input during execution, storing result in variable.",
            icon="input",
        )

        self.register(
            MergeNode,
            description="Converge multiple execution paths into a single continuation point.",
            icon="merge",
        )

        self.register(
            PrintNode,
            description="Print formatted messages to the console output.",
            icon="print",
        )

        self.register(
            DataAggregationNode,
            description="Combine data from multiple sources using flexible aggregation strategies.",
            icon="aggregate",
        )

        self.register(
            JSONParseNode,
            description="Parse JSON strings into Python objects (dict, list, etc.).",
            icon="json",
        )

        self.register(
            JSONStringifyNode,
            description="Convert Python objects to JSON strings with formatting options.",
            icon="json",
        )

        self.register(
            ThreadNode,
            description="Spawn parallel threads for concurrent execution of downstream nodes.",
            icon="thread",
        )

        self.register(
            ThreadJoinNode,
            description="Wait for thread completion before continuing execution. Enables synchronization points.",
            icon="thread-join",
        )

        self.register(
            TryCatchNode,
            description="Exception handling with try/except paths. Enables error handling in visual scripts.",
            icon="shield",
        )

        self.register(
            BreakpointNode,
            description="Pause execution for debugging. Enables step-through debugging and variable inspection.",
            icon="bug",
        )

        self.register(
            DatabaseQueryNode,
            description="Execute SQL queries against databases with configurable connection strings.",
            icon="database",
        )

        self.register(
            ListAppendNode,
            description="Append one or more elements to a list. Supports single append or extend mode.",
            icon="list-add",
        )

        self.register(
            ListFilterNode,
            description="Filter list elements based on predefined conditions or custom expressions.",
            icon="filter",
        )

        self.register(
            ListMapNode,
            description="Transform each element of a list using predefined or custom transformations.",
            icon="transform",
        )

        self.register(
            ListReduceNode,
            description="Reduce a list to a single value using operations like sum, join, min, max, etc.",
            icon="compress",
        )

        # Math operation nodes
        self.register(
            AddNode,
            description="Add two numbers together. Visual arithmetic without coding.",
            icon="plus",
        )

        self.register(
            SubtractNode,
            description="Subtract one number from another. Visual arithmetic without coding.",
            icon="minus",
        )

        self.register(
            MultiplyNode,
            description="Multiply two numbers together. Visual arithmetic without coding.",
            icon="multiply",
        )

        self.register(
            DivideNode,
            description="Divide one number by another. Supports integer and float division.",
            icon="divide",
        )

        self.register(
            ModuloNode,
            description="Get the remainder of division (modulo operation).",
            icon="percent",
        )

        self.register(
            PowerNode,
            description="Raise a number to a power (exponentiation).",
            icon="superscript",
        )

        # Regex nodes
        self.register(
            RegexMatchNode,
            description="Find pattern matches in text using regular expressions.",
            icon="search",
        )

        self.register(
            RegexReplaceNode,
            description="Find and replace text patterns using regular expressions.",
            icon="replace",
        )

        # String operation nodes
        self.register(
            StringConcatNode,
            description="Concatenate multiple strings together with an optional separator.",
            icon="text",
        )

        self.register(
            StringSplitNode,
            description="Split a string into a list of substrings using a delimiter.",
            icon="split",
        )

        self.register(
            StringReplaceNode,
            description="Find and replace text in strings (simple text, not regex).",
            icon="replace-text",
        )

        self.register(
            StringFormatNode,
            description="Format strings using template placeholders like {0}, {1}, or {name}.",
            icon="template",
        )

        # Subgraph nodes
        self.register(
            SubgraphNode,
            description="A reusable subgraph that can be called like a function. Enables modular script composition.",
            icon="box",
        )

        self.register(
            SubgraphInputNode,
            description="Define an input parameter for a subgraph. Place inside subgraphs to receive external values.",
            icon="arrow-right",
        )

        self.register(
            SubgraphOutputNode,
            description="Define an output parameter for a subgraph. Place inside subgraphs to return values.",
            icon="arrow-left",
        )


# Module-level convenience function
def get_node_registry() -> NodeRegistry:
    """Get the global node registry instance."""
    return NodeRegistry.get_instance()
