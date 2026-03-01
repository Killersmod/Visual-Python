# VisualPython

A visual node-based scripting environment for Python. Build Python programs by connecting nodes in an intuitive graphical interface instead of writing code directly.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-orange)

## Features

- **Node-Based Visual Programming** — Drag, drop, and connect nodes on a canvas to build Python programs visually. Each node displays live syntax-highlighted code previews, execution state indicators, and inline value editors so you can tweak inputs directly on the canvas without creating extra nodes.

- **45+ Built-in Nodes** — A rich library spanning control flow (if/else, for, while, try/catch), I/O (file read/write, HTTP requests, database queries), math, string and list operations (map, filter, reduce), regex, JSON, threading with join synchronization, and more. Nodes are organized by category in a searchable palette with drag-and-drop placement.

- **Live Execution** — Execute graphs in a background thread with real-time streaming output, per-node progress tracking, and a continue-on-error mode that marks downstream nodes as skipped rather than halting the entire workflow. Includes step-through debugging with pause/resume and built-in runtime type inference that catches data flow mismatches as they happen.

- **Code Generation** — Compile visual graphs into clean, executable Python scripts with proper imports, indentation, and control flow. The compiler is scope-aware, tracking conditional variable definitions across branches and warning about unsafe access paths before you ever run the code.

- **Subgraphs** — Encapsulate reusable logic into nested subgraph nodes that act like functions. Subgraphs can be embedded directly or referenced from external `.vpy`/`.vnl` files, with automatic port synchronization, version tracking, and broken-reference detection.

- **Undo/Redo** — Every operation is reversible through a command-based undo/redo system. Consecutive edits like typing or dragging are automatically merged into single undo steps, and composite commands let bulk operations (like deleting multiple nodes) be undone in one action.

- **Project Serialization** — Save and load complete workflows as `.vpy` files with automatic version tracking. The serializer preserves all nodes, connections, metadata, and graph structure, with backward-compatible loading for older formats.

- **Variable Management** — A thread-safe global variable store shared across all nodes, with atomic operations (increment, get-and-set, compare-and-swap) for safe concurrent access during threaded execution. Supports optional type validation and persists across sessions via JSON or SQLite backends.

- **Library Export/Import** — Export selected nodes and their connections as reusable `.vnl` library files with metadata like name, author, version, and tags. Importing automatically remaps IDs to prevent conflicts and offsets positions for clean placement.

- **Dependency Management** — Automatically scans and visualizes subgraph dependencies across workflows in a dedicated panel with forward, reverse, and saved tree views. Detects circular and broken references, color-codes dependency types, and persists named dependency trees with SQLite-backed storage for change tracking.

- **Workflow Templates** — Browse pre-built starter templates for data processing, file operations, and web scraping in a searchable panel organized by category and difficulty level. Instantiate templates by double-clicking or dragging them onto the canvas to jumpstart new workflows.

## Requirements

- Python 3.10 or higher
- PyQt6 6.5.0 or higher

## Installation

```bash
# Clone the repository
git clone https://github.com/Killersmod/Visual-Python.git
cd Visual-Python

# Install dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e ".[dev]"
```

## Usage

```bash
# Run as a Python module
python -m visualpython

# Or use the console entry point (after pip install)
visualpython
```

On Windows, you can also use the PowerShell launcher:

```powershell
.\run.ps1

# Open a project file
.\run.ps1 -File "path\to\project.vpy"
```

## Project Structure

```
src/visualpython/
├── core/           # Application controller and keybindings
├── ui/             # Main window, dialogs, and panels
├── graph/          # Graph data model and Qt scene/view
├── nodes/          # Node system (models, views, controllers)
├── execution/      # Graph execution engine
├── compiler/       # Python code generation
├── serialization/  # Project and variable save/load
├── commands/       # Undo/redo command pattern
├── templates/      # Workflow template presets
├── variables/      # Variable management
├── dependencies/   # Dependency scanning
├── layout/         # Graph layout algorithms
└── utils/          # Logging and utilities
```

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Type checking
mypy src/

# Format code
black src/
isort src/

# Lint
flake8 src/
```

## License

MIT
