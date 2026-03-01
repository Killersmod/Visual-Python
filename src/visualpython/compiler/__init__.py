"""Compiler module for converting node graphs to Python code."""

from visualpython.compiler.code_generator import (
    CodeGenerator,
    CodeContext,
    GenerationContext,
    GenerationError,
    GenerationResult,
    IndentationManager,
    NodeEmitter,
    # Node emitters
    StartNodeEmitter,
    EndNodeEmitter,
    CodeNodeEmitter,
    IfNodeEmitter,
    ForLoopNodeEmitter,
    GetVariableNodeEmitter,
    SetVariableNodeEmitter,
)

from visualpython.compiler.variable_scope import (
    VariableScopeManager,
    ScopeType,
    VariableInfo,
    Scope,
    ScopeAccessError,
)

from visualpython.compiler.graph_validator import (
    GraphValidator,
    ValidationResult,
    ValidationIssue,
    ValidationSeverity,
    CycleInfo,
    validate_graph,
    validate_graph_for_compilation,
)

__all__ = [
    # Main classes
    "CodeGenerator",
    "GenerationResult",
    "GenerationError",
    # Graph validation
    "GraphValidator",
    "ValidationResult",
    "ValidationIssue",
    "ValidationSeverity",
    "CycleInfo",
    "validate_graph",
    "validate_graph_for_compilation",
    # Context and utilities
    "GenerationContext",
    "CodeContext",
    "IndentationManager",
    # Base emitter
    "NodeEmitter",
    # Node emitters
    "StartNodeEmitter",
    "EndNodeEmitter",
    "CodeNodeEmitter",
    "IfNodeEmitter",
    "ForLoopNodeEmitter",
    "GetVariableNodeEmitter",
    "SetVariableNodeEmitter",
    # Variable scope management
    "VariableScopeManager",
    "ScopeType",
    "VariableInfo",
    "Scope",
    "ScopeAccessError",
]
