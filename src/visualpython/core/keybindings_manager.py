"""
Keybindings manager for persisting custom keyboard shortcuts.

Stores user-defined keybindings in a JSON file in the user's app data
directory so they persist across restarts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import QStandardPaths
from visualpython.utils.logging import get_logger

_logger = get_logger(__name__)

# Default keybindings: action_id -> shortcut string
DEFAULT_KEYBINDINGS: Dict[str, str] = {
    # File
    "file.new": "Ctrl+N",
    "file.open": "Ctrl+O",
    "file.save": "Ctrl+S",
    "file.save_as": "Ctrl+Shift+S",
    "file.export_python": "Ctrl+Shift+E",
    "file.exit": "Ctrl+Q",
    # Edit
    "edit.undo": "Ctrl+Z",
    "edit.redo": "Ctrl+Y",
    "edit.cut": "Ctrl+X",
    "edit.copy": "Ctrl+C",
    "edit.paste": "Ctrl+V",
    "edit.duplicate": "Ctrl+D",
    "edit.delete": "Delete",
    "edit.select_all": "Ctrl+A",
    "edit.find": "Ctrl+F",
    "edit.group": "Ctrl+Alt+G",
    "edit.ungroup": "Ctrl+Shift+G",
    # View
    "view.zoom_in": "Ctrl++",
    "view.zoom_out": "Ctrl+-",
    "view.reset_zoom": "Ctrl+0",
    "view.fit_window": "Ctrl+Shift+F",
    "view.snap_grid": "Ctrl+G",
    # Run
    "run.run": "F5",
    "run.stop": "Shift+F5",
    "run.step_mode": "F10",
    "run.step_next": "F11",
    "run.continue": "F8",
    "run.run_selected": "Ctrl+F5",
}

# Human-readable names for the UI
ACTION_DISPLAY_NAMES: Dict[str, str] = {
    "file.new": "New Project",
    "file.open": "Open Project",
    "file.save": "Save Project",
    "file.save_as": "Save As",
    "file.export_python": "Export as Python",
    "file.exit": "Exit",
    "edit.undo": "Undo",
    "edit.redo": "Redo",
    "edit.cut": "Cut",
    "edit.copy": "Copy",
    "edit.paste": "Paste",
    "edit.duplicate": "Duplicate",
    "edit.delete": "Delete",
    "edit.select_all": "Select All",
    "edit.find": "Find",
    "edit.group": "Group Selected",
    "edit.ungroup": "Ungroup",
    "view.zoom_in": "Zoom In",
    "view.zoom_out": "Zoom Out",
    "view.reset_zoom": "Reset Zoom",
    "view.fit_window": "Fit to Window",
    "view.snap_grid": "Snap to Grid",
    "run.run": "Run",
    "run.stop": "Stop",
    "run.step_mode": "Step Mode",
    "run.step_next": "Step Next",
    "run.continue": "Continue",
    "run.run_selected": "Run Selected",
}

# Category groupings for the UI
ACTION_CATEGORIES: Dict[str, list] = {
    "File": [k for k in DEFAULT_KEYBINDINGS if k.startswith("file.")],
    "Edit": [k for k in DEFAULT_KEYBINDINGS if k.startswith("edit.")],
    "View": [k for k in DEFAULT_KEYBINDINGS if k.startswith("view.")],
    "Run": [k for k in DEFAULT_KEYBINDINGS if k.startswith("run.")],
}


class KeybindingsManager:
    """
    Manages persistent keybindings stored in a JSON config file.

    The config file is stored in the platform-specific app data directory
    (e.g. %APPDATA%/VisualPython/ on Windows).
    """

    CONFIG_FILENAME = "keybindings.json"

    def __init__(self) -> None:
        self._bindings: Dict[str, str] = dict(DEFAULT_KEYBINDINGS)
        self._config_path = self._get_config_path()
        self.load()

    def _get_config_path(self) -> Path:
        """Get the path to the keybindings config file."""
        app_data = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        if not app_data:
            # Fallback to project directory
            app_data = str(Path(__file__).resolve().parent.parent.parent.parent)

        config_dir = Path(app_data)
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / self.CONFIG_FILENAME

    def load(self) -> None:
        """Load keybindings from the config file, falling back to defaults."""
        if not self._config_path.exists():
            self._bindings = dict(DEFAULT_KEYBINDINGS)
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)

            # Merge saved bindings over defaults (so new actions get defaults)
            self._bindings = dict(DEFAULT_KEYBINDINGS)
            for action_id, shortcut in saved.items():
                if action_id in self._bindings:
                    self._bindings[action_id] = shortcut
        except Exception as e:
            _logger.warning(f"Failed to load keybindings: {e}")
            self._bindings = dict(DEFAULT_KEYBINDINGS)

    def save(self) -> None:
        """Save current keybindings to the config file."""
        # Only save bindings that differ from defaults to keep file minimal
        custom = {}
        for action_id, shortcut in self._bindings.items():
            if shortcut != DEFAULT_KEYBINDINGS.get(action_id):
                custom[action_id] = shortcut
            else:
                # Save all bindings so user can see them in the file
                custom[action_id] = shortcut

        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(custom, f, indent=2, sort_keys=True)
            _logger.info(f"Keybindings saved to {self._config_path}")
        except Exception as e:
            _logger.warning(f"Failed to save keybindings: {e}")

    def get(self, action_id: str) -> str:
        """Get the shortcut string for an action."""
        return self._bindings.get(action_id, "")

    def set(self, action_id: str, shortcut: str) -> None:
        """Set the shortcut for an action."""
        self._bindings[action_id] = shortcut

    def get_all(self) -> Dict[str, str]:
        """Get all keybindings."""
        return dict(self._bindings)

    def reset_to_defaults(self) -> None:
        """Reset all keybindings to defaults."""
        self._bindings = dict(DEFAULT_KEYBINDINGS)

    def reset_action(self, action_id: str) -> None:
        """Reset a single action to its default keybinding."""
        if action_id in DEFAULT_KEYBINDINGS:
            self._bindings[action_id] = DEFAULT_KEYBINDINGS[action_id]

    def get_default(self, action_id: str) -> str:
        """Get the default shortcut for an action."""
        return DEFAULT_KEYBINDINGS.get(action_id, "")

    @property
    def config_path(self) -> Path:
        """Get the config file path."""
        return self._config_path
