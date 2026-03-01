"""
Template data model for VisualPython graph templates.

This module provides the GraphTemplate class that represents a pre-built
template graph that users can instantiate to accelerate development.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TemplateCategory(str, Enum):
    """Categories for organizing templates."""

    FILE_PROCESSING = "File Processing"
    WEB_SCRAPING = "Web Scraping"
    DATA_PROCESSING = "Data Processing"
    API_INTEGRATION = "API Integration"
    CONTROL_FLOW = "Control Flow"
    UTILITY = "Utility"


class TemplateDifficulty(str, Enum):
    """Difficulty levels for templates."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


@dataclass
class GraphTemplate:
    """
    A pre-built graph template that users can instantiate.

    Templates provide common patterns for tasks like file processing,
    web scraping, and data transformation.

    Attributes:
        template_id: Unique identifier for the template.
        name: Human-readable name for the template.
        description: Detailed description of what the template does.
        category: Category for organizing in the UI.
        difficulty: Difficulty level (beginner, intermediate, advanced).
        tags: List of searchable tags.
        author: Author of the template.
        version: Template version string.
        graph_data: The serialized graph data (nodes, connections, etc.).
        preview_description: Short description for preview in template browser.
    """

    template_id: str
    name: str
    description: str
    category: TemplateCategory
    graph_data: Dict[str, Any]
    difficulty: TemplateDifficulty = TemplateDifficulty.BEGINNER
    tags: List[str] = field(default_factory=list)
    author: str = "VisualPython Team"
    version: str = "1.0.0"
    preview_description: str = ""

    def __post_init__(self) -> None:
        """Validate template data after initialization."""
        if not self.template_id:
            raise ValueError("Template ID cannot be empty")
        if not self.name:
            raise ValueError("Template name cannot be empty")
        if not self.graph_data:
            raise ValueError("Template graph_data cannot be empty")

        # Use description as preview if not provided
        if not self.preview_description:
            self.preview_description = self.description[:100] + "..." if len(self.description) > 100 else self.description

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize the template to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "difficulty": self.difficulty.value,
            "tags": self.tags.copy(),
            "author": self.author,
            "version": self.version,
            "preview_description": self.preview_description,
            "graph_data": self.graph_data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GraphTemplate:
        """
        Create a template from a dictionary.

        Args:
            data: Dictionary containing template data.

        Returns:
            A new GraphTemplate instance.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        # Parse category
        category_value = data.get("category", TemplateCategory.UTILITY.value)
        try:
            category = TemplateCategory(category_value)
        except ValueError:
            category = TemplateCategory.UTILITY

        # Parse difficulty
        difficulty_value = data.get("difficulty", TemplateDifficulty.BEGINNER.value)
        try:
            difficulty = TemplateDifficulty(difficulty_value)
        except ValueError:
            difficulty = TemplateDifficulty.BEGINNER

        return cls(
            template_id=data["template_id"],
            name=data["name"],
            description=data.get("description", ""),
            category=category,
            difficulty=difficulty,
            tags=data.get("tags", []),
            author=data.get("author", "VisualPython Team"),
            version=data.get("version", "1.0.0"),
            preview_description=data.get("preview_description", ""),
            graph_data=data["graph_data"],
        )

    def matches_search(self, query: str) -> bool:
        """
        Check if the template matches a search query.

        Args:
            query: The search text to match against.

        Returns:
            True if the template matches the query.
        """
        query_lower = query.lower().strip()
        if not query_lower:
            return True

        searchable = [
            self.name.lower(),
            self.description.lower(),
            self.category.value.lower(),
            *[tag.lower() for tag in self.tags],
        ]

        return any(query_lower in text for text in searchable)
