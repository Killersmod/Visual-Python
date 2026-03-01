"""
Template registry for centralized management of graph templates.

This module provides a registry that tracks all available templates,
their metadata, and provides methods for creating graphs from templates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from visualpython.templates.template import GraphTemplate, TemplateCategory, TemplateDifficulty
from visualpython.utils.logging import get_logger

if TYPE_CHECKING:
    from visualpython.graph.graph import Graph

logger = get_logger(__name__)


class TemplateRegistry:
    """
    Registry for managing available graph templates.

    The TemplateRegistry serves as a centralized location for registering
    templates and creating graph instances from them. It provides:
    - Registration of templates from dictionaries or JSON files
    - Loading templates from a preset directory
    - Grouping of templates by category
    - Search and filtering of templates
    - Factory method for creating graphs from templates

    Example:
        >>> registry = TemplateRegistry()
        >>> registry.load_default_templates()
        >>> templates = registry.get_templates_by_category(TemplateCategory.FILE_PROCESSING)
        >>> graph = registry.create_graph_from_template("read_write_file")
    """

    _instance: Optional[TemplateRegistry] = None

    def __new__(cls) -> TemplateRegistry:
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
        self._templates: Dict[str, GraphTemplate] = {}
        self._categories: Dict[TemplateCategory, List[str]] = {}
        self._presets_loaded = False

    @classmethod
    def get_instance(cls) -> TemplateRegistry:
        """Get the singleton instance of the registry."""
        return cls()

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (mainly for testing)."""
        cls._instance = None

    def register(self, template: GraphTemplate) -> None:
        """
        Register a template with the registry.

        Args:
            template: The template to register.

        Raises:
            ValueError: If a template with the same ID already exists.
        """
        if template.template_id in self._templates:
            raise ValueError(f"Template with ID '{template.template_id}' already exists")

        self._templates[template.template_id] = template

        # Update category grouping
        if template.category not in self._categories:
            self._categories[template.category] = []
        self._categories[template.category].append(template.template_id)

    def register_from_dict(self, data: Dict[str, Any]) -> GraphTemplate:
        """
        Register a template from a dictionary.

        Args:
            data: Dictionary containing template data.

        Returns:
            The registered GraphTemplate.

        Raises:
            ValueError: If the data is invalid or template ID already exists.
        """
        template = GraphTemplate.from_dict(data)
        self.register(template)
        return template

    def register_from_json(self, file_path: Path) -> GraphTemplate:
        """
        Register a template from a JSON file.

        Args:
            file_path: Path to the JSON file containing template data.

        Returns:
            The registered GraphTemplate.

        Raises:
            ValueError: If the file is invalid or template ID already exists.
            FileNotFoundError: If the file doesn't exist.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.register_from_dict(data)

    def unregister(self, template_id: str) -> bool:
        """
        Unregister a template from the registry.

        Args:
            template_id: The ID of the template to unregister.

        Returns:
            True if the template was unregistered, False if not found.
        """
        if template_id not in self._templates:
            return False

        template = self._templates[template_id]
        del self._templates[template_id]

        # Update category grouping
        if template.category in self._categories:
            if template_id in self._categories[template.category]:
                self._categories[template.category].remove(template_id)
            if not self._categories[template.category]:
                del self._categories[template.category]

        return True

    def get_template(self, template_id: str) -> Optional[GraphTemplate]:
        """
        Get a template by its ID.

        Args:
            template_id: The ID of the template to find.

        Returns:
            The GraphTemplate if found, None otherwise.
        """
        return self._templates.get(template_id)

    def get_all_templates(self) -> List[GraphTemplate]:
        """Get all registered templates."""
        return list(self._templates.values())

    def get_categories(self) -> List[TemplateCategory]:
        """Get all categories that have templates."""
        return sorted(self._categories.keys(), key=lambda c: c.value)

    def get_templates_in_category(self, category: TemplateCategory) -> List[GraphTemplate]:
        """
        Get all templates in a specific category.

        Args:
            category: The category to filter by.

        Returns:
            List of templates in the category.
        """
        template_ids = self._categories.get(category, [])
        return [self._templates[tid] for tid in template_ids if tid in self._templates]

    def get_templates_by_category(self) -> Dict[TemplateCategory, List[GraphTemplate]]:
        """
        Get all templates grouped by category.

        Returns:
            Dictionary mapping categories to lists of templates.
        """
        result: Dict[TemplateCategory, List[GraphTemplate]] = {}
        for category in self.get_categories():
            result[category] = self.get_templates_in_category(category)
        return result

    def get_templates_by_difficulty(self, difficulty: TemplateDifficulty) -> List[GraphTemplate]:
        """
        Get all templates of a specific difficulty level.

        Args:
            difficulty: The difficulty level to filter by.

        Returns:
            List of templates with the specified difficulty.
        """
        return [t for t in self._templates.values() if t.difficulty == difficulty]

    def search_templates(self, query: str) -> List[GraphTemplate]:
        """
        Search templates by name, description, or tags.

        Args:
            query: The search query.

        Returns:
            List of templates matching the search.
        """
        return [t for t in self._templates.values() if t.matches_search(query)]

    def is_registered(self, template_id: str) -> bool:
        """Check if a template is registered."""
        return template_id in self._templates

    def create_graph_from_template(self, template_id: str) -> Optional["Graph"]:
        """
        Create a new graph instance from a template.

        Args:
            template_id: The ID of the template to instantiate.

        Returns:
            A new Graph instance with the template's nodes and connections,
            or None if the template is not found.
        """
        template = self.get_template(template_id)
        if template is None:
            return None

        from visualpython.graph.graph import Graph
        from visualpython.nodes.registry import get_node_registry

        registry = get_node_registry()
        registry.register_default_nodes()

        # Create node factory
        def node_factory(node_data: Dict[str, Any]) -> Any:
            return registry.create_node_from_dict(node_data)

        # Deserialize the graph from template data
        return Graph.from_dict(template.graph_data, node_factory)

    def load_templates_from_directory(self, directory: Path) -> int:
        """
        Load all template JSON files from a directory (recursively).

        Args:
            directory: Path to the directory containing template files.

        Returns:
            Number of templates successfully loaded.
        """
        count = 0
        if not directory.exists():
            return count

        for json_file in directory.rglob("*.json"):
            try:
                self.register_from_json(json_file)
                count += 1
            except (ValueError, json.JSONDecodeError, KeyError) as e:
                # Log error but continue loading other templates
                logger.warning("Failed to load template from %s: %s", json_file, e)

        return count

    def load_default_templates(self) -> int:
        """
        Load all built-in templates from the presets directory.

        Returns:
            Number of templates loaded.
        """
        if self._presets_loaded:
            return 0

        # Get the presets directory relative to this module
        presets_dir = Path(__file__).parent / "presets"
        count = self.load_templates_from_directory(presets_dir)
        self._presets_loaded = True
        return count

    @property
    def template_count(self) -> int:
        """Get the number of registered templates."""
        return len(self._templates)


# Module-level convenience function
def get_template_registry() -> TemplateRegistry:
    """Get the global template registry instance."""
    return TemplateRegistry.get_instance()
