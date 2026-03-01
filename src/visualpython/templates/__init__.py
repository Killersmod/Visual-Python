"""
Template system for VisualPython pre-built graph templates.

This module provides a registry of pre-built template graphs for common tasks
like file processing, web scraping, and data transformation.
"""

from visualpython.templates.template import GraphTemplate, TemplateCategory, TemplateDifficulty
from visualpython.templates.registry import TemplateRegistry, get_template_registry

__all__ = [
    "GraphTemplate",
    "TemplateCategory",
    "TemplateDifficulty",
    "TemplateRegistry",
    "get_template_registry",
]
