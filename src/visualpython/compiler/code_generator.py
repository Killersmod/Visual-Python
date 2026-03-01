"""
Python code generator for converting visual node graphs to executable Python scripts.

This module provides the core CodeGenerator class that traverses a graph of nodes
and generates equivalent Python source code. It handles control flow structures,
variable management, and proper code indentation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from visualpython.compiler.ast_validator import validate_generated_code
from visualpython.compiler.variable_scope import (
    VariableScopeManager,
    ScopeType,
    VariableInfo,
)

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph
    from visualpython.nodes.models.base_node import BaseNode
    from visualpython.nodes.models.port import Connection


class GenerationError(Exception):
    """Exception raised when code generation fails."""

    def __init__(self, message: str, node_id: Optional[str] = None) -> None:
        """
        Initialize a generation error.

        Args:
            message: Error description.
            node_id: Optional ID of the node that caused the error.
        """
        self.node_id = node_id
        super().__init__(message)


class CodeContext(Enum):
    """Represents the current code generation context."""

    GLOBAL = auto()
    """Top-level script code."""

    FUNCTION = auto()
    """Inside a function definition."""

    IF_BRANCH = auto()
    """Inside an if/else branch."""

    LOOP_BODY = auto()
    """Inside a loop body."""


@dataclass
class IndentationManager:
    """Manages code indentation levels."""

    indent_string: str = "    "
    """The string used for one level of indentation (default: 4 spaces)."""

    _current_level: int = 0
    """Current indentation level."""

    @property
    def current_level(self) -> int:
        """Get the current indentation level."""
        return self._current_level

    def indent(self) -> None:
        """Increase indentation by one level."""
        self._current_level += 1

    def dedent(self) -> None:
        """Decrease indentation by one level."""
        if self._current_level > 0:
            self._current_level -= 1

    def get_indent(self) -> str:
        """Get the current indentation string."""
        return self.indent_string * self._current_level

    def indent_code(self, code: str) -> str:
        """
        Apply current indentation to a code block.

        Args:
            code: The code to indent.

        Returns:
            The indented code.
        """
        if not code:
            return code

        indent = self.get_indent()
        lines = code.split("\n")
        indented_lines = [f"{indent}{line}" if line.strip() else line for line in lines]
        return "\n".join(indented_lines)

    def reset(self) -> None:
        """Reset indentation to zero."""
        self._current_level = 0


@dataclass
class GenerationContext:
    """
    Holds state information during code generation.

    This context is passed through the generation process to track:
    - Variable declarations and assignments
    - Current scope and indentation
    - Generated code sections
    - Node processing state
    - Variable scope management for safe variable accessibility
    """

    indentation: IndentationManager = field(default_factory=IndentationManager)
    """Manages code indentation."""

    context_stack: List[CodeContext] = field(default_factory=list)
    """Stack of code contexts for nested structures."""

    generated_variables: Dict[str, str] = field(default_factory=dict)
    """Maps node output port keys to generated variable names."""

    processed_nodes: Set[str] = field(default_factory=set)
    """Set of node IDs that have been processed."""

    code_lines: List[str] = field(default_factory=list)
    """Accumulated generated code lines."""

    imports: Set[str] = field(default_factory=set)
    """Required import statements."""

    errors: List[str] = field(default_factory=list)
    """Any errors encountered during generation."""

    warnings: List[str] = field(default_factory=list)
    """Warnings about potential issues (e.g., conditional variable access)."""

    _variable_counter: int = 0
    """Counter for generating unique variable names."""

    _scope_manager: Optional[VariableScopeManager] = field(default=None)
    """Manages variable scopes for safe code generation."""

    thread_variables: Dict[str, str] = field(default_factory=dict)
    """Maps thread node IDs to their threads list variable names for join synchronization."""

    subgraph_inline_stack: Set[str] = field(default_factory=set)
    """Tracks subgraph file paths currently being inlined, to detect circular references."""

    def __post_init__(self) -> None:
        """Initialize the scope manager after dataclass init."""
        if self._scope_manager is None:
            self._scope_manager = VariableScopeManager()

    @property
    def scope_manager(self) -> VariableScopeManager:
        """Get the variable scope manager."""
        if self._scope_manager is None:
            self._scope_manager = VariableScopeManager()
        return self._scope_manager

    def push_context(self, context: CodeContext) -> None:
        """Push a new code context onto the stack."""
        self.context_stack.append(context)

    def pop_context(self) -> Optional[CodeContext]:
        """Pop the current code context from the stack."""
        if self.context_stack:
            return self.context_stack.pop()
        return None

    @property
    def current_context(self) -> CodeContext:
        """Get the current code context."""
        if self.context_stack:
            return self.context_stack[-1]
        return CodeContext.GLOBAL

    def enter_scope(
        self,
        context: CodeContext,
        branch_name: Optional[str] = None,
    ) -> None:
        """
        Enter a new scope for variable tracking.

        This method combines pushing the code context and entering a scope
        for variable management.

        Args:
            context: The code context being entered.
            branch_name: Optional name for conditional branches (e.g., 'true_branch').
        """
        self.push_context(context)

        # Map CodeContext to ScopeType
        scope_type_map = {
            CodeContext.GLOBAL: ScopeType.GLOBAL,
            CodeContext.FUNCTION: ScopeType.FUNCTION,
            CodeContext.IF_BRANCH: ScopeType.IF_BRANCH,
            CodeContext.LOOP_BODY: ScopeType.LOOP_BODY,
        }
        scope_type = scope_type_map.get(context, ScopeType.GLOBAL)
        self.scope_manager.enter_scope(scope_type, branch_name)

    def exit_scope(self) -> Optional[CodeContext]:
        """
        Exit the current scope.

        This method combines popping the code context and exiting the scope
        for variable management.

        Returns:
            The code context that was exited.
        """
        self.scope_manager.exit_scope()
        return self.pop_context()

    def generate_variable_name(self, prefix: str = "var") -> str:
        """
        Generate a unique variable name.

        Args:
            prefix: Prefix for the variable name.

        Returns:
            A unique variable name.
        """
        self._variable_counter += 1
        return f"{prefix}_{self._variable_counter}"

    def add_line(self, line: str) -> None:
        """
        Add an indented line of code.

        Args:
            line: The line of code to add.
        """
        if line.strip():
            self.code_lines.append(self.indentation.indent_code(line))
        else:
            self.code_lines.append("")

    def add_lines(self, lines: List[str]) -> None:
        """
        Add multiple indented lines of code.

        Args:
            lines: The lines of code to add.
        """
        for line in lines:
            self.add_line(line)

    def add_blank_line(self) -> None:
        """Add a blank line to the generated code."""
        self.code_lines.append("")

    def get_output_variable(self, node_id: str, port_name: str) -> Optional[str]:
        """
        Get the variable name for a node's output port.

        Args:
            node_id: The node ID.
            port_name: The output port name.

        Returns:
            The variable name if it exists, None otherwise.
        """
        key = f"{node_id}.{port_name}"
        return self.generated_variables.get(key)

    def set_output_variable(
        self,
        node_id: str,
        port_name: str,
        var_name: str,
        track_scope: bool = True,
    ) -> None:
        """
        Set the variable name for a node's output port.

        Args:
            node_id: The node ID.
            port_name: The output port name.
            var_name: The variable name to associate.
            track_scope: Whether to track this variable in the scope manager.
        """
        key = f"{node_id}.{port_name}"
        self.generated_variables[key] = var_name

        # Also track in the scope manager for scope-aware access checking
        # Only if there's an active scope (during actual code generation)
        if track_scope and self.scope_manager.current_scope is not None:
            self.scope_manager.define_variable(node_id, port_name, var_name)

    def get_output_variable_with_scope_check(
        self,
        node_id: str,
        port_name: str,
        accessing_node_id: str,
    ) -> Optional[str]:
        """
        Get a variable name with scope safety checking.

        This method retrieves a variable and checks if it's safely accessible
        from the current scope. If the variable is only conditionally defined,
        a warning is added.

        Args:
            node_id: The source node ID.
            port_name: The source port name.
            accessing_node_id: The ID of the node trying to access the variable.

        Returns:
            The variable name if it exists, None otherwise.
        """
        var_name = self.get_output_variable(node_id, port_name)

        if var_name:
            # Check for scope access issues
            access_warnings = self.scope_manager.check_variable_access(
                node_id, port_name, accessing_node_id
            )
            self.warnings.extend(access_warnings)

        return var_name

    def get_variable_scope_info(
        self,
        node_id: str,
        port_name: str,
    ) -> Optional[VariableInfo]:
        """
        Get detailed scope information about a variable.

        Args:
            node_id: The source node ID.
            port_name: The source port name.

        Returns:
            VariableInfo if the variable exists, None otherwise.
        """
        return self.scope_manager.get_variable(node_id, port_name)

    def is_variable_conditional(self, node_id: str, port_name: str) -> bool:
        """
        Check if a variable is only conditionally defined.

        Args:
            node_id: The source node ID.
            port_name: The source port name.

        Returns:
            True if the variable is only defined in some code paths.
        """
        var_info = self.scope_manager.get_variable(node_id, port_name)
        return var_info.is_conditional if var_info else False

    def is_node_processed(self, node_id: str) -> bool:
        """Check if a node has been processed."""
        return node_id in self.processed_nodes

    def mark_node_processed(self, node_id: str) -> None:
        """Mark a node as processed."""
        self.processed_nodes.add(node_id)

    def get_conditional_variable_initializations(self) -> List[str]:
        """
        Get initialization statements for conditional variables.

        Returns:
            List of initialization statements to prevent undefined variable errors.
        """
        return self.scope_manager.generate_initialization_code()

    def get_generated_code(self) -> str:
        """Get the complete generated code as a string."""
        parts: List[str] = []

        # Add imports if any
        if self.imports:
            for imp in sorted(self.imports):
                parts.append(imp)
            parts.append("")

        # Add main code
        parts.extend(self.code_lines)

        return "\n".join(parts)

    def get_scope_warnings(self) -> List[str]:
        """
        Get all warnings related to variable scopes.

        Returns:
            Combined list of context warnings and scope manager warnings.
        """
        return self.warnings + self.scope_manager.warnings

    def reset(self) -> None:
        """Reset the context for a fresh generation."""
        self.indentation.reset()
        self.context_stack.clear()
        self.generated_variables.clear()
        self.processed_nodes.clear()
        self.code_lines.clear()
        self.imports.clear()
        self.errors.clear()
        self.warnings.clear()
        self._variable_counter = 0
        self.scope_manager.reset()
        self.thread_variables.clear()


class NodeEmitter(ABC):
    """
    Abstract base class for node-specific code emitters.

    Each node type has its own emitter that knows how to generate
    the appropriate Python code for that node's behavior.
    """

    @property
    @abstractmethod
    def node_type(self) -> str:
        """Return the node type this emitter handles."""
        pass

    @abstractmethod
    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for the given node.

        Args:
            node: The node to generate code for.
            context: The current generation context.
            generator: The parent code generator.
        """
        pass

    def get_input_value(
        self,
        node: BaseNode,
        port_name: str,
        context: GenerationContext,
        graph: Graph,
        default: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get the variable name or value for an input port.

        Args:
            node: The node containing the input port.
            port_name: The name of the input port.
            context: The current generation context.
            graph: The graph being processed.
            default: Default value if not connected.

        Returns:
            The variable name or literal value, or None if not available.
        """
        port = node.get_input_port(port_name)
        if port is None:
            return default

        if port.is_connected() and port.connection:
            # Get the variable from the source node's output
            source_node_id = port.connection.source_node_id
            source_port_name = port.connection.source_port_name
            var_name = context.get_output_variable(source_node_id, source_port_name)
            if var_name:
                return var_name

        # Use default value if available
        if port.default_value is not None:
            return repr(port.default_value)

        return default


class StartNodeEmitter(NodeEmitter):
    """Emitter for Start nodes - entry point of execution."""

    @property
    def node_type(self) -> str:
        return "start"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """Start nodes just mark the beginning - emit a comment."""
        context.add_line("# Script execution begins")
        context.mark_node_processed(node.id)


class EndNodeEmitter(NodeEmitter):
    """Emitter for End nodes - termination point of execution."""

    @property
    def node_type(self) -> str:
        return "end"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """End nodes capture results and terminate execution paths."""
        result_var = self.get_input_value(node, "result", context, generator.graph)

        if result_var:
            context.add_line(f"# End of execution - result: {result_var}")
            context.add_line(f"_end_result = {result_var}")
        else:
            context.add_line("# End of execution")
            context.add_line("pass  # End node")

        context.mark_node_processed(node.id)


class CodeNodeEmitter(NodeEmitter):
    """
    Emitter for Code nodes - inline Python code execution.

    This emitter extracts Python code from CodeNode instances and inserts it
    into the generated script. The user's code has access to:
    - 'inputs': A dictionary containing values from connected input ports
    - 'outputs': A dictionary where the code should set output values
    - 'globals': A dictionary (_global_vars) for persistent state across nodes

    The emitter handles:
    - Proper indentation within control flow structures (if/for)
    - Variable tracking for connecting outputs to downstream nodes
    - Empty code node handling
    - Multi-line code preservation
    """

    @property
    def node_type(self) -> str:
        return "code"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a CodeNode.

        The CodeNode's code is embedded directly into the generated script,
        wrapped with proper namespace setup for inputs, outputs, and globals.
        The code maintains its original formatting and indentation relative
        to the current context.

        Args:
            node: The CodeNode to generate code for.
            context: The current generation context with indentation state.
            generator: The parent code generator for graph access.
        """
        from visualpython.nodes.models.code_node import CodeNode

        if not isinstance(node, CodeNode):
            context.errors.append(f"Expected CodeNode but got {type(node).__name__}")
            return

        code = node.code
        if not code or not code.strip():
            context.add_line("pass  # Empty code node")
            context.mark_node_processed(node.id)
            return

        # Get input value if connected
        input_var = self.get_input_value(node, "value", context, generator.graph)

        # Generate a variable for the result
        result_var = context.generate_variable_name("result")
        context.set_output_variable(node.id, "result", result_var)

        # Add comment header for the code block
        context.add_line(f"# Code node: {node.name}")

        # Create the inputs dict with connected values
        if input_var:
            context.add_line(f"inputs = {{'value': {input_var}}}")
        else:
            context.add_line("inputs = {}")

        # Create outputs dict for user code to populate
        context.add_line("outputs = {}")

        # Provide access to globals (the global variable store)
        # This allows user code to use: globals.get('key'), globals['key'] = value
        context.add_line("globals = _global_vars")

        # Emit the user's Python code
        # Each line is added with proper indentation for the current context
        code_lines = code.strip().split("\n")
        for line in code_lines:
            context.add_line(line)

        # Extract result from outputs dict into tracked variable
        context.add_line(f"{result_var} = outputs.get('result')")
        context.add_blank_line()

        context.mark_node_processed(node.id)


class IfNodeEmitter(NodeEmitter):
    """Emitter for If nodes - conditional branching."""

    @property
    def node_type(self) -> str:
        return "if"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for an IfNode.

        Creates an if/else structure and recursively generates code
        for each branch. Tracks variable scopes to detect variables that
        are only defined in one branch (conditional variables).

        When both branches converge to the same node (typically a merge node),
        that convergence node is emitted after the if/else block completes,
        ensuring proper code structure.
        """
        from visualpython.nodes.models.if_node import IfNode

        if not isinstance(node, IfNode):
            context.errors.append(f"Expected IfNode but got {type(node).__name__}")
            return

        # Get condition value
        condition_var = self.get_input_value(node, "condition", context, generator.graph)

        # Determine the condition expression
        if node.condition_code:
            # Use the condition code directly
            condition_expr = node.condition_code.strip()
        elif condition_var:
            condition_expr = condition_var
        else:
            condition_expr = "False"

        # Store the result (defined at current scope, not conditional)
        result_var = context.generate_variable_name("condition_result")
        context.set_output_variable(node.id, "result", result_var)

        context.add_line(f"# If node: {node.name}")
        context.add_line(f"{result_var} = bool({condition_expr})")
        context.add_line(f"if {result_var}:")

        # Find convergence nodes - nodes that both branches lead to
        # These should be emitted after the if/else block, not inside branches
        convergence_nodes = self._find_convergence_nodes(node, generator)

        # True branch - enter scope for variable tracking
        context.indentation.indent()
        context.enter_scope(CodeContext.IF_BRANCH, branch_name="true_branch")

        true_branch_nodes = generator.get_flow_connected_nodes(node.id, "true_branch")
        if true_branch_nodes:
            for branch_node in true_branch_nodes:
                # Skip convergence nodes - they'll be emitted after if/else
                if branch_node.id not in convergence_nodes:
                    self._emit_branch_flow(branch_node, context, generator, convergence_nodes)
                else:
                    context.add_line("pass  # Continues to merge point")
        else:
            context.add_line("pass")

        # Exit true branch scope
        true_branch_scope = context.scope_manager.current_scope
        context.exit_scope()
        context.indentation.dedent()

        # False branch
        context.add_line("else:")
        context.indentation.indent()
        context.enter_scope(CodeContext.IF_BRANCH, branch_name="false_branch")

        false_branch_nodes = generator.get_flow_connected_nodes(node.id, "false_branch")
        if false_branch_nodes:
            for branch_node in false_branch_nodes:
                # Skip convergence nodes - they'll be emitted after if/else
                if branch_node.id not in convergence_nodes:
                    self._emit_branch_flow(branch_node, context, generator, convergence_nodes)
                else:
                    context.add_line("pass  # Continues to merge point")
        else:
            context.add_line("pass")

        # Exit false branch scope
        false_branch_scope = context.scope_manager.current_scope
        context.exit_scope()
        context.indentation.dedent()

        # Merge branch scopes to identify truly conditional variables
        if true_branch_scope and false_branch_scope:
            context.scope_manager.merge_branch_scopes(
                [true_branch_scope, false_branch_scope]
            )

        context.add_blank_line()
        context.mark_node_processed(node.id)

        # Now emit convergence nodes after the if/else block
        for conv_node_id in convergence_nodes:
            conv_node = generator.graph.get_node(conv_node_id)
            if conv_node and not context.is_node_processed(conv_node.id):
                generator._emit_flow_from_node(conv_node, context)

    def _find_convergence_nodes(
        self,
        if_node: BaseNode,
        generator: CodeGenerator,
    ) -> Set[str]:
        """
        Find nodes that both true and false branches eventually lead to.

        These are convergence points (typically merge nodes) that should be
        emitted after the if/else block rather than inside a branch.

        Args:
            if_node: The if node being processed.
            generator: The code generator for graph access.

        Returns:
            Set of node IDs that are convergence points.
        """
        # Get immediate successors of each branch
        true_successors = self._get_all_successors(if_node.id, "true_branch", generator)
        false_successors = self._get_all_successors(if_node.id, "false_branch", generator)

        # Convergence nodes are those reachable from both branches
        convergence = true_successors & false_successors

        return convergence

    def _get_all_successors(
        self,
        node_id: str,
        port_name: str,
        generator: CodeGenerator,
    ) -> Set[str]:
        """
        Get all successor node IDs reachable from a given port.

        Args:
            node_id: The source node ID.
            port_name: The output port name.
            generator: The code generator for graph access.

        Returns:
            Set of node IDs reachable from the port.
        """
        successors: Set[str] = set()
        visited: Set[str] = set()

        def traverse(nid: str, pname: str) -> None:
            connections = generator.graph.get_connections_for_port(nid, pname, is_input=False)
            for conn in connections:
                target_id = conn.target_node_id
                if target_id not in visited:
                    visited.add(target_id)
                    successors.add(target_id)
                    # Continue traversing from the target node's exec_out
                    target_node = generator.graph.get_node(target_id)
                    if target_node:
                        # Don't traverse through if nodes to avoid infinite loops
                        if target_node.node_type != "if":
                            traverse(target_id, "exec_out")

        traverse(node_id, port_name)
        return successors

    def _emit_branch_flow(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
        convergence_nodes: Set[str],
    ) -> None:
        """
        Emit code for a branch, stopping at convergence nodes.

        Args:
            node: The starting node of the branch.
            context: The generation context.
            generator: The code generator.
            convergence_nodes: Set of node IDs to stop at (convergence points).
        """
        if context.is_node_processed(node.id):
            return

        if node.id in convergence_nodes:
            # Don't emit convergence nodes inside branches
            return

        # Emit this node
        generator.emit_node(node, context)

        # Follow flow output to next nodes
        if node.node_type not in ("if", "for_loop"):
            flow_out_port = node.get_output_port("exec_out")
            if flow_out_port:
                next_nodes = generator.get_flow_connected_nodes(node.id, "exec_out")
                for next_node in next_nodes:
                    self._emit_branch_flow(next_node, context, generator, convergence_nodes)


class ForLoopNodeEmitter(NodeEmitter):
    """Emitter for ForLoop nodes - iteration over collections."""

    @property
    def node_type(self) -> str:
        return "for_loop"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a ForLoopNode.

        Creates a for loop structure with the configured iteration variable.
        Variables defined inside the loop body are tracked as conditional
        since they depend on the loop executing at least once.
        """
        from visualpython.nodes.models.for_loop_node import ForLoopNode

        if not isinstance(node, ForLoopNode):
            context.errors.append(f"Expected ForLoopNode but got {type(node).__name__}")
            return

        # Get iterable
        iterable_var = self.get_input_value(
            node, "iterable", context, generator.graph, default="[]"
        )

        # Get iteration variable name
        iter_var = node.iteration_variable or "item"
        index_var = context.generate_variable_name("index")

        # Set output variables for loop body access (tracked at current scope)
        # These are available inside the loop body
        context.set_output_variable(node.id, "item", iter_var, track_scope=False)
        context.set_output_variable(node.id, "index", index_var, track_scope=False)

        context.add_line(f"# For loop: {node.name}")
        context.add_line(f"for {index_var}, {iter_var} in enumerate({iterable_var}):")

        # Loop body - enter scope for variable tracking
        context.indentation.indent()
        context.enter_scope(CodeContext.LOOP_BODY, branch_name="loop_body")

        loop_body_nodes = generator.get_flow_connected_nodes(node.id, "loop_body")
        if loop_body_nodes:
            for body_node in loop_body_nodes:
                generator.emit_node(body_node, context)
        else:
            context.add_line("pass")

        # Exit loop body scope
        context.exit_scope()
        context.indentation.dedent()
        context.add_blank_line()

        # Handle completed flow (nodes after the loop)
        context.mark_node_processed(node.id)


class GetVariableNodeEmitter(NodeEmitter):
    """Emitter for GetVariable nodes - retrieve global variables."""

    @property
    def node_type(self) -> str:
        return "get_variable"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """Generate code to retrieve a global variable."""
        from visualpython.nodes.models.get_variable_node import GetVariableNode

        if not isinstance(node, GetVariableNode):
            context.errors.append(f"Expected GetVariableNode but got {type(node).__name__}")
            return

        var_name = node.variable_name
        dynamic_name = self.get_input_value(node, "variable_name", context, generator.graph)

        # Generate output variable
        value_var = context.generate_variable_name("var_value")
        exists_var = context.generate_variable_name("var_exists")

        context.set_output_variable(node.id, "value", value_var)
        context.set_output_variable(node.id, "exists", exists_var)

        context.add_line(f"# Get variable: {node.name}")

        # Determine the variable name to use
        if dynamic_name:
            context.add_line(f"_var_name = {dynamic_name}")
        else:
            context.add_line(f"_var_name = {repr(var_name)}")

        # Generate the retrieval code using globals dict
        default_repr = repr(node.default_value) if node.default_value is not None else "None"
        context.add_line(f"{exists_var} = _var_name in _global_vars")
        context.add_line(f"{value_var} = _global_vars.get(_var_name, {default_repr})")
        context.add_blank_line()

        context.mark_node_processed(node.id)


class SetVariableNodeEmitter(NodeEmitter):
    """Emitter for SetVariable nodes - store global variables."""

    @property
    def node_type(self) -> str:
        return "set_variable"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """Generate code to set a global variable."""
        from visualpython.nodes.models.set_variable_node import SetVariableNode

        if not isinstance(node, SetVariableNode):
            context.errors.append(f"Expected SetVariableNode but got {type(node).__name__}")
            return

        var_name = node.variable_name
        dynamic_name = self.get_input_value(node, "variable_name", context, generator.graph)
        value = self.get_input_value(node, "value", context, generator.graph, default="None")

        # Generate success output variable
        success_var = context.generate_variable_name("set_success")
        context.set_output_variable(node.id, "success", success_var)

        context.add_line(f"# Set variable: {node.name}")

        # Determine the variable name to use
        if dynamic_name:
            context.add_line(f"_var_name = {dynamic_name}")
        else:
            context.add_line(f"_var_name = {repr(var_name)}")

        # Generate the set code
        context.add_line(f"_global_vars[_var_name] = {value}")
        context.add_line(f"{success_var} = True")
        context.add_blank_line()

        context.mark_node_processed(node.id)


class MergeNodeEmitter(NodeEmitter):
    """
    Emitter for Merge nodes - converge multiple execution paths.

    The MergeNode enables path convergence after branching operations like if/else
    statements. In generated code, it aggregates data from whichever input path(s)
    were executed and continues execution through a single output path.

    Generated code handles:
    - Tracking which input path triggered the merge
    - Consolidating data from the triggered input(s)
    - Providing outputs for merged_data and triggered_path
    - Continuing execution flow through exec_out
    """

    @property
    def node_type(self) -> str:
        return "merge"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a MergeNode.

        The generated code determines which input path was taken and consolidates
        the data from that path. Since in static code generation only one branch
        of an if/else actually executes, the merge node uses conditionally-defined
        variables to track which path arrived.

        Args:
            node: The MergeNode to generate code for.
            context: The current generation context with indentation state.
            generator: The parent code generator for graph access.
        """
        from visualpython.nodes.models.merge_node import MergeNode

        if not isinstance(node, MergeNode):
            context.errors.append(f"Expected MergeNode but got {type(node).__name__}")
            return

        # Generate output variables for the merge result
        merged_data_var = context.generate_variable_name("merged_data")
        triggered_path_var = context.generate_variable_name("triggered_path")

        context.set_output_variable(node.id, "merged_data", merged_data_var)
        context.set_output_variable(node.id, "triggered_path", triggered_path_var)

        context.add_line(f"# Merge node: {node.name}")

        # Initialize output variables
        context.add_line(f"{merged_data_var} = None")
        context.add_line(f"{triggered_path_var} = 0")

        # Check each input path for connected data
        # In generated code, we check which data inputs have values defined
        # The data_in_N variables will be set by upstream nodes in whichever branch executed
        data_inputs_found: List[tuple] = []

        for i in range(1, node.num_inputs + 1):
            data_port_name = f"data_in_{i}"
            data_var = self.get_input_value(
                node, data_port_name, context, generator.graph
            )
            if data_var:
                data_inputs_found.append((i, data_var))

        if data_inputs_found:
            # Generate code to determine which path's data to use
            # For multiple connected data inputs, generate conditional checks
            if len(data_inputs_found) == 1:
                # Simple case: only one data input connected
                idx, data_var = data_inputs_found[0]
                context.add_line(f"{merged_data_var} = {data_var}")
                context.add_line(f"{triggered_path_var} = {idx}")
            else:
                # Multiple data inputs connected
                # Generate conditional logic to select based on which variable is defined
                # This handles cases where different branches define different variables
                first = True
                for idx, data_var in data_inputs_found:
                    var_info = context.get_variable_scope_info(
                        *self._parse_var_reference(data_var, context)
                    )
                    is_conditional = var_info.is_conditional if var_info else False

                    if is_conditional:
                        # Variable is conditionally defined, need to check existence
                        if first:
                            context.add_line(f"if '{data_var}' in dir():")
                            first = False
                        else:
                            context.add_line(f"elif '{data_var}' in dir():")
                        context.indentation.indent()
                        context.add_line(f"{merged_data_var} = {data_var}")
                        context.add_line(f"{triggered_path_var} = {idx}")
                        context.indentation.dedent()
                    else:
                        # Variable is unconditionally defined
                        if first:
                            context.add_line(f"{merged_data_var} = {data_var}")
                            context.add_line(f"{triggered_path_var} = {idx}")
                            first = False
                        else:
                            # If we have an unconditional variable after conditionals,
                            # it should be the fallback
                            context.add_line("else:")
                            context.indentation.indent()
                            context.add_line(f"{merged_data_var} = {data_var}")
                            context.add_line(f"{triggered_path_var} = {idx}")
                            context.indentation.dedent()

        context.add_blank_line()
        context.mark_node_processed(node.id)

    def _parse_var_reference(
        self, var_name: str, context: GenerationContext
    ) -> tuple:
        """
        Parse a variable reference to find its source node and port.

        Args:
            var_name: The variable name to look up.
            context: The generation context with variable mappings.

        Returns:
            Tuple of (node_id, port_name) or (None, None) if not found.
        """
        # Reverse lookup in generated_variables
        for key, value in context.generated_variables.items():
            if value == var_name:
                parts = key.split(".", 1)
                if len(parts) == 2:
                    return parts[0], parts[1]
        return None, None


class ThreadNodeEmitter(NodeEmitter):
    """
    Emitter for Thread nodes - spawn parallel execution paths.

    The ThreadNode enables concurrent processing by generating Python threading code
    that executes connected downstream paths in separate threads. Each thread output
    port becomes a separate thread function that runs in parallel.

    Generated code pattern:
    1. Define a thread function for each connected thread output
    2. Create threading.Thread instances for each function
    3. Start all threads
    4. If wait_for_all is True, join all threads before continuing

    Thread-safe data sharing is handled through the global _global_vars dictionary.
    """

    @property
    def node_type(self) -> str:
        return "thread"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate Python threading code for parallel execution.

        Creates thread functions for each connected thread output, starts them,
        and optionally waits for completion based on the node's configuration.

        Args:
            node: The ThreadNode to generate code for.
            context: The current generation context with indentation state.
            generator: The parent code generator for graph access.
        """
        from visualpython.nodes.models.thread_node import ThreadNode

        if not isinstance(node, ThreadNode):
            context.errors.append(f"Expected ThreadNode but got {type(node).__name__}")
            return

        # Add threading import
        context.imports.add("import threading")

        # Get input data to pass to threads
        data_var = self.get_input_value(node, "data_in", context, generator.graph)

        # Generate variables for tracking threads
        threads_list_var = context.generate_variable_name("threads")
        results_var = context.generate_variable_name("thread_results")
        lock_var = context.generate_variable_name("thread_lock")

        context.set_output_variable(node.id, "thread_results", results_var)
        context.set_output_variable(node.id, "data_out", data_var if data_var else "None")

        context.add_line(f"# Thread node: {node.name}")
        context.add_line(f"{threads_list_var} = []")
        context.add_line(f"{results_var} = {{}}")
        context.add_line(f"{lock_var} = threading.Lock()")
        context.add_blank_line()

        # Store thread variables in context for ThreadJoinNode to use
        context.thread_variables[node.id] = threads_list_var

        # Get connected thread outputs and generate functions for each
        connected_indices = node.get_connected_thread_indices()

        for idx in connected_indices:
            port_name = f"thread_out_{idx}"
            func_name = context.generate_variable_name(f"thread_func_{idx}")

            # Generate thread function
            context.add_line(f"def {func_name}():")
            context.indentation.indent()

            # Provide access to shared data in thread
            if data_var:
                context.add_line(f"_thread_data = {data_var}")
            else:
                context.add_line("_thread_data = None")

            # Enter a new scope for thread body (similar to loop body)
            context.enter_scope(CodeContext.FUNCTION, branch_name=f"thread_{idx}")

            # Get nodes connected to this thread output and emit them
            thread_nodes = generator.get_flow_connected_nodes(node.id, port_name)
            if thread_nodes:
                for thread_node in thread_nodes:
                    # Recursively emit the thread body
                    self._emit_thread_body(thread_node, context, generator, idx, results_var, lock_var)
            else:
                context.add_line("pass  # Empty thread body")

            # Exit thread scope
            context.exit_scope()
            context.indentation.dedent()
            context.add_blank_line()

            # Create and add thread to list
            context.add_line(f"_t_{idx} = threading.Thread(target={func_name}, name='thread_{idx}')")
            context.add_line(f"{threads_list_var}.append(_t_{idx})")

        # Mark thread output nodes as processed (they're handled inside thread functions)
        for idx in connected_indices:
            port_name = f"thread_out_{idx}"
            thread_nodes = generator.get_flow_connected_nodes(node.id, port_name)
            for thread_node in thread_nodes:
                self._mark_thread_nodes_processed(thread_node, context, generator)

        context.add_blank_line()

        # Start all threads
        context.add_line(f"# Start all threads")
        context.add_line(f"for _t in {threads_list_var}:")
        context.indentation.indent()
        context.add_line("_t.start()")
        context.indentation.dedent()
        context.add_blank_line()

        # Wait for all threads if configured
        if node.wait_for_all:
            context.add_line(f"# Wait for all threads to complete")
            context.add_line(f"for _t in {threads_list_var}:")
            context.indentation.indent()
            context.add_line("_t.join()")
            context.indentation.dedent()
            context.add_blank_line()

        context.mark_node_processed(node.id)

    def _emit_thread_body(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
        thread_idx: int,
        results_var: str,
        lock_var: str,
    ) -> None:
        """
        Emit code for nodes within a thread body.

        Args:
            node: The node to emit code for.
            context: The generation context.
            generator: The code generator.
            thread_idx: The index of the current thread.
            results_var: Variable name for thread results dictionary.
            lock_var: Variable name for the thread lock.
        """
        if context.is_node_processed(node.id):
            return

        # Check if this node is a ThreadJoinNode - stop here
        if node.node_type == "thread_join":
            return

        # Emit this node
        generator.emit_node(node, context)

        # Follow flow output to next nodes
        if node.node_type not in ("if", "for_loop"):
            next_nodes = generator.get_flow_connected_nodes(node.id, "exec_out")
            for next_node in next_nodes:
                self._emit_thread_body(next_node, context, generator, thread_idx, results_var, lock_var)

    def _mark_thread_nodes_processed(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Mark all nodes in a thread body as processed.

        This prevents the main traversal from re-emitting nodes that
        have already been emitted inside thread functions.

        Args:
            node: The starting node of the thread body.
            context: The generation context.
            generator: The code generator.
        """
        if context.is_node_processed(node.id):
            return

        # Stop at thread join nodes
        if node.node_type == "thread_join":
            return

        context.mark_node_processed(node.id)

        # Follow flow output to next nodes
        if node.node_type not in ("if", "for_loop"):
            next_nodes = generator.get_flow_connected_nodes(node.id, "exec_out")
            for next_node in next_nodes:
                self._mark_thread_nodes_processed(next_node, context, generator)


class ThreadJoinNodeEmitter(NodeEmitter):
    """
    Emitter for ThreadJoin nodes - synchronization point for parallel threads.

    The ThreadJoinNode waits for specified threads to complete before allowing
    execution to continue. This provides synchronization points in parallel workflows.

    Generated code pattern:
    1. Find thread variables from connected ThreadNode(s)
    2. Generate thread.join() calls with optional timeout
    3. Collect results from all threads
    4. Continue execution after synchronization
    """

    @property
    def node_type(self) -> str:
        return "thread_join"

    def _find_source_thread_nodes(
        self,
        node: BaseNode,
        generator: CodeGenerator,
    ) -> List[str]:
        """
        Find the ThreadNode IDs that feed into this ThreadJoinNode.

        Traces back through the graph from thread_in_N ports to find
        the source ThreadNode(s).

        Args:
            node: The ThreadJoinNode.
            generator: The code generator for graph access.

        Returns:
            List of ThreadNode IDs that connect to this join node.
        """
        from visualpython.nodes.models.thread_join_node import ThreadJoinNode

        if not isinstance(node, ThreadJoinNode):
            return []

        thread_node_ids: List[str] = []
        visited: Set[str] = set()

        def trace_back(current_node_id: str) -> None:
            """Recursively trace back to find ThreadNodes."""
            if current_node_id in visited:
                return
            visited.add(current_node_id)

            current_node = generator.graph.get_node(current_node_id)
            if current_node is None:
                return

            # Check if this is a ThreadNode
            if current_node.node_type == "thread":
                if current_node_id not in thread_node_ids:
                    thread_node_ids.append(current_node_id)
                return

            # Trace back through flow inputs
            for port in current_node.input_ports:
                if port.is_connected() and port.connection:
                    source_node_id = port.connection.source_node_id
                    trace_back(source_node_id)

        # Start tracing from thread_in_N ports
        for i in range(1, node.num_inputs + 1):
            port = node.get_input_port(f"thread_in_{i}")
            if port and port.is_connected() and port.connection:
                source_node_id = port.connection.source_node_id
                trace_back(source_node_id)

        return thread_node_ids

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate synchronization code for thread joining.

        Generates explicit thread.join() calls to wait for thread completion,
        with optional timeout support based on the node's configuration.

        Args:
            node: The ThreadJoinNode to generate code for.
            context: The current generation context with indentation state.
            generator: The parent code generator for graph access.
        """
        from visualpython.nodes.models.thread_join_node import ThreadJoinNode

        if not isinstance(node, ThreadJoinNode):
            context.errors.append(f"Expected ThreadJoinNode but got {type(node).__name__}")
            return

        # Add threading import (may already be added by ThreadNodeEmitter)
        context.imports.add("import threading")

        # Generate output variables
        all_completed_var = context.generate_variable_name("all_completed")
        completed_count_var = context.generate_variable_name("completed_count")
        thread_data_var = context.generate_variable_name("thread_data")

        context.set_output_variable(node.id, "all_completed", all_completed_var)
        context.set_output_variable(node.id, "completed_count", completed_count_var)
        context.set_output_variable(node.id, "thread_data", thread_data_var)

        context.add_line(f"# Thread join node: {node.name}")

        # Find source ThreadNode(s) and their thread list variables
        source_thread_node_ids = self._find_source_thread_nodes(node, generator)
        threads_to_join: List[str] = []

        for thread_node_id in source_thread_node_ids:
            threads_list_var = context.thread_variables.get(thread_node_id)
            if threads_list_var:
                threads_to_join.append(threads_list_var)

        # Generate thread.join() calls for synchronization
        if threads_to_join:
            context.add_line(f"# Wait for threads to complete")

            # Handle timeout configuration
            timeout_seconds = node.timeout_ms / 1000.0 if node.timeout_ms > 0 else None

            if node.wait_for_all:
                # Wait for all threads from all source ThreadNodes
                for threads_list_var in threads_to_join:
                    context.add_line(f"for _thread in {threads_list_var}:")
                    context.indentation.indent()
                    if timeout_seconds is not None:
                        context.add_line(f"_thread.join(timeout={timeout_seconds})")
                    else:
                        context.add_line("_thread.join()")
                    context.indentation.dedent()
            else:
                # Wait for any thread to complete (join with short poll intervals)
                # This creates a polling mechanism to detect first completion
                context.add_line(f"_all_threads = []")
                for threads_list_var in threads_to_join:
                    context.add_line(f"_all_threads.extend({threads_list_var})")

                if timeout_seconds is not None:
                    context.add_line(f"_join_timeout = {timeout_seconds}")
                    context.add_line(f"_poll_interval = min(0.1, _join_timeout / 10)")
                    context.add_line(f"_elapsed = 0.0")
                    context.add_line(f"while _elapsed < _join_timeout:")
                    context.indentation.indent()
                    context.add_line(f"for _thread in _all_threads:")
                    context.indentation.indent()
                    context.add_line(f"if not _thread.is_alive():")
                    context.indentation.indent()
                    context.add_line(f"break")
                    context.indentation.dedent()
                    context.indentation.dedent()
                    context.add_line(f"else:")
                    context.indentation.indent()
                    context.add_line(f"import time")
                    context.add_line(f"time.sleep(_poll_interval)")
                    context.add_line(f"_elapsed += _poll_interval")
                    context.add_line(f"continue")
                    context.indentation.dedent()
                    context.add_line(f"break")
                    context.indentation.dedent()
                else:
                    # No timeout - just join all threads
                    context.add_line(f"for _thread in _all_threads:")
                    context.indentation.indent()
                    context.add_line("_thread.join()")
                    context.indentation.dedent()

            context.add_blank_line()

        # Collect data from connected thread inputs
        data_inputs: List[tuple] = []
        for i in range(1, node.num_inputs + 1):
            data_port_name = f"data_in_{i}"
            data_var = self.get_input_value(node, data_port_name, context, generator.graph)
            if data_var:
                data_inputs.append((i, data_var))

        # Initialize thread data dictionary
        context.add_line(f"{thread_data_var} = {{}}")

        # Collect data from inputs
        for idx, data_var in data_inputs:
            context.add_line(f"{thread_data_var}[{idx}] = {data_var}")

        # Calculate completion status based on threads still alive
        if threads_to_join:
            context.add_line(f"# Calculate completion status")
            context.add_line(f"_alive_count = 0")
            for threads_list_var in threads_to_join:
                context.add_line(f"for _t in {threads_list_var}:")
                context.indentation.indent()
                context.add_line(f"if _t.is_alive():")
                context.indentation.indent()
                context.add_line(f"_alive_count += 1")
                context.indentation.dedent()
                context.indentation.dedent()
            context.add_line(f"_total_threads = sum(len(_tl) for _tl in [{', '.join(threads_to_join)}])")
            context.add_line(f"{completed_count_var} = _total_threads - _alive_count")
            context.add_line(f"{all_completed_var} = _alive_count == 0")
        else:
            # No threads found, use data inputs to determine completion
            context.add_line(f"{completed_count_var} = len({thread_data_var})")
            expected_count = len(data_inputs) if data_inputs else node.num_inputs
            context.add_line(f"{all_completed_var} = {completed_count_var} >= {expected_count}")

        context.add_blank_line()
        context.mark_node_processed(node.id)


class DatabaseQueryNodeEmitter(NodeEmitter):
    """
    Emitter for DatabaseQuery nodes - SQL database operations.

    The DatabaseQueryNode enables executing SQL queries against databases
    with configurable connection strings. Currently supports SQLite natively.

    Generated code pattern:
    ```python
    import sqlite3
    _conn = sqlite3.connect(connection_string)
    _conn.row_factory = sqlite3.Row
    _cursor = _conn.cursor()
    _cursor.execute(query, parameters)
    rows = [dict(row) for row in _cursor.fetchall()]
    # ... result handling ...
    _conn.close()
    ```
    """

    @property
    def node_type(self) -> str:
        return "database_query"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a DatabaseQueryNode.

        Creates database connection and query execution code with proper
        error handling and resource cleanup.

        Args:
            node: The DatabaseQueryNode to generate code for.
            context: The current generation context with indentation state.
            generator: The parent code generator for graph access.
        """
        from visualpython.nodes.models.database_query_node import DatabaseQueryNode

        if not isinstance(node, DatabaseQueryNode):
            context.errors.append(f"Expected DatabaseQueryNode but got {type(node).__name__}")
            return

        # Add sqlite3 import
        context.imports.add("import sqlite3")

        # Get input values or use configured values
        connection_var = self.get_input_value(
            node, "connection_string", context, generator.graph
        )
        query_var = self.get_input_value(
            node, "query", context, generator.graph
        )
        params_var = self.get_input_value(
            node, "parameters", context, generator.graph
        )
        timeout_var = self.get_input_value(
            node, "timeout", context, generator.graph
        )

        # Generate output variable names
        rows_var = context.generate_variable_name("db_rows")
        row_count_var = context.generate_variable_name("db_row_count")
        columns_var = context.generate_variable_name("db_columns")
        success_var = context.generate_variable_name("db_success")
        error_var = context.generate_variable_name("db_error")
        last_insert_id_var = context.generate_variable_name("db_last_insert_id")
        rows_affected_var = context.generate_variable_name("db_rows_affected")

        # Set output variables for downstream nodes
        context.set_output_variable(node.id, "rows", rows_var)
        context.set_output_variable(node.id, "row_count", row_count_var)
        context.set_output_variable(node.id, "columns", columns_var)
        context.set_output_variable(node.id, "success", success_var)
        context.set_output_variable(node.id, "error_message", error_var)
        context.set_output_variable(node.id, "last_insert_id", last_insert_id_var)
        context.set_output_variable(node.id, "rows_affected", rows_affected_var)

        context.add_line(f"# Database query node: {node.name}")

        # Determine connection string
        if connection_var:
            context.add_line(f"_db_connection_string = {connection_var}")
        else:
            context.add_line(f"_db_connection_string = {repr(node.connection_string)}")

        # Determine query
        if query_var:
            context.add_line(f"_db_query = {query_var}")
        else:
            context.add_line(f"_db_query = {repr(node.query)}")

        # Determine parameters
        if params_var:
            context.add_line(f"_db_params = {params_var}")
        else:
            context.add_line(f"_db_params = {repr(node.parameters)}")

        # Determine timeout
        if timeout_var:
            context.add_line(f"_db_timeout = {timeout_var}")
        else:
            context.add_line(f"_db_timeout = {node.timeout}")

        # Initialize output variables
        context.add_line(f"{rows_var} = []")
        context.add_line(f"{row_count_var} = 0")
        context.add_line(f"{columns_var} = []")
        context.add_line(f"{success_var} = False")
        context.add_line(f"{error_var} = ''")
        context.add_line(f"{last_insert_id_var} = 0")
        context.add_line(f"{rows_affected_var} = 0")

        # Generate try/except block for database operations
        context.add_line("try:")
        context.indentation.indent()

        # Connect to database
        context.add_line("_db_conn = sqlite3.connect(_db_connection_string, timeout=_db_timeout)")
        context.add_line("_db_conn.row_factory = sqlite3.Row")
        context.add_line("try:")
        context.indentation.indent()

        # Execute query
        context.add_line("_db_cursor = _db_conn.cursor()")
        context.add_line("if _db_params:")
        context.indentation.indent()
        context.add_line("_db_cursor.execute(_db_query, _db_params)")
        context.indentation.dedent()
        context.add_line("else:")
        context.indentation.indent()
        context.add_line("_db_cursor.execute(_db_query)")
        context.indentation.dedent()

        # Check if SELECT query
        context.add_line("_db_is_select = _db_query.strip().upper().startswith(('SELECT', 'WITH'))")
        context.add_line("if _db_is_select:")
        context.indentation.indent()

        # Fetch results for SELECT queries
        if node.fetch_size > 0:
            context.add_line(f"_db_raw_rows = _db_cursor.fetchmany({node.fetch_size})")
        else:
            context.add_line("_db_raw_rows = _db_cursor.fetchall()")

        context.add_line(f"{columns_var} = [desc[0] for desc in _db_cursor.description] if _db_cursor.description else []")
        context.add_line(f"{rows_var} = [dict(row) for row in _db_raw_rows]")
        context.add_line(f"{row_count_var} = len({rows_var})")
        context.indentation.dedent()

        context.add_line("else:")
        context.indentation.indent()
        context.add_line("_db_conn.commit()")
        context.add_line(f"{last_insert_id_var} = _db_cursor.lastrowid or 0")
        context.add_line(f"{rows_affected_var} = _db_cursor.rowcount")
        context.add_line(f"{row_count_var} = _db_cursor.rowcount")
        context.indentation.dedent()

        context.add_line(f"{success_var} = True")

        # Close connection in inner try
        context.indentation.dedent()
        context.add_line("finally:")
        context.indentation.indent()
        context.add_line("_db_conn.close()")
        context.indentation.dedent()

        # Handle exceptions
        context.indentation.dedent()
        context.add_line("except sqlite3.Error as _db_e:")
        context.indentation.indent()
        context.add_line(f"{error_var} = f'SQLite Error: {{_db_e}}'")
        context.indentation.dedent()
        context.add_line("except Exception as _db_e:")
        context.indentation.indent()
        context.add_line(f"{error_var} = str(_db_e)")
        context.indentation.dedent()

        context.add_blank_line()
        context.mark_node_processed(node.id)


class RegexMatchNodeEmitter(NodeEmitter):
    """
    Emitter for RegexMatch nodes - pattern matching operations.

    The RegexMatchNode enables visual regex pattern matching. Generated code
    uses Python's re module to find all matches in the input text.

    Generated code pattern:
    ```python
    import re
    _flags = 0
    if case_insensitive: _flags |= re.IGNORECASE
    # ... other flags ...
    _pattern = re.compile(pattern, _flags)
    _matches = _pattern.findall(text)
    # ... extract match info ...
    ```
    """

    @property
    def node_type(self) -> str:
        return "regex_match"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a RegexMatchNode.

        Creates regex matching code with proper error handling and flag support.

        Args:
            node: The RegexMatchNode to generate code for.
            context: The current generation context with indentation state.
            generator: The parent code generator for graph access.
        """
        from visualpython.nodes.models.regex_match_node import RegexMatchNode

        if not isinstance(node, RegexMatchNode):
            context.errors.append(f"Expected RegexMatchNode but got {type(node).__name__}")
            return

        # Add re import
        context.imports.add("import re")

        # Get input values
        text_var = self.get_input_value(node, "text", context, generator.graph)
        pattern_var = self.get_input_value(node, "pattern", context, generator.graph)

        # Generate output variable names
        matches_var = context.generate_variable_name("regex_matches")
        match_found_var = context.generate_variable_name("regex_match_found")
        first_match_var = context.generate_variable_name("regex_first_match")
        match_count_var = context.generate_variable_name("regex_match_count")
        groups_var = context.generate_variable_name("regex_groups")
        error_var = context.generate_variable_name("regex_error")

        # Set output variables
        context.set_output_variable(node.id, "matches", matches_var)
        context.set_output_variable(node.id, "match_found", match_found_var)
        context.set_output_variable(node.id, "first_match", first_match_var)
        context.set_output_variable(node.id, "match_count", match_count_var)
        context.set_output_variable(node.id, "groups", groups_var)
        context.set_output_variable(node.id, "error_message", error_var)

        context.add_line(f"# Regex match node: {node.name}")

        # Determine text value
        if text_var:
            context.add_line(f"_regex_text = str({text_var}) if {text_var} is not None else ''")
        else:
            context.add_line("_regex_text = ''")

        # Determine pattern value
        if pattern_var:
            context.add_line(f"_regex_pattern = {pattern_var}")
        else:
            context.add_line(f"_regex_pattern = {repr(node.default_pattern)}")

        # Initialize output variables
        context.add_line(f"{matches_var} = []")
        context.add_line(f"{match_found_var} = False")
        context.add_line(f"{first_match_var} = ''")
        context.add_line(f"{match_count_var} = 0")
        context.add_line(f"{groups_var} = []")
        context.add_line(f"{error_var} = ''")

        # Build flags
        flags_parts = []
        if node.case_insensitive:
            flags_parts.append("re.IGNORECASE")
        if node.multiline:
            flags_parts.append("re.MULTILINE")
        if node.dot_all:
            flags_parts.append("re.DOTALL")

        flags_expr = " | ".join(flags_parts) if flags_parts else "0"

        # Generate try/except block for regex operations
        context.add_line("try:")
        context.indentation.indent()

        context.add_line(f"_regex_compiled = re.compile(_regex_pattern, {flags_expr})")
        context.add_line(f"_regex_all_matches = _regex_compiled.findall(_regex_text)")

        # Handle groups - findall returns tuples if pattern has groups
        context.add_line("if _regex_all_matches:")
        context.indentation.indent()
        context.add_line("if isinstance(_regex_all_matches[0], tuple):")
        context.indentation.indent()
        context.add_line(f"{matches_var} = [m[0] if m else '' for m in _regex_all_matches]")
        context.indentation.dedent()
        context.add_line("else:")
        context.indentation.indent()
        context.add_line(f"{matches_var} = list(_regex_all_matches)")
        context.indentation.dedent()
        context.add_line(f"{match_found_var} = True")
        context.add_line(f"{first_match_var} = {matches_var}[0] if {matches_var} else ''")
        context.add_line(f"{match_count_var} = len({matches_var})")
        context.add_line("_regex_first_match_obj = _regex_compiled.search(_regex_text)")
        context.add_line("if _regex_first_match_obj and _regex_first_match_obj.groups():")
        context.indentation.indent()
        context.add_line(f"{groups_var} = list(_regex_first_match_obj.groups())")
        context.indentation.dedent()
        context.indentation.dedent()

        context.indentation.dedent()
        context.add_line("except re.error as _regex_e:")
        context.indentation.indent()
        context.add_line(f"{error_var} = f'Regex error: {{_regex_e}}'")
        context.indentation.dedent()
        context.add_line("except Exception as _regex_e:")
        context.indentation.indent()
        context.add_line(f"{error_var} = str(_regex_e)")
        context.indentation.dedent()

        context.add_blank_line()
        context.mark_node_processed(node.id)


class RegexReplaceNodeEmitter(NodeEmitter):
    """
    Emitter for RegexReplace nodes - pattern replacement operations.

    The RegexReplaceNode enables visual regex pattern replacement. Generated code
    uses Python's re module to replace all matches in the input text.

    Generated code pattern:
    ```python
    import re
    _flags = 0
    # ... flag setup ...
    _pattern = re.compile(pattern, _flags)
    _result, _count = _pattern.subn(replacement, text)
    ```
    """

    @property
    def node_type(self) -> str:
        return "regex_replace"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a RegexReplaceNode.

        Creates regex replacement code with proper error handling and flag support.

        Args:
            node: The RegexReplaceNode to generate code for.
            context: The current generation context with indentation state.
            generator: The parent code generator for graph access.
        """
        from visualpython.nodes.models.regex_replace_node import RegexReplaceNode

        if not isinstance(node, RegexReplaceNode):
            context.errors.append(f"Expected RegexReplaceNode but got {type(node).__name__}")
            return

        # Add re import
        context.imports.add("import re")

        # Get input values
        text_var = self.get_input_value(node, "text", context, generator.graph)
        pattern_var = self.get_input_value(node, "pattern", context, generator.graph)
        replacement_var = self.get_input_value(node, "replacement", context, generator.graph)

        # Generate output variable names
        result_var = context.generate_variable_name("regex_result")
        count_var = context.generate_variable_name("regex_replace_count")
        original_var = context.generate_variable_name("regex_original")
        changed_var = context.generate_variable_name("regex_changed")
        error_var = context.generate_variable_name("regex_replace_error")

        # Set output variables
        context.set_output_variable(node.id, "result", result_var)
        context.set_output_variable(node.id, "replacement_count", count_var)
        context.set_output_variable(node.id, "original_text", original_var)
        context.set_output_variable(node.id, "changed", changed_var)
        context.set_output_variable(node.id, "error_message", error_var)

        context.add_line(f"# Regex replace node: {node.name}")

        # Determine text value
        if text_var:
            context.add_line(f"_regex_text = str({text_var}) if {text_var} is not None else ''")
        else:
            context.add_line("_regex_text = ''")

        # Store original
        context.add_line(f"{original_var} = _regex_text")

        # Determine pattern value
        if pattern_var:
            context.add_line(f"_regex_pattern = {pattern_var}")
        else:
            context.add_line(f"_regex_pattern = {repr(node.default_pattern)}")

        # Determine replacement value
        if replacement_var:
            context.add_line(f"_regex_replacement = {replacement_var}")
        else:
            context.add_line(f"_regex_replacement = {repr(node.default_replacement)}")

        # Initialize output variables
        context.add_line(f"{result_var} = _regex_text")
        context.add_line(f"{count_var} = 0")
        context.add_line(f"{changed_var} = False")
        context.add_line(f"{error_var} = ''")

        # Build flags
        flags_parts = []
        if node.case_insensitive:
            flags_parts.append("re.IGNORECASE")
        if node.multiline:
            flags_parts.append("re.MULTILINE")
        if node.dot_all:
            flags_parts.append("re.DOTALL")

        flags_expr = " | ".join(flags_parts) if flags_parts else "0"

        # Generate try/except block for regex operations
        context.add_line("try:")
        context.indentation.indent()

        context.add_line(f"_regex_compiled = re.compile(_regex_pattern, {flags_expr})")

        # Perform replacement with optional count limit
        if node.max_replacements > 0:
            context.add_line(f"{result_var}, {count_var} = _regex_compiled.subn(_regex_replacement, _regex_text, count={node.max_replacements})")
        else:
            context.add_line(f"{result_var}, {count_var} = _regex_compiled.subn(_regex_replacement, _regex_text)")

        context.add_line(f"{changed_var} = {count_var} > 0")

        context.indentation.dedent()
        context.add_line("except re.error as _regex_e:")
        context.indentation.indent()
        context.add_line(f"{error_var} = f'Regex error: {{_regex_e}}'")
        context.add_line(f"{result_var} = _regex_text")
        context.indentation.dedent()
        context.add_line("except Exception as _regex_e:")
        context.indentation.indent()
        context.add_line(f"{error_var} = str(_regex_e)")
        context.add_line(f"{result_var} = _regex_text")
        context.indentation.dedent()

        context.add_blank_line()
        context.mark_node_processed(node.id)


class WhileLoopNodeEmitter(NodeEmitter):
    """
    Emitter for WhileLoop nodes - condition-based iteration.

    The WhileLoopNode enables visual condition-based iteration similar to Python's
    while loop. The loop continues executing the body as long as the condition
    evaluates to True.

    Generated code pattern:
    ```python
    while condition_expression:
        # loop_body nodes execute here
        # condition re-evaluated at loop start
    ```
    """

    @property
    def node_type(self) -> str:
        return "while_loop"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a WhileLoopNode.

        Creates a while loop structure that iterates as long as the condition
        is True. Variables defined inside the loop body are tracked as conditional
        since they depend on the loop executing at least once.

        Args:
            node: The WhileLoopNode to generate code for.
            context: The current generation context with indentation state.
            generator: The parent code generator for graph access.
        """
        from visualpython.nodes.models.while_loop_node import WhileLoopNode

        if not isinstance(node, WhileLoopNode):
            context.errors.append(f"Expected WhileLoopNode but got {type(node).__name__}")
            return

        # Get condition value or code
        condition_var = self.get_input_value(node, "condition", context, generator.graph)

        # Determine the condition expression
        if node.condition_code:
            # Use the condition code directly
            condition_expr = node.condition_code.strip()
        elif condition_var:
            condition_expr = condition_var
        else:
            condition_expr = "False"

        # Generate iteration counter variable
        iteration_var = context.generate_variable_name("while_iteration")
        context.set_output_variable(node.id, "iteration_count", iteration_var, track_scope=False)

        context.add_line(f"# While loop: {node.name}")
        context.add_line(f"{iteration_var} = 0")

        # Add max iterations check if configured
        if node.max_iterations > 0:
            max_iter_var = context.generate_variable_name("max_iterations")
            context.add_line(f"{max_iter_var} = {node.max_iterations}")
            context.add_line(f"while ({condition_expr}) and ({iteration_var} < {max_iter_var}):")
        else:
            context.add_line(f"while {condition_expr}:")

        # Loop body - enter scope for variable tracking
        context.indentation.indent()
        context.enter_scope(CodeContext.LOOP_BODY, branch_name="while_body")

        loop_body_nodes = generator.get_flow_connected_nodes(node.id, "loop_body")
        if loop_body_nodes:
            for body_node in loop_body_nodes:
                generator.emit_node(body_node, context)
        else:
            context.add_line("pass")

        # Increment iteration counter at end of loop body
        context.add_line(f"{iteration_var} += 1")

        # Exit loop body scope
        context.exit_scope()
        context.indentation.dedent()
        context.add_blank_line()

        # Handle completed flow (nodes after the loop)
        context.mark_node_processed(node.id)


class TryCatchNodeEmitter(NodeEmitter):
    """
    Emitter for TryCatch nodes - exception handling with try/except paths.

    The TryCatchNode enables visual exception handling similar to Python's try/except
    statement. Generated code wraps the try_body in a try block and routes to
    except_path if an exception is caught.
    """

    @property
    def node_type(self) -> str:
        return "try_catch"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a TryCatchNode.

        Creates a try/except structure and recursively generates code
        for each branch. The try_body is executed first, and if an exception
        matching the specified types is raised, execution continues to except_path.

        Args:
            node: The TryCatchNode to generate code for.
            context: The current generation context with indentation state.
            generator: The parent code generator for graph access.
        """
        from visualpython.nodes.models.try_catch_node import TryCatchNode

        if not isinstance(node, TryCatchNode):
            context.errors.append(f"Expected TryCatchNode but got {type(node).__name__}")
            return

        # Generate variable names for exception outputs
        exception_var = node.exception_variable or "e"
        exception_type_var = context.generate_variable_name("exception_type")

        # Store output variables for downstream nodes
        context.set_output_variable(node.id, "caught_exception", exception_var)
        context.set_output_variable(node.id, "exception_type_name", exception_type_var)

        context.add_line(f"# Try/Catch node: {node.name}")

        # Initialize exception tracking variables
        context.add_line(f"{exception_var} = None")
        context.add_line(f"{exception_type_var} = None")

        # Start the try block
        context.add_line("try:")

        # Try body - enter scope for variable tracking
        context.indentation.indent()
        context.enter_scope(CodeContext.IF_BRANCH, branch_name="try_body")

        try_body_nodes = generator.get_flow_connected_nodes(node.id, "try_body")
        if try_body_nodes:
            for body_node in try_body_nodes:
                self._emit_branch_flow(body_node, context, generator)
        else:
            context.add_line("pass")

        # Exit try body scope
        context.exit_scope()
        context.indentation.dedent()

        # Generate the except clause
        if node.catch_all:
            context.add_line(f"except Exception as {exception_var}:")
        else:
            # Get the exception types to catch
            exc_types = node.get_exception_type_list()
            if len(exc_types) == 1:
                context.add_line(f"except {exc_types[0]} as {exception_var}:")
            else:
                exc_tuple = ", ".join(exc_types)
                context.add_line(f"except ({exc_tuple}) as {exception_var}:")

        # Except body - enter scope for variable tracking
        context.indentation.indent()
        context.enter_scope(CodeContext.IF_BRANCH, branch_name="except_path")

        # Set the exception type name
        context.add_line(f"{exception_type_var} = type({exception_var}).__name__")

        except_path_nodes = generator.get_flow_connected_nodes(node.id, "except_path")
        if except_path_nodes:
            for except_node in except_path_nodes:
                self._emit_branch_flow(except_node, context, generator)
        else:
            context.add_line("pass")

        # Exit except body scope
        context.exit_scope()
        context.indentation.dedent()

        # Check if there's a finally block
        finally_path_nodes = generator.get_flow_connected_nodes(node.id, "finally_path")
        if finally_path_nodes:
            context.add_line("finally:")
            context.indentation.indent()
            context.enter_scope(CodeContext.IF_BRANCH, branch_name="finally_path")

            for finally_node in finally_path_nodes:
                self._emit_branch_flow(finally_node, context, generator)

            context.exit_scope()
            context.indentation.dedent()

        context.add_blank_line()
        context.mark_node_processed(node.id)

    def _emit_branch_flow(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Emit code for a branch (try body, except path, or finally path).

        Args:
            node: The starting node of the branch.
            context: The generation context.
            generator: The code generator.
        """
        if context.is_node_processed(node.id):
            return

        # Emit this node
        generator.emit_node(node, context)

        # Follow flow output to next nodes
        if node.node_type not in ("if", "for_loop", "try_catch"):
            flow_out_port = node.get_output_port("exec_out")
            if flow_out_port:
                next_nodes = generator.get_flow_connected_nodes(node.id, "exec_out")
                for next_node in next_nodes:
                    self._emit_branch_flow(next_node, context, generator)


class SubgraphNodeEmitter(NodeEmitter):
    """
    Emitter for Subgraph nodes - reusable subgraph execution.

    The SubgraphNode enables modular composition by allowing users to encapsulate
    groups of nodes as reusable functions. Generated code creates a function from
    the subgraph's internal nodes and calls it with the provided inputs.

    Generated code pattern:
    ```python
    def _subgraph_<id>(<inputs>):
        # Subgraph internal code
        return {<outputs>}

    _subgraph_result = _subgraph_<id>(<input_values>)
    output_1 = _subgraph_result['output_1']
    ```
    """

    @property
    def node_type(self) -> str:
        return "subgraph"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a SubgraphNode.

        Creates a function definition from the subgraph's internal graph and
        calls it with the provided input values.

        Args:
            node: The SubgraphNode to generate code for.
            context: The current generation context with indentation state.
            generator: The parent code generator for graph access.
        """
        from visualpython.nodes.models.subgraph_node import SubgraphNode

        if not isinstance(node, SubgraphNode):
            context.errors.append(f"Expected SubgraphNode but got {type(node).__name__}")
            return

        # Generate unique function name for this subgraph
        func_name = context.generate_variable_name(f"subgraph_{node.subgraph_name.replace(' ', '_').lower()}")

        context.add_line(f"# Subgraph: {node.name} ({node.subgraph_name})")

        # Circular reference detection for reference-based nodes
        _tracking_path = None
        if node.is_reference_based and node.subgraph_path:
            if node.subgraph_path in context.subgraph_inline_stack:
                context.errors.append(
                    f"Circular subgraph reference detected: '{node.subgraph_path}'"
                )
                context.add_line(f"# Error: Circular reference to '{node.subgraph_path}'")
                context.add_line("pass")
                context.mark_node_processed(node.id)
                return
            context.subgraph_inline_stack.add(node.subgraph_path)
            _tracking_path = node.subgraph_path

        # Get the internal graph data (reads from library file for reference-based nodes)
        graph_data = node.get_internal_graph_data()

        if graph_data is None:
            context.add_line(f"# Warning: Subgraph '{node.subgraph_name}' has no graph data")
            context.add_line("pass")
            context.mark_node_processed(node.id)
            if _tracking_path:
                context.subgraph_inline_stack.discard(_tracking_path)
            return

        # Collect input values
        input_values: Dict[str, str] = {}
        for port_name in node.input_mappings:
            input_var = self.get_input_value(node, port_name, context, generator.graph)
            if input_var:
                input_values[port_name] = input_var
            else:
                # Use default value if no connection
                input_port = node.get_input_port(port_name)
                if input_port and input_port.default_value is not None:
                    input_values[port_name] = repr(input_port.default_value)
                else:
                    input_values[port_name] = "None"

        # Generate function parameters
        param_names = list(node.input_mappings.keys())
        params_str = ", ".join(param_names) if param_names else ""

        # Generate the subgraph function definition
        context.add_line(f"def {func_name}({params_str}):")
        context.indentation.indent()

        # Enter function scope
        context.enter_scope(CodeContext.FUNCTION, branch_name="subgraph")

        # Generate subgraph body
        self._emit_subgraph_body(node, graph_data, context, generator)

        # Generate return statement with output values
        output_names = list(node.output_mappings.keys())
        if output_names:
            return_dict_items = ", ".join([f"'{name}': _{name}_output" for name in output_names])
            context.add_line(f"return {{{return_dict_items}}}")
        else:
            context.add_line("return {}")

        # Exit function scope
        context.exit_scope()
        context.indentation.dedent()
        context.add_blank_line()

        # Call the subgraph function with input values
        args_str = ", ".join([f"{name}={input_values.get(name, 'None')}" for name in param_names])
        result_var = context.generate_variable_name("subgraph_result")
        context.add_line(f"{result_var} = {func_name}({args_str})")

        # Extract output values
        for port_name in output_names:
            output_var = context.generate_variable_name(f"subgraph_out_{port_name}")
            context.set_output_variable(node.id, port_name, output_var)
            context.add_line(f"{output_var} = {result_var}.get('{port_name}')")

        context.add_blank_line()
        context.mark_node_processed(node.id)

        # Clean up circular reference tracking
        if _tracking_path:
            context.subgraph_inline_stack.discard(_tracking_path)

    def _emit_subgraph_body(
        self,
        subgraph_node: BaseNode,
        graph_data: Dict[str, Any],
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Emit the body of the subgraph function.

        This method fully compiles the nested workflow into inline Python code,
        supporting nested subgraphs (workflows within workflows).

        Args:
            subgraph_node: The SubgraphNode being processed.
            graph_data: The internal graph data.
            context: The generation context.
            generator: The code generator.
        """
        from visualpython.nodes.models.subgraph_node import SubgraphNode
        from visualpython.graph.graph import Graph
        from visualpython.nodes.registry import get_node_registry

        if not isinstance(subgraph_node, SubgraphNode):
            context.add_line("pass  # Invalid subgraph node")
            return

        nodes_data = graph_data.get("nodes", [])
        connections_data = graph_data.get("connections", [])

        # Build a mapping of node IDs to node data
        node_map: Dict[str, Dict[str, Any]] = {n["id"]: n for n in nodes_data}

        # Find SubgraphInput nodes and assign input values
        for port_name, input_node_id in subgraph_node.input_mappings.items():
            input_node_data = node_map.get(input_node_id)
            if input_node_data:
                # The input value is available as a function parameter
                output_var = context.generate_variable_name(f"input_{port_name}")
                context.set_output_variable(input_node_id, "value", output_var)
                context.add_line(f"{output_var} = {port_name}")

        # Build subgraph context mapping for tracking output variables
        subgraph_context_vars: Dict[str, Dict[str, str]] = {}

        # Process SubgraphInput nodes first to establish input variable mappings
        for node_data in nodes_data:
            if node_data.get("type") == "subgraph_input":
                node_id = node_data.get("id")
                port_name = node_data.get("properties", {}).get("port_name", "input")
                if node_id in [nid for nid in subgraph_node.input_mappings.values()]:
                    # Already handled above
                    pass
                else:
                    # Standalone input node - use default value
                    default_val = node_data.get("properties", {}).get("default_value")
                    output_var = context.generate_variable_name(f"input_{port_name}")
                    context.set_output_variable(node_id, "value", output_var)
                    context.add_line(f"{output_var} = {repr(default_val)}")
                subgraph_context_vars[node_id] = {"value": context.get_output_variable(node_id, "value")}

        # Build execution order from connections
        execution_order = self._get_subgraph_execution_order(nodes_data, connections_data)

        # Process nodes in execution order
        for node_id in execution_order:
            node_data = node_map.get(node_id)
            if not node_data:
                continue

            node_type = node_data.get("type")
            node_name = node_data.get("name", node_type)

            if node_type == "subgraph_input":
                # Already handled above
                continue

            if node_type == "subgraph_output":
                # Handle output collection
                port_name = node_data.get("properties", {}).get("port_name", "output")

                # Find what's connected to this output node's value input
                value_source = self._find_input_source(
                    node_id, "value", connections_data, context
                )

                # Set the output variable
                if value_source:
                    context.add_line(f"_{port_name}_output = {value_source}")
                else:
                    context.add_line(f"_{port_name}_output = None")
                continue

            if node_type == "subgraph":
                # Nested subgraph - recursively generate
                self._emit_nested_subgraph(node_data, connections_data, context, generator)
                continue

            if node_type == "code":
                # Code node - emit the code
                self._emit_code_node(node_data, connections_data, context)
                continue

            # For other node types, generate based on type
            self._emit_generic_node(node_data, connections_data, context)

        # If no output nodes were found, ensure we have placeholders
        for port_name in subgraph_node.output_mappings:
            output_var_name = f"_{port_name}_output"
            # Check if we already defined this variable
            if output_var_name not in context.get_generated_code():
                context.add_line(f"{output_var_name} = None  # No connection found")

    def _get_subgraph_execution_order(
        self,
        nodes_data: List[Dict[str, Any]],
        connections_data: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Determine execution order of nodes in a subgraph.

        Uses topological sort based on data flow connections.

        Args:
            nodes_data: List of node data dictionaries.
            connections_data: List of connection data dictionaries.

        Returns:
            List of node IDs in execution order.
        """
        from collections import deque

        # Build dependency graph
        node_ids = {n["id"] for n in nodes_data}
        in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
        outgoing: Dict[str, List[str]] = {nid: [] for nid in node_ids}

        for conn in connections_data:
            src = conn.get("source_node_id")
            tgt = conn.get("target_node_id")
            if src in node_ids and tgt in node_ids:
                outgoing[src].append(tgt)
                in_degree[tgt] += 1

        # Kahn's algorithm for topological sort
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        result = []

        while queue:
            node_id = queue.popleft()
            result.append(node_id)

            for successor in outgoing[node_id]:
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        return result

    def _find_input_source(
        self,
        node_id: str,
        port_name: str,
        connections_data: List[Dict[str, Any]],
        context: GenerationContext,
    ) -> Optional[str]:
        """
        Find the variable that provides a value to an input port.

        Args:
            node_id: The target node ID.
            port_name: The target port name.
            connections_data: Connection data from the subgraph.
            context: The generation context.

        Returns:
            Variable name if found, None otherwise.
        """
        for conn in connections_data:
            if (conn.get("target_node_id") == node_id and
                conn.get("target_port_name") == port_name):
                source_node_id = conn.get("source_node_id")
                source_port_name = conn.get("source_port_name")
                return context.get_output_variable(source_node_id, source_port_name)
        return None

    def _emit_code_node(
        self,
        node_data: Dict[str, Any],
        connections_data: List[Dict[str, Any]],
        context: GenerationContext,
    ) -> None:
        """
        Emit code for a Code node within a subgraph.

        Args:
            node_data: The node data dictionary.
            connections_data: Connection data from the subgraph.
            context: The generation context.
        """
        node_id = node_data.get("id")
        node_name = node_data.get("name", "Code")
        properties = node_data.get("properties", {})
        code = properties.get("code", "")

        if not code or not code.strip():
            context.add_line("pass  # Empty code node")
            return

        # Get input value if connected
        input_var = self._find_input_source(node_id, "value", connections_data, context)

        # Generate a variable for the result
        result_var = context.generate_variable_name("result")
        context.set_output_variable(node_id, "result", result_var)

        context.add_line(f"# Code node: {node_name}")

        # Create the inputs dict
        if input_var:
            context.add_line(f"inputs = {{'value': {input_var}}}")
        else:
            context.add_line("inputs = {}")

        context.add_line("outputs = {}")
        context.add_line("globals = _global_vars")

        # Emit the user's Python code
        code_lines = code.strip().split("\n")
        for line in code_lines:
            context.add_line(line)

        # Extract result
        context.add_line(f"{result_var} = outputs.get('result')")
        context.add_blank_line()

    def _emit_nested_subgraph(
        self,
        node_data: Dict[str, Any],
        parent_connections: List[Dict[str, Any]],
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Emit code for a nested subgraph within another subgraph.

        Args:
            node_data: The node data dictionary.
            parent_connections: Connections from the parent subgraph.
            context: The generation context.
            generator: The code generator.
        """
        node_id = node_data.get("id")
        properties = node_data.get("properties", {})
        subgraph_name = properties.get("subgraph_name", "Nested")
        is_reference_based = properties.get("is_reference_based", False)

        embedded_data = None
        if is_reference_based:
            subgraph_path = properties.get("subgraph_path")
            if subgraph_path:
                # Check for circular references
                if subgraph_path in context.subgraph_inline_stack:
                    context.errors.append(
                        f"Circular subgraph reference detected: '{subgraph_path}'"
                    )
                    context.add_line(f"# Error: Circular reference to '{subgraph_path}'")
                    context.add_line("pass")
                    return
                context.subgraph_inline_stack.add(subgraph_path)
                try:
                    import json as _json
                    with open(subgraph_path, "r", encoding="utf-8") as f:
                        file_data = _json.load(f)
                    if "graph" in file_data:
                        embedded_data = file_data["graph"]
                    elif "subgraph" in file_data:
                        embedded_data = file_data["subgraph"]
                    else:
                        embedded_data = file_data
                except Exception as e:
                    context.add_line(f"# Error: Could not load nested subgraph from '{subgraph_path}': {e}")
                    context.add_line("pass")
                    context.subgraph_inline_stack.discard(subgraph_path)
                    return
            else:
                context.add_line(f"# Warning: Reference-based subgraph '{subgraph_name}' has no path")
                context.add_line("pass")
                return
        else:
            embedded_data = properties.get("embedded_graph_data")

        if not embedded_data:
            context.add_line(f"# Warning: Nested subgraph '{subgraph_name}' has no graph data")
            context.add_line("pass")
            return

        # Generate function name
        func_name = context.generate_variable_name(f"nested_{subgraph_name.replace(' ', '_').lower()}")

        context.add_line(f"# Nested subgraph: {subgraph_name}")

        # Collect inputs
        input_mappings = properties.get("input_mappings", {})
        output_mappings = properties.get("output_mappings", {})

        input_values: Dict[str, str] = {}
        for port_name in input_mappings:
            input_var = self._find_input_source(node_id, port_name, parent_connections, context)
            input_values[port_name] = input_var if input_var else "None"

        # Generate function parameters
        param_names = list(input_mappings.keys())
        params_str = ", ".join(param_names) if param_names else ""

        # Generate the nested function
        context.add_line(f"def {func_name}({params_str}):")
        context.indentation.indent()
        context.enter_scope(CodeContext.FUNCTION, branch_name="nested_subgraph")

        # Recursively emit the nested subgraph body
        # Create a minimal SubgraphNode-like object for compatibility
        from visualpython.nodes.models.subgraph_node import SubgraphNode
        nested_subgraph = SubgraphNode(node_id=node_id, name=subgraph_name)
        nested_subgraph._input_mappings = input_mappings
        nested_subgraph._output_mappings = output_mappings
        nested_subgraph._embedded_graph_data = embedded_data
        nested_subgraph._subgraph_loaded = True

        self._emit_subgraph_body(nested_subgraph, embedded_data, context, generator)

        # Return statement
        output_names = list(output_mappings.keys())
        if output_names:
            return_dict_items = ", ".join([f"'{name}': _{name}_output" for name in output_names])
            context.add_line(f"return {{{return_dict_items}}}")
        else:
            context.add_line("return {}")

        context.exit_scope()
        context.indentation.dedent()
        context.add_blank_line()

        # Call the nested function
        args_str = ", ".join([f"{name}={input_values.get(name, 'None')}" for name in param_names])
        result_var = context.generate_variable_name("nested_result")
        context.add_line(f"{result_var} = {func_name}({args_str})")

        # Extract outputs
        for port_name in output_names:
            output_var = context.generate_variable_name(f"nested_out_{port_name}")
            context.set_output_variable(node_id, port_name, output_var)
            context.add_line(f"{output_var} = {result_var}.get('{port_name}')")

        context.add_blank_line()

        # Clean up circular reference tracking
        if is_reference_based and properties.get("subgraph_path"):
            context.subgraph_inline_stack.discard(properties["subgraph_path"])

    def _emit_generic_node(
        self,
        node_data: Dict[str, Any],
        connections_data: List[Dict[str, Any]],
        context: GenerationContext,
    ) -> None:
        """
        Emit code for a generic node type within a subgraph.

        Args:
            node_data: The node data dictionary.
            connections_data: Connection data from the subgraph.
            context: The generation context.
        """
        node_id = node_data.get("id")
        node_type = node_data.get("type", "unknown")
        node_name = node_data.get("name", node_type)

        context.add_line(f"# {node_type} node: {node_name}")

        # Generate a placeholder output variable
        result_var = context.generate_variable_name(f"{node_type}_result")
        context.set_output_variable(node_id, "result", result_var)
        context.set_output_variable(node_id, "value", result_var)
        context.set_output_variable(node_id, "output", result_var)

        context.add_line(f"{result_var} = None  # Placeholder for {node_type} node")


class SubgraphInputNodeEmitter(NodeEmitter):
    """
    Emitter for SubgraphInput nodes - input parameter definition within subgraphs.

    Within a subgraph, SubgraphInput nodes receive values passed from the parent
    SubgraphNode and make them available to downstream nodes.
    """

    @property
    def node_type(self) -> str:
        return "subgraph_input"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a SubgraphInputNode.

        Args:
            node: The SubgraphInputNode to generate code for.
            context: The current generation context.
            generator: The parent code generator.
        """
        from visualpython.nodes.models.subgraph_input_node import SubgraphInputNode

        if not isinstance(node, SubgraphInputNode):
            context.errors.append(f"Expected SubgraphInputNode but got {type(node).__name__}")
            return

        # Generate output variable for the input value
        value_var = context.generate_variable_name(f"subgraph_input_{node.port_name}")
        context.set_output_variable(node.id, "value", value_var)

        context.add_line(f"# Subgraph input: {node.port_name}")

        # The value should be provided by the subgraph execution context
        # For now, use the default value if available
        default_repr = repr(node.default_value) if node.default_value is not None else "None"
        context.add_line(f"{value_var} = _subgraph_inputs.get('{node.port_name}', {default_repr})")
        context.add_blank_line()

        context.mark_node_processed(node.id)


class SubgraphOutputNodeEmitter(NodeEmitter):
    """
    Emitter for SubgraphOutput nodes - output parameter definition within subgraphs.

    Within a subgraph, SubgraphOutput nodes capture values to be returned to the
    parent SubgraphNode.
    """

    @property
    def node_type(self) -> str:
        return "subgraph_output"

    def emit(
        self,
        node: BaseNode,
        context: GenerationContext,
        generator: CodeGenerator,
    ) -> None:
        """
        Generate code for a SubgraphOutputNode.

        Args:
            node: The SubgraphOutputNode to generate code for.
            context: The current generation context.
            generator: The parent code generator.
        """
        from visualpython.nodes.models.subgraph_output_node import SubgraphOutputNode

        if not isinstance(node, SubgraphOutputNode):
            context.errors.append(f"Expected SubgraphOutputNode but got {type(node).__name__}")
            return

        context.add_line(f"# Subgraph output: {node.port_name}")

        # Get the value being output
        value_var = self.get_input_value(node, "value", context, generator.graph)

        if value_var:
            context.add_line(f"_subgraph_outputs['{node.port_name}'] = {value_var}")
        else:
            context.add_line(f"_subgraph_outputs['{node.port_name}'] = None")

        context.add_blank_line()
        context.mark_node_processed(node.id)


@dataclass
class GenerationResult:
    """
    Result of code generation.

    Attributes:
        success: Whether generation completed without errors.
        code: The generated Python code.
        errors: List of error messages if any.
        warnings: List of warning messages if any.
        ast_valid: Whether the generated code passed AST validation.
    """

    success: bool
    code: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ast_valid: bool = False


class CodeGenerator:
    """
    Main code generator class that orchestrates the graph traversal
    and code generation process.

    The CodeGenerator:
    1. Validates the graph structure
    2. Traverses nodes in execution order
    3. Delegates code generation to node-specific emitters
    4. Combines generated code into a complete Python script

    Example:
        >>> graph = Graph()
        >>> # ... build graph ...
        >>> generator = CodeGenerator(graph)
        >>> result = generator.generate()
        >>> if result.success:
        ...     print(result.code)
    """

    def __init__(self, graph: Graph) -> None:
        """
        Initialize the code generator.

        Args:
            graph: The graph to generate code from.
        """
        self._graph = graph
        self._emitters: Dict[str, NodeEmitter] = {}
        self._context = GenerationContext()

        # Register default emitters
        self._register_default_emitters()

    def _register_default_emitters(self) -> None:
        """Register the built-in node emitters."""
        emitters: List[NodeEmitter] = [
            StartNodeEmitter(),
            EndNodeEmitter(),
            CodeNodeEmitter(),
            IfNodeEmitter(),
            ForLoopNodeEmitter(),
            WhileLoopNodeEmitter(),
            GetVariableNodeEmitter(),
            SetVariableNodeEmitter(),
            MergeNodeEmitter(),
            ThreadNodeEmitter(),
            ThreadJoinNodeEmitter(),
            TryCatchNodeEmitter(),
            DatabaseQueryNodeEmitter(),
            RegexMatchNodeEmitter(),
            RegexReplaceNodeEmitter(),
            SubgraphNodeEmitter(),
            SubgraphInputNodeEmitter(),
            SubgraphOutputNodeEmitter(),
        ]

        for emitter in emitters:
            self._emitters[emitter.node_type] = emitter

    @property
    def graph(self) -> Graph:
        """Get the graph being processed."""
        return self._graph

    def register_emitter(self, emitter: NodeEmitter) -> None:
        """
        Register a custom node emitter.

        Args:
            emitter: The emitter to register.
        """
        self._emitters[emitter.node_type] = emitter

    def get_emitter(self, node_type: str) -> Optional[NodeEmitter]:
        """
        Get the emitter for a node type.

        Args:
            node_type: The node type.

        Returns:
            The emitter if registered, None otherwise.
        """
        return self._emitters.get(node_type)

    def get_flow_connected_nodes(self, node_id: str, port_name: str) -> List[BaseNode]:
        """
        Get nodes connected to a flow output port.

        Args:
            node_id: The source node ID.
            port_name: The flow output port name.

        Returns:
            List of connected nodes in connection order.
        """
        connections = self._graph.get_connections_for_port(node_id, port_name, is_input=False)
        nodes: List[BaseNode] = []

        for conn in connections:
            target_node = self._graph.get_node(conn.target_node_id)
            if target_node and not self._context.is_node_processed(target_node.id):
                nodes.append(target_node)

        return nodes

    def emit_node(self, node: BaseNode, context: GenerationContext) -> None:
        """
        Emit code for a single node.

        Args:
            node: The node to generate code for.
            context: The generation context.
        """
        if context.is_node_processed(node.id):
            return

        emitter = self.get_emitter(node.node_type)
        if emitter is None:
            context.errors.append(f"No emitter registered for node type: {node.node_type}")
            context.add_line(f"# Unsupported node type: {node.node_type}")
            context.mark_node_processed(node.id)
            return

        emitter.emit(node, context, self)

    def _generate_preamble(self, context: GenerationContext) -> None:
        """Generate the script preamble (comments, setup code)."""
        context.add_line('"""')
        context.add_line(f"Generated Python script from: {self._graph.name}")
        context.add_line(f"Description: {self._graph.description}")
        context.add_line('"""')
        context.add_blank_line()
        context.add_line("# Global variable storage")
        context.add_line("_global_vars = {}")
        context.add_blank_line()

    def _validate_graph(self) -> List[str]:
        """
        Validate the graph before generation.

        Returns:
            List of validation errors.
        """
        errors: List[str] = []

        # Check for cycles
        if self._graph.has_cycle():
            errors.append("Graph contains cycles - cannot generate sequential code")

        # Check for start node
        start_nodes = self._graph.get_nodes_by_type("start")
        if not start_nodes:
            errors.append("Graph must have at least one Start node")

        # Validate all nodes
        graph_errors = self._graph.validate()
        errors.extend(graph_errors)

        return errors

    def generate(self) -> GenerationResult:
        """
        Generate Python code from the graph.

        Uses AST validation to verify the generated code syntax before
        returning. This catches compilation errors early in the process.
        Tracks variable scopes to detect potential undefined variable errors.

        Returns:
            GenerationResult containing the generated code and any errors.
        """
        # Reset context
        self._context.reset()

        # Initialize global scope for variable tracking
        self._context.scope_manager.enter_scope(ScopeType.GLOBAL)

        # Validate graph
        validation_errors = self._validate_graph()
        if validation_errors:
            return GenerationResult(
                success=False,
                code="",
                errors=validation_errors,
                ast_valid=False,
            )

        # Generate preamble
        self._generate_preamble(self._context)

        # Get execution order using flow-based traversal from start nodes
        start_nodes = self._graph.get_nodes_by_type("start")

        # Process each start node and follow the flow
        for start_node in start_nodes:
            self._emit_flow_from_node(start_node, self._context)

        # Check for any generation errors
        if self._context.errors:
            return GenerationResult(
                success=False,
                code=self._context.get_generated_code(),
                errors=self._context.errors,
                ast_valid=False,
            )

        # Validate generated code using AST
        generated_code = self._context.get_generated_code()
        ast_result = validate_generated_code(generated_code)

        if not ast_result.valid:
            # Add AST validation errors to the result
            ast_errors = [f"Generated code syntax error: {e}" for e in ast_result.error_messages]
            return GenerationResult(
                success=False,
                code=generated_code,
                errors=ast_errors,
                ast_valid=False,
            )

        # Collect scope-related warnings
        scope_warnings = self._context.get_scope_warnings()

        return GenerationResult(
            success=True,
            code=generated_code,
            errors=[],
            warnings=scope_warnings,
            ast_valid=True,
        )

    def _emit_flow_from_node(self, node: BaseNode, context: GenerationContext) -> None:
        """
        Emit code following the execution flow from a node.

        Args:
            node: The starting node.
            context: The generation context.
        """
        if context.is_node_processed(node.id):
            return

        # Emit this node
        self.emit_node(node, context)

        # Follow flow output to next nodes (unless this is a control flow node)
        # Control flow nodes (if, for, while, try_catch) handle their own flow traversal
        if node.node_type not in ("if", "for_loop", "while_loop", "try_catch"):
            # Get flow output port and follow connections
            flow_out_port = node.get_output_port("exec_out")
            if flow_out_port:
                next_nodes = self.get_flow_connected_nodes(node.id, "exec_out")
                for next_node in next_nodes:
                    self._emit_flow_from_node(next_node, context)

        # For loop nodes: handle the 'completed' flow (code that runs after the loop)
        if node.node_type == "for_loop":
            completed_nodes = self.get_flow_connected_nodes(node.id, "completed")
            for completed_node in completed_nodes:
                self._emit_flow_from_node(completed_node, context)

        # While loop nodes: handle the 'completed' flow (code that runs after the loop)
        if node.node_type == "while_loop":
            completed_nodes = self.get_flow_connected_nodes(node.id, "completed")
            for completed_node in completed_nodes:
                self._emit_flow_from_node(completed_node, context)
