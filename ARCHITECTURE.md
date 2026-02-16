# CodeGraph Architecture

This document describes the architecture and design of the CodeGraph tool.

## Overview

CodeGraph is a Python tool that creates dependency graphs from Python source code. It analyzes Python files, extracts function/class definitions and their relationships, and generates interactive visualizations.

## Project Structure

```
codegraph/
├── codegraph/              # Main package
│   ├── __init__.py         # Package init, version definition
│   ├── main.py             # CLI entry point (click-based)
│   ├── core.py             # Core graph building logic
│   ├── parser.py           # Python source code parser
│   ├── utils.py            # Utility functions
│   └── vizualyzer.py       # Visualization (D3.js + matplotlib)
├── tests/                  # Test suite
│   ├── test_codegraph.py   # Basic tests
│   ├── test_graph_generation.py  # Comprehensive graph tests
│   ├── test_utils.py       # Utility function tests
│   └── test_data/          # Test fixtures
├── docs/                   # Documentation
├── pyproject.toml          # Poetry configuration
├── tox.ini                 # Multi-version testing
└── .github/workflows/      # CI/CD
```

## Core Components

### 1. Parser (`codegraph/parser.py`)

The parser uses Python's `tokenize` module to extract code structure from source files.

**Key Classes:**
- `_Object` - Base class for all parsed objects (lineno, endno, name, parent)
- `Function` - Represents a function definition
- `AsyncFunction` - Represents an async function definition
- `Class` - Represents a class definition with methods
- `Import` - Collects all imports from a module

**Main Function:**
- `create_objects_array(fname, source)` - Parses source code and returns list of objects

**Import Handling:**
- Simple imports: `import os` → `['os']`
- From imports: `from os import path` → `['os.path']`
- Comma-separated: `from pkg import a, b, c` → `['pkg.a', 'pkg.b', 'pkg.c']`
- Aliased imports: `from pkg import mod as m` → `['pkg.mod as m']`

### 2. Core (`codegraph/core.py`)

The core module builds the dependency graph from parsed data.

**Key Classes:**
- `CodeGraph` - Main class that orchestrates graph building
- `FocusConfig` - Dataclass holding focus/exclude settings for method-level analysis

**Key Functions:**
- `get_code_objects(paths_list)` - Parse all files and return dict of module → objects
- `get_imports_and_entities_lines()` - Extract imports and entity line ranges
- `collect_entities_usage_in_modules()` - Find where entities are used
- `search_entity_usage()` - Check if entity is used in a line
- `expand_entities_lines_for_focus()` - Replace class-level entry with per-method entries for focused class
- `detect_self_method_calls()` - Scan focused class for `self.method()` and `ClassName.method()` patterns
- `apply_exclusions()` - Remove excluded entity names from the dependency graph

**Data Flow:**
```
Python Files → Parser → Code Objects → Import Analysis → [Focus Expansion] → Entity Usage → [Self-call Detection] → Dependency Graph → [Exclusion Filter]
```

**Graph Format:**
```python
# Standard (class-level):
{
    "/path/to/module.py": {
        "function_name": ["other_module.func1", "local_func"],
        "class_name": ["dependency1"],
    }
}

# With --focus (method-level for focused class):
{
    "/path/to/module.py": {
        "Game.play_round": ["Game.deal_cards", "Game.calculate_score"],
        "Game.deal_cards": [],
        "helper_function": ["Game.play_round"],
    }
}
```

**Focus Mode:**

When `--focus file.py:ClassName` is used, the focused class is expanded from a single node into per-method nodes. The `FocusConfig` dataclass drives this:

1. `expand_entities_lines_for_focus()` replaces the class-level `(lineno, endno) → ClassName` entry with per-method entries like `(method.lineno, method.endno) → ClassName.method_name`
2. `detect_self_method_calls()` scans the class body for `self.method()` and `ClassName.method()` patterns, adding them as intra-class edges
3. `apply_exclusions()` post-filters the graph to remove noisy entities like `logger` or `print`

**Known Limitations:**
- `self.deck.shuffle()` does NOT resolve to `Deck.shuffle` (requires type inference)
- Inherited methods called via `self.inherited_method()` won't resolve if not defined on the focused class
- Only `self.method()` and `ClassName.method()` patterns are detected for intra-class calls

### 3. Visualizer (`codegraph/vizualyzer.py`)

Provides two visualization modes: D3.js (default) and matplotlib (legacy).

**D3.js Visualization:**
- `convert_to_d3_format()` - Converts graph to D3.js node/link format
- `get_d3_html_template()` - Returns complete HTML with embedded D3.js
- `draw_graph()` - Saves HTML and opens in browser

**D3.js Features:**
- Force-directed layout for automatic node positioning
- Zoom/pan with mouse wheel and drag
- Node dragging to reposition
- Collapse/expand modules and entities
- Search with autocomplete
- Tooltips and statistics panel

**Matplotlib Visualization:**
- `draw_graph_matplotlib()` - Legacy visualization using networkx
- `process_module_in_graph()` - Process single module into graph

**D3.js Data Format:**
```json
{
  "nodes": [
    {"id": "module.py", "type": "module", "collapsed": false},
    {"id": "module.py:func", "label": "func", "type": "entity", "parent": "module.py"}
  ],
  "links": [
    {"source": "module.py", "target": "module.py:func", "type": "module-entity"},
    {"source": "module.py:func", "target": "other.py:dep", "type": "dependency"}
  ]
}
```

### 4. CLI (`codegraph/main.py`)

Click-based command-line interface.

**Options:**
- `paths` - Directory or file paths to analyze
- `--focus` - Focus on a class for method-level analysis (e.g., `engine.py:Game`)
- `--exclude` - Comma-separated entity names to exclude (e.g., `logger,print`)
- `--csv PATH` - Export graph data to CSV file
- `--matplotlib` - Use legacy matplotlib visualization
- `--output` - Custom output path for HTML file

### 5. Utilities (`codegraph/utils.py`)

Helper functions for file system operations.

**Key Functions:**
- `get_python_paths_list(path)` - Recursively find all .py files

## Data Flow

```
1. CLI receives path(s) + optional --focus / --exclude
        ↓
2. utils.get_python_paths_list() finds all .py files
        ↓
3. parser.create_objects_array() parses each file
   - Extracts functions, classes, methods
   - Collects import statements
        ↓
4. core.CodeGraph.usage_graph() builds dependency graph
   - Maps entities to line ranges
   - [If --focus] Expands focused class into per-method entries
   - Finds entity usage in code
   - [If --focus] Detects self.method() calls within focused class
   - Creates dependency edges
   - [If --exclude] Removes excluded entities from graph
        ↓
5. vizualyzer.draw_graph() creates visualization
   - Converts to D3.js format (handles method-level dotted names)
   - Generates HTML with embedded JS
   - Opens in browser
```

## Node Types

| Type | Visual | Description |
|------|--------|-------------|
| Module | Green square | Python .py file |
| Entity | Blue circle | Function or class |
| Method | Blue circle | Method within a focused class (only with `--focus`) |
| External | Gray circle | Dependency from outside analyzed codebase |

## Link Types

| Type | Visual | Description |
|------|--------|-------------|
| module-entity | Green dashed | Module contains entity |
| module-module | Orange solid | Module imports from module |
| dependency | Red | Entity uses another entity |

## Testing Strategy

- **Unit tests**: Parser, import handling, utility functions
- **Integration tests**: Full graph generation on test data
- **Self-reference tests**: CodeGraph analyzing its own codebase
- **Multi-version**: Python 3.9 - 3.13 via tox

## Dependencies

- **networkx**: Graph data structure (for matplotlib mode)
- **matplotlib**: Legacy visualization
- **click**: CLI framework

## Extension Points

1. **New visualizers**: Add functions to `vizualyzer.py`
2. **New parsers**: Extend `parser.py` for other languages
3. **New link types**: Add to `convert_to_d3_format()`
4. **Export formats**: Add to `vizualyzer.py` (JSON, DOT, etc.)
