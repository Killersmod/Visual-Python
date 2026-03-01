# VisualPython

A visual node-based scripting environment for Python. Build Python programs by connecting nodes in an intuitive graphical interface instead of writing code directly.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-orange)

## Features

- **Node-Based Visual Programming** — Create workflows by dragging, dropping, and connecting nodes on a canvas
- **45+ Built-in Nodes** — Control flow, I/O, math, strings, lists, JSON, HTTP requests, regex, database queries, threading, and more
- **Live Execution** — Run graphs with real-time output capture and execution summaries
- **Code Generation** — Generate executable Python code from visual graphs
- **Subgraphs** — Encapsulate reusable logic into nested subgraph nodes
- **Undo/Redo** — Full command-based undo/redo for all operations
- **Project Serialization** — Save and load projects as `.vpy` files
- **Variable Management** — Persistent variables across sessions with JSON and SQLite backends
- **Library Export/Import** — Share reusable node libraries
- **Dependency Management** — Automatically scans and visualizes subgraph dependencies across workflows, detects circular and broken references, and persists dependency trees with SQLite-backed storage
- **Workflow Templates** — Pre-built templates for data processing, file processing, and web scraping

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
