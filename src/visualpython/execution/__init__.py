"""
Execution module for running compiled Python scripts.

This module provides the execution engine that runs visual Python scripts
using Python's exec() with proper context management.
"""

from visualpython.execution.case import (
    Case,
    InvalidVariableNameError,
    TypeValidationError,
    validate_variable_name,
)
from visualpython.execution.context import (
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    NodeExecutionRecord,
)
from visualpython.execution.engine import (
    ExecutionEngine,
    ExecutionError,
    execute_code,
    execute_graph,
    get_current_case,
)
from visualpython.execution.error_report import (
    ErrorCategory,
    ErrorReport,
    NodeLocation,
)
from visualpython.execution.output_capture import (
    OutputCapture,
    OutputCaptureManager,
)
from visualpython.execution.state_manager import (
    ExecutionState,
    ExecutionStateManager,
)
from visualpython.execution.type_info import (
    PortTypeInfo,
    TypeInfo,
    TypeKind,
    TypeMismatch,
)
from visualpython.execution.type_inference import (
    InferenceResult,
    TypeInferenceEngine,
)

__all__ = [
    # Case context
    "Case",
    "InvalidVariableNameError",
    "TypeValidationError",
    "validate_variable_name",
    # Context
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionStatus",
    "NodeExecutionRecord",
    # Engine
    "ExecutionEngine",
    "ExecutionError",
    "execute_code",
    "execute_graph",
    "get_current_case",
    # Error handling
    "ErrorCategory",
    "ErrorReport",
    "NodeLocation",
    # Output capture
    "OutputCapture",
    "OutputCaptureManager",
    # State management
    "ExecutionState",
    "ExecutionStateManager",
    # Type inference
    "InferenceResult",
    "PortTypeInfo",
    "TypeInfo",
    "TypeInferenceEngine",
    "TypeKind",
    "TypeMismatch",
]
