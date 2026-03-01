"""
AST-based validation for Python code syntax.

This module provides the ASTValidator class that uses Python's ast module to
validate generated code syntax before execution. It catches compilation errors
early in the process and provides detailed error information.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional

from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class ValidationMode(Enum):
    """Mode for code validation."""

    EXEC = auto()
    """Validate as a sequence of statements (module mode)."""

    EVAL = auto()
    """Validate as a single expression."""


@dataclass
class ValidationError:
    """
    Represents a syntax or validation error found in code.

    Attributes:
        message: Human-readable error description.
        line: Line number where the error occurred (1-based).
        column: Column number where the error occurred (1-based).
        end_line: End line number for multi-line errors.
        end_column: End column number for errors spanning multiple characters.
        code_snippet: The problematic code snippet if available.
    """

    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    code_snippet: Optional[str] = None

    def __str__(self) -> str:
        """Format the error as a human-readable string."""
        location = ""
        if self.line is not None:
            location = f" at line {self.line}"
            if self.column is not None:
                location += f", column {self.column}"

        result = f"Syntax error{location}: {self.message}"

        if self.code_snippet:
            result += f"\n  Code: {self.code_snippet}"

        return result


@dataclass
class ValidationResult:
    """
    Result of AST validation.

    Attributes:
        valid: Whether the code passed validation.
        errors: List of validation errors if any.
        ast_tree: The parsed AST tree if validation succeeded.
    """

    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    ast_tree: Optional[ast.AST] = None

    @property
    def error_messages(self) -> List[str]:
        """Get all error messages as a list of strings."""
        return [str(e) for e in self.errors]


class ASTValidator:
    """
    Validates Python code using the ast module.

    The ASTValidator parses Python code into an Abstract Syntax Tree (AST)
    to catch syntax errors before runtime execution. This provides:
    - Early detection of syntax errors
    - Detailed error location information (line, column)
    - Prevention of invalid code from reaching exec()

    Example:
        >>> validator = ASTValidator()
        >>> result = validator.validate("x = 1 + 2")
        >>> print(result.valid)
        True
        >>> result = validator.validate("x = ")
        >>> print(result.valid)
        False
        >>> print(result.errors[0])
        Syntax error at line 1, column 5: unexpected EOF while parsing
    """

    def validate(
        self,
        code: str,
        mode: ValidationMode = ValidationMode.EXEC,
        filename: str = "<code>",
    ) -> ValidationResult:
        """
        Validate Python code syntax using ast.parse().

        Args:
            code: The Python code to validate.
            mode: Validation mode - EXEC for statements, EVAL for expressions.
            filename: Filename to use in error messages.

        Returns:
            ValidationResult containing validation status and any errors.
        """
        if not code or not code.strip():
            return ValidationResult(
                valid=False,
                errors=[ValidationError(message="Code cannot be empty")],
            )

        parse_mode = "exec" if mode == ValidationMode.EXEC else "eval"

        try:
            tree = ast.parse(code, filename=filename, mode=parse_mode)
            return ValidationResult(valid=True, ast_tree=tree)

        except SyntaxError as e:
            error = self._syntax_error_to_validation_error(e, code)
            return ValidationResult(valid=False, errors=[error])

        except ValueError as e:
            # ValueError can be raised for certain malformed strings
            logger.debug("AST validation error: %s", e)
            return ValidationResult(
                valid=False,
                errors=[ValidationError(message=f"Invalid code: {str(e)}")],
            )

    def validate_expression(
        self,
        code: str,
        filename: str = "<expression>",
    ) -> ValidationResult:
        """
        Validate code as a single Python expression.

        This is useful for validating conditions in if statements,
        loop conditions, etc.

        Args:
            code: The expression code to validate.
            filename: Filename to use in error messages.

        Returns:
            ValidationResult containing validation status and any errors.
        """
        return self.validate(code, mode=ValidationMode.EVAL, filename=filename)

    def validate_statements(
        self,
        code: str,
        filename: str = "<code>",
    ) -> ValidationResult:
        """
        Validate code as a sequence of statements.

        This is the standard mode for validating user code blocks
        or generated Python scripts.

        Args:
            code: The code to validate.
            filename: Filename to use in error messages.

        Returns:
            ValidationResult containing validation status and any errors.
        """
        return self.validate(code, mode=ValidationMode.EXEC, filename=filename)

    def _syntax_error_to_validation_error(
        self,
        error: SyntaxError,
        code: str,
    ) -> ValidationError:
        """
        Convert a Python SyntaxError to a ValidationError with context.

        Args:
            error: The SyntaxError to convert.
            code: The original code for extracting snippets.

        Returns:
            A ValidationError with detailed information.
        """
        # Extract line and column information
        line = error.lineno
        column = error.offset
        end_line = getattr(error, "end_lineno", None)
        end_column = getattr(error, "end_offset", None)

        # Get the code snippet for context
        code_snippet = None
        if line is not None:
            lines = code.split("\n")
            if 0 < line <= len(lines):
                code_snippet = lines[line - 1].strip()
                # Truncate long lines
                if len(code_snippet) > 50:
                    code_snippet = code_snippet[:47] + "..."

        return ValidationError(
            message=error.msg or "Invalid syntax",
            line=line,
            column=column,
            end_line=end_line,
            end_column=end_column,
            code_snippet=code_snippet,
        )


def validate_python_code(
    code: str,
    mode: ValidationMode = ValidationMode.EXEC,
) -> ValidationResult:
    """
    Convenience function to validate Python code.

    Args:
        code: The Python code to validate.
        mode: Validation mode - EXEC for statements, EVAL for expressions.

    Returns:
        ValidationResult containing validation status and any errors.

    Example:
        >>> result = validate_python_code("print('hello')")
        >>> print(result.valid)
        True
        >>> result = validate_python_code("x ==== y")
        >>> print(result.valid)
        False
    """
    validator = ASTValidator()
    return validator.validate(code, mode=mode)


def validate_generated_code(code: str) -> ValidationResult:
    """
    Validate generated Python code before execution.

    This function is specifically designed for validating code that has been
    generated by the CodeGenerator. It validates the code as a complete
    Python module.

    Args:
        code: The generated Python code to validate.

    Returns:
        ValidationResult containing validation status and any errors.
    """
    validator = ASTValidator()
    return validator.validate(code, mode=ValidationMode.EXEC, filename="<generated>")


def validate_user_code(code: str) -> ValidationResult:
    """
    Validate user-written code from CodeNodes.

    This function validates code that users write in CodeNode blocks.
    It validates as statements and uses a descriptive filename.

    Args:
        code: The user code to validate.

    Returns:
        ValidationResult containing validation status and any errors.
    """
    validator = ASTValidator()
    return validator.validate(code, mode=ValidationMode.EXEC, filename="<user_code>")


def validate_condition_code(code: str) -> ValidationResult:
    """
    Validate condition code used in IfNode or loops.

    Conditions are evaluated as expressions, not statements.

    Args:
        code: The condition expression to validate.

    Returns:
        ValidationResult containing validation status and any errors.
    """
    validator = ASTValidator()
    return validator.validate(code, mode=ValidationMode.EVAL, filename="<condition>")
