"""
Variable scope management for code generation.

This module provides comprehensive variable scope tracking during code generation
to ensure proper variable accessibility across nodes and control flow structures.
Prevents undefined variable errors in generated code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from visualpython.compiler.code_generator import CodeContext


class ScopeType(Enum):
    """Types of variable scopes in generated code."""

    GLOBAL = auto()
    """Top-level script scope - variables accessible everywhere."""

    FUNCTION = auto()
    """Function-level scope - variables local to a function."""

    IF_BRANCH = auto()
    """If/else branch scope - variables may not be accessible outside."""

    LOOP_BODY = auto()
    """Loop body scope - variables defined inside loop iteration."""

    CONDITIONAL = auto()
    """Conditional scope where variable availability depends on runtime."""


@dataclass
class VariableInfo:
    """
    Information about a variable in the scope system.

    Attributes:
        name: The generated variable name.
        source_node_id: The node ID that created this variable.
        source_port_name: The port name that produced this variable.
        scope_level: The nesting level where variable was defined.
        scope_type: The type of scope where variable was defined.
        is_conditional: True if variable is only defined in some branches.
        defined_in_branches: Set of branch names where variable is defined.
    """

    name: str
    source_node_id: str
    source_port_name: str
    scope_level: int
    scope_type: ScopeType
    is_conditional: bool = False
    defined_in_branches: Set[str] = field(default_factory=set)

    @property
    def key(self) -> str:
        """Get the unique key for this variable."""
        return f"{self.source_node_id}.{self.source_port_name}"


@dataclass
class Scope:
    """
    Represents a single scope in the scope hierarchy.

    Attributes:
        scope_type: The type of this scope.
        level: The nesting level (0 = global).
        parent: Reference to parent scope (None for global).
        variables: Variables defined in this scope.
        branch_name: Name of the branch (e.g., 'true_branch', 'false_branch').
    """

    scope_type: ScopeType
    level: int
    parent: Optional[Scope] = None
    variables: Dict[str, VariableInfo] = field(default_factory=dict)
    branch_name: Optional[str] = None
    child_branches: List[Scope] = field(default_factory=list)

    def define_variable(self, var_info: VariableInfo) -> None:
        """
        Define a variable in this scope.

        Args:
            var_info: The variable information to store.
        """
        self.variables[var_info.key] = var_info

    def get_variable(self, key: str) -> Optional[VariableInfo]:
        """
        Get a variable from this scope or parent scopes.

        Args:
            key: The variable key (node_id.port_name).

        Returns:
            The variable info if found, None otherwise.
        """
        if key in self.variables:
            return self.variables[key]
        if self.parent:
            return self.parent.get_variable(key)
        return None

    def has_variable(self, key: str) -> bool:
        """Check if a variable exists in this scope or parent scopes."""
        return self.get_variable(key) is not None

    def has_variable_in_scope(self, key: str) -> bool:
        """Check if a variable exists in this exact scope (not parents)."""
        return key in self.variables

    def get_all_variable_keys(self) -> Set[str]:
        """Get all variable keys accessible from this scope."""
        keys = set(self.variables.keys())
        if self.parent:
            keys.update(self.parent.get_all_variable_keys())
        return keys


class ScopeAccessError(Exception):
    """Exception raised when a variable access would cause an undefined error."""

    def __init__(
        self,
        message: str,
        variable_name: str,
        node_id: Optional[str] = None,
        suggested_fix: Optional[str] = None,
    ) -> None:
        """
        Initialize a scope access error.

        Args:
            message: Error description.
            variable_name: The problematic variable name.
            node_id: Optional ID of the node where error occurred.
            suggested_fix: Optional suggested fix for the error.
        """
        self.variable_name = variable_name
        self.node_id = node_id
        self.suggested_fix = suggested_fix
        super().__init__(message)


class VariableScopeManager:
    """
    Manages variable scopes during code generation.

    This class tracks variable definitions and their scopes to:
    - Prevent undefined variable errors in generated code
    - Detect variables only defined in conditional branches
    - Generate proper initialization code for conditional variables
    - Track which variables are accessible at each point in code generation

    Example:
        >>> manager = VariableScopeManager()
        >>> manager.enter_scope(ScopeType.GLOBAL)
        >>> manager.define_variable("node1", "result", "var_1")
        >>> manager.enter_scope(ScopeType.IF_BRANCH, branch_name="true_branch")
        >>> manager.define_variable("node2", "output", "var_2")
        >>> manager.exit_scope()
        >>> # var_2 is now marked as conditional
        >>> accessible = manager.get_accessible_variables()
    """

    def __init__(self) -> None:
        """Initialize the scope manager."""
        self._scope_stack: List[Scope] = []
        self._global_scope: Optional[Scope] = None
        self._all_variables: Dict[str, VariableInfo] = {}
        self._warnings: List[str] = []
        self._conditional_initializations: Dict[str, str] = {}

    @property
    def current_scope(self) -> Optional[Scope]:
        """Get the current scope."""
        return self._scope_stack[-1] if self._scope_stack else None

    @property
    def current_level(self) -> int:
        """Get the current nesting level."""
        return len(self._scope_stack) - 1

    @property
    def is_in_conditional_scope(self) -> bool:
        """Check if currently in a conditional scope (if branch or loop)."""
        if not self.current_scope:
            return False
        return self.current_scope.scope_type in (
            ScopeType.IF_BRANCH,
            ScopeType.LOOP_BODY,
            ScopeType.CONDITIONAL,
        )

    def enter_scope(
        self,
        scope_type: ScopeType,
        branch_name: Optional[str] = None,
    ) -> Scope:
        """
        Enter a new scope.

        Args:
            scope_type: The type of scope to enter.
            branch_name: Optional name for conditional branches.

        Returns:
            The newly created scope.
        """
        level = len(self._scope_stack)
        parent = self._scope_stack[-1] if self._scope_stack else None

        scope = Scope(
            scope_type=scope_type,
            level=level,
            parent=parent,
            branch_name=branch_name,
        )

        if parent and scope_type == ScopeType.IF_BRANCH:
            parent.child_branches.append(scope)

        self._scope_stack.append(scope)

        if level == 0:
            self._global_scope = scope

        return scope

    def exit_scope(self) -> Optional[Scope]:
        """
        Exit the current scope.

        Returns:
            The scope that was exited, or None if no scope was active.
        """
        if not self._scope_stack:
            return None

        exited_scope = self._scope_stack.pop()

        # Mark variables defined in conditional scopes
        if exited_scope.scope_type in (ScopeType.IF_BRANCH, ScopeType.LOOP_BODY):
            for var_info in exited_scope.variables.values():
                var_info.is_conditional = True
                if exited_scope.branch_name:
                    var_info.defined_in_branches.add(exited_scope.branch_name)

        return exited_scope

    def define_variable(
        self,
        node_id: str,
        port_name: str,
        var_name: str,
    ) -> VariableInfo:
        """
        Define a variable in the current scope.

        Args:
            node_id: The ID of the node creating the variable.
            port_name: The name of the output port.
            var_name: The generated variable name.

        Returns:
            The created VariableInfo.

        Raises:
            RuntimeError: If no scope is currently active.
        """
        if not self.current_scope:
            raise RuntimeError("Cannot define variable without an active scope")

        var_info = VariableInfo(
            name=var_name,
            source_node_id=node_id,
            source_port_name=port_name,
            scope_level=self.current_level,
            scope_type=self.current_scope.scope_type,
        )

        self.current_scope.define_variable(var_info)
        self._all_variables[var_info.key] = var_info

        return var_info

    def get_variable(self, node_id: str, port_name: str) -> Optional[VariableInfo]:
        """
        Get a variable by its source node and port.

        Args:
            node_id: The source node ID.
            port_name: The source port name.

        Returns:
            The variable info if found, None otherwise.
        """
        key = f"{node_id}.{port_name}"
        return self._all_variables.get(key)

    def get_variable_name(self, node_id: str, port_name: str) -> Optional[str]:
        """
        Get the generated name of a variable.

        Args:
            node_id: The source node ID.
            port_name: The source port name.

        Returns:
            The variable name if found, None otherwise.
        """
        var_info = self.get_variable(node_id, port_name)
        return var_info.name if var_info else None

    def is_variable_accessible(
        self,
        node_id: str,
        port_name: str,
        check_conditional: bool = True,
    ) -> bool:
        """
        Check if a variable is accessible in the current scope.

        Args:
            node_id: The source node ID.
            port_name: The source port name.
            check_conditional: Whether to flag conditional variables as issues.

        Returns:
            True if the variable is safely accessible.
        """
        key = f"{node_id}.{port_name}"

        if not self.current_scope:
            return key in self._all_variables

        var_info = self.current_scope.get_variable(key)
        if not var_info:
            return False

        if check_conditional and var_info.is_conditional:
            # Variable might not be defined in all code paths
            return False

        return True

    def check_variable_access(
        self,
        node_id: str,
        port_name: str,
        accessing_node_id: str,
    ) -> List[str]:
        """
        Check if accessing a variable would cause issues and return warnings.

        Args:
            node_id: The source node ID of the variable.
            port_name: The source port name.
            accessing_node_id: The ID of the node trying to access the variable.

        Returns:
            List of warning messages (empty if access is safe).
        """
        warnings = []
        key = f"{node_id}.{port_name}"
        var_info = self._all_variables.get(key)

        if not var_info:
            warnings.append(
                f"Variable from {node_id}.{port_name} is not defined. "
                f"Ensure the source node executes before node {accessing_node_id}."
            )
            return warnings

        if var_info.is_conditional:
            warnings.append(
                f"Variable '{var_info.name}' from node {node_id} is only defined "
                f"in conditional branches ({', '.join(var_info.defined_in_branches)}). "
                f"It may be undefined when accessed by node {accessing_node_id}."
            )

        # Check scope hierarchy
        if self.current_scope:
            current_level = self.current_level
            if var_info.scope_level > current_level:
                warnings.append(
                    f"Variable '{var_info.name}' was defined in a nested scope "
                    f"(level {var_info.scope_level}) and may not be accessible "
                    f"at the current scope (level {current_level})."
                )

        return warnings

    def get_conditional_variables(self) -> List[VariableInfo]:
        """Get all variables that are only conditionally defined."""
        return [v for v in self._all_variables.values() if v.is_conditional]

    def get_variables_needing_initialization(self) -> Dict[str, str]:
        """
        Get variables that need pre-initialization to avoid undefined errors.

        Returns:
            Dict mapping variable names to their default initialization value.
        """
        init_needed: Dict[str, str] = {}

        for var_info in self._all_variables.values():
            if var_info.is_conditional:
                # Conditional variables need initialization with None
                init_needed[var_info.name] = "None"

        return init_needed

    def generate_initialization_code(self) -> List[str]:
        """
        Generate initialization code for conditional variables.

        Returns:
            List of initialization statements.
        """
        init_vars = self.get_variables_needing_initialization()
        if not init_vars:
            return []

        lines = ["# Initialize conditional variables to avoid undefined errors"]
        for var_name, default_value in sorted(init_vars.items()):
            lines.append(f"{var_name} = {default_value}")
        lines.append("")

        return lines

    def merge_branch_scopes(self, branches: List[Scope]) -> None:
        """
        Merge variables from parallel branches (e.g., if/else).

        Variables defined in all branches become non-conditional.
        Variables defined in only some branches remain conditional.

        Args:
            branches: List of branch scopes to merge.
        """
        if not branches:
            return

        # Find variables defined in all branches
        all_keys: Set[str] = set()
        for branch in branches:
            all_keys.update(branch.variables.keys())

        for key in all_keys:
            branches_with_var = [b for b in branches if key in b.variables]

            if len(branches_with_var) == len(branches):
                # Variable defined in all branches - not conditional
                var_info = branches_with_var[0].variables[key]
                var_info.is_conditional = False
                var_info.defined_in_branches.clear()
            else:
                # Variable only in some branches - remains conditional
                for branch in branches_with_var:
                    var_info = branch.variables[key]
                    var_info.is_conditional = True

    def get_scope_summary(self) -> Dict[str, any]:
        """
        Get a summary of the current scope state for debugging.

        Returns:
            Dictionary with scope information.
        """
        return {
            "current_level": self.current_level,
            "scope_stack_size": len(self._scope_stack),
            "total_variables": len(self._all_variables),
            "conditional_variables": len(self.get_conditional_variables()),
            "current_scope_type": (
                self.current_scope.scope_type.name if self.current_scope else None
            ),
        }

    def reset(self) -> None:
        """Reset the scope manager for a new generation."""
        self._scope_stack.clear()
        self._global_scope = None
        self._all_variables.clear()
        self._warnings.clear()
        self._conditional_initializations.clear()

    @property
    def warnings(self) -> List[str]:
        """Get all accumulated warnings."""
        return self._warnings.copy()

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self._warnings.append(message)
