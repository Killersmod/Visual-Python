"""
HTTP request node model for making HTTP requests.

This module defines the HTTPRequestNode class, which makes HTTP requests
with configurable URL, method, headers, and body.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from visualpython.nodes.models.base_node import BaseNode, Position
from visualpython.nodes.models.port import InputPort, OutputPort, PortType
from visualpython.utils.logging import get_logger

logger = get_logger(__name__)


class HTTPRequestNode(BaseNode):
    """
    A node that makes HTTP requests.

    The HTTPRequestNode makes HTTP requests to a specified URL with
    configurable method, headers, and body. It supports GET, POST, PUT,
    PATCH, and DELETE methods.

    The configuration can be:
    - Set directly on the node (via properties)
    - Provided dynamically through input ports

    Attributes:
        url: The URL to send the request to.
        method: The HTTP method (GET, POST, PUT, PATCH, DELETE).
        headers: Dictionary of HTTP headers.
        body: The request body (for POST, PUT, PATCH).
        timeout: Request timeout in seconds.

    Example:
        >>> node = HTTPRequestNode(url="https://api.example.com/data")
        >>> result = node.execute({})
        >>> result['success']
        True
        >>> result['status_code']
        200
    """

    # Class-level metadata
    node_type: str = "http_request"
    """Unique identifier for HTTP request nodes."""

    node_category: str = "Network"
    """Category for organizing in the UI."""

    node_color: str = "#2196F3"
    """Blue color for network operations."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        name: Optional[str] = None,
        position: Optional[Position] = None,
        url: str = "",
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: str = "",
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize a new HTTPRequestNode instance.

        Args:
            node_id: Optional unique identifier. If not provided, a UUID will be generated.
            name: Optional display name. If not provided, defaults to 'Http Request'.
            position: Optional initial position. If not provided, defaults to (0, 0).
            url: The URL to send the request to.
            method: The HTTP method (GET, POST, PUT, PATCH, DELETE).
            headers: Dictionary of HTTP headers.
            body: The request body for POST/PUT/PATCH requests.
            timeout: Request timeout in seconds.
        """
        self._url: str = url
        self._method: str = method.upper()
        self._headers: Dict[str, str] = headers or {}
        self._body: str = body
        self._timeout: float = timeout
        super().__init__(node_id, name, position)

    def _setup_ports(self) -> None:
        """
        Set up the input and output ports for the HTTP request node.

        The HTTP request node has:
        - An execution flow input port (for controlling execution order)
        - A url input port (optional, for dynamic URLs)
        - A method input port (optional, for dynamic HTTP method)
        - A headers input port (optional, for dynamic headers)
        - A body input port (optional, for dynamic request body)
        - A timeout input port (optional, for dynamic timeout)
        - An execution flow output port (for chaining execution)
        - A response_body output port with the response content
        - A status_code output port with the HTTP status code
        - A response_headers output port with response headers
        - A success output port indicating whether the request succeeded
        - An error_message output port with error details if failed
        """
        # Execution flow ports
        self.add_input_port(InputPort(
            name="exec_in",
            port_type=PortType.FLOW,
            description="Execution flow input",
            required=False,
        ))
        self.add_output_port(OutputPort(
            name="exec_out",
            port_type=PortType.FLOW,
            description="Execution flow output",
        ))

        # URL input (optional - allows dynamic URLs)
        self.add_input_port(InputPort(
            name="url",
            port_type=PortType.STRING,
            description="URL to send the request to (overrides configured URL)",
            required=False,
            display_hint=self._url,
        ))

        # Method input (optional - allows dynamic method)
        self.add_input_port(InputPort(
            name="method",
            port_type=PortType.STRING,
            description="HTTP method: GET, POST, PUT, PATCH, DELETE (overrides configured method)",
            required=False,
            display_hint=self._method,
        ))

        # Headers input (optional - allows dynamic headers)
        self.add_input_port(InputPort(
            name="headers",
            port_type=PortType.DICT,
            description="HTTP headers as a dictionary (merged with configured headers)",
            required=False,
        ))

        # Body input (optional - allows dynamic body)
        self.add_input_port(InputPort(
            name="body",
            port_type=PortType.STRING,
            description="Request body for POST/PUT/PATCH requests (overrides configured body)",
            required=False,
            display_hint=self._body,
        ))

        # Timeout input (optional - allows dynamic timeout)
        self.add_input_port(InputPort(
            name="timeout",
            port_type=PortType.FLOAT,
            description="Request timeout in seconds (overrides configured timeout)",
            required=False,
            display_hint=self._timeout,
        ))

        # Output ports
        self.add_output_port(OutputPort(
            name="response_body",
            port_type=PortType.STRING,
            description="The response body from the server",
        ))
        self.add_output_port(OutputPort(
            name="status_code",
            port_type=PortType.INTEGER,
            description="HTTP status code (e.g., 200, 404, 500)",
        ))
        self.add_output_port(OutputPort(
            name="response_headers",
            port_type=PortType.DICT,
            description="Response headers as a dictionary",
        ))
        self.add_output_port(OutputPort(
            name="success",
            port_type=PortType.BOOLEAN,
            description="Whether the request was successful (status code 2xx)",
        ))
        self.add_output_port(OutputPort(
            name="error_message",
            port_type=PortType.STRING,
            description="Error message if the request failed",
        ))

    @property
    def url(self) -> str:
        """Get the configured URL."""
        return self._url

    @url.setter
    def url(self, value: str) -> None:
        """
        Set the URL to send requests to.

        Args:
            value: The URL.
        """
        self._url = value

    @property
    def method(self) -> str:
        """Get the configured HTTP method."""
        return self._method

    @method.setter
    def method(self, value: str) -> None:
        """
        Set the HTTP method.

        Args:
            value: The HTTP method (GET, POST, PUT, PATCH, DELETE).
        """
        self._method = value.upper()

    @property
    def headers(self) -> Dict[str, str]:
        """Get the configured headers."""
        return self._headers.copy()

    @headers.setter
    def headers(self, value: Dict[str, str]) -> None:
        """
        Set the HTTP headers.

        Args:
            value: Dictionary of headers.
        """
        self._headers = value or {}

    @property
    def body(self) -> str:
        """Get the configured request body."""
        return self._body

    @body.setter
    def body(self, value: str) -> None:
        """
        Set the request body.

        Args:
            value: The request body string.
        """
        self._body = value

    @property
    def timeout(self) -> float:
        """Get the configured timeout."""
        return self._timeout

    @timeout.setter
    def timeout(self, value: float) -> None:
        """
        Set the request timeout.

        Args:
            value: Timeout in seconds.
        """
        self._timeout = value

    def validate(self) -> List[str]:
        """
        Validate the node's configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: List[str] = []

        # URL is required (either configured or via input port)
        if not self._url:
            # Check if url input port is connected
            url_port = self.get_input_port("url")
            if url_port and not url_port.is_connected():
                errors.append(
                    "URL must be configured or provided via input port"
                )

        # Validate method
        valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        if self._method and self._method not in valid_methods:
            errors.append(
                f"Invalid HTTP method '{self._method}'. Must be one of: {', '.join(sorted(valid_methods))}"
            )

        # Validate timeout
        if self._timeout <= 0:
            errors.append("Timeout must be greater than 0")

        return errors

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make the HTTP request.

        The request configuration is determined by:
        1. Input port values (if provided)
        2. Configured properties (as fallback)

        Args:
            inputs: Dictionary mapping input port names to their values.

        Returns:
            Dictionary containing:
                - 'response_body': The response body (empty string if failed)
                - 'status_code': HTTP status code (0 if request failed before getting response)
                - 'response_headers': Response headers as dictionary
                - 'success': Boolean indicating if the request succeeded (2xx status)
                - 'error_message': Error message if failed (empty string if success)

        Raises:
            ValueError: If no URL is specified.
        """
        # Determine the URL to use
        url = inputs.get("url", self._url)
        if not url:
            raise ValueError("No URL specified")

        # Determine method
        method = inputs.get("method", self._method)
        if not method:
            method = "GET"
        method = method.upper()

        # Determine headers (merge configured with input)
        headers = self._headers.copy()
        input_headers = inputs.get("headers")
        if input_headers and isinstance(input_headers, dict):
            headers.update(input_headers)

        # Determine body
        body = inputs.get("body", self._body)

        # Determine timeout
        timeout = inputs.get("timeout", self._timeout)
        if not timeout or timeout <= 0:
            timeout = 30.0

        try:
            # Prepare the request
            data = None
            if body and method in ("POST", "PUT", "PATCH"):
                data = body.encode("utf-8")
                if "Content-Type" not in headers:
                    # Try to detect JSON
                    try:
                        json.loads(body)
                        headers["Content-Type"] = "application/json"
                    except (json.JSONDecodeError, TypeError):
                        headers["Content-Type"] = "application/x-www-form-urlencoded"

            request = Request(
                url,
                data=data,
                headers=headers,
                method=method,
            )

            # Make the request
            with urlopen(request, timeout=timeout) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                status_code = response.status
                response_headers = dict(response.headers)

            success = 200 <= status_code < 300

            return {
                "response_body": response_body,
                "status_code": status_code,
                "response_headers": response_headers,
                "success": success,
                "error_message": "",
            }

        except HTTPError as e:
            # HTTP error responses (4xx, 5xx)
            try:
                error_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                error_body = ""

            return {
                "response_body": error_body,
                "status_code": e.code,
                "response_headers": dict(e.headers) if e.headers else {},
                "success": False,
                "error_message": f"HTTP {e.code}: {e.reason}",
            }

        except URLError as e:
            # Network errors (connection refused, DNS failure, etc.)
            logger.error("HTTP request failed: %s", e, exc_info=True)
            return {
                "response_body": "",
                "status_code": 0,
                "response_headers": {},
                "success": False,
                "error_message": f"URL Error: {e.reason}",
            }

        except TimeoutError as e:
            logger.error("HTTP request failed: %s", e, exc_info=True)
            return {
                "response_body": "",
                "status_code": 0,
                "response_headers": {},
                "success": False,
                "error_message": f"Request timed out after {timeout} seconds",
            }

        except Exception as e:
            logger.error("HTTP request failed: %s", e, exc_info=True)
            return {
                "response_body": "",
                "status_code": 0,
                "response_headers": {},
                "success": False,
                "error_message": str(e),
            }

    def _get_serializable_properties(self) -> Dict[str, Any]:
        """
        Get HTTP request node specific properties for serialization.

        Returns:
            Dictionary containing the URL, method, headers, body, and timeout.
        """
        return {
            "url": self._url,
            "method": self._method,
            "headers": self._headers,
            "body": self._body,
            "timeout": self._timeout,
        }

    def _load_serializable_properties(self, properties: Dict[str, Any]) -> None:
        """
        Load HTTP request node specific properties from serialized data.

        Args:
            properties: Dictionary containing serialized properties.
        """
        self._url = properties.get("url", "")
        self._method = properties.get("method", "GET")
        self._headers = properties.get("headers", {})
        self._body = properties.get("body", "")
        self._timeout = properties.get("timeout", 30.0)

    def __repr__(self) -> str:
        """Get a detailed string representation of the HTTP request node."""
        return (
            f"{self.__class__.__name__}("
            f"id='{self._id[:8]}...', "
            f"name='{self._name}', "
            f"url='{self._url}', "
            f"method='{self._method}', "
            f"state={self._execution_state.name})"
        )
