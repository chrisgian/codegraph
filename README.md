### CodeGraph - static code analyzator, that create a diagram with your code structure.

![badge1](https://img.shields.io/pypi/v/codegraph) ![badge2](https://img.shields.io/pypi/l/codegraph) ![badge3](https://img.shields.io/pypi/pyversions/codegraph)![workflow](https://github.com/xnuinside/codegraph/actions/workflows/main.yml/badge.svg)

**[Live Demo](https://xnuinside.github.io/codegraph/)** - Interactive visualization of [simple-ddl-parser](https://github.com/xnuinside/simple-ddl-parser) codebase

Tool that creates a diagram with your code structure to show dependencies between code entities (methods, modules, classes and etc).
Main advantage of CodeGraph is that it does not execute the code itself. You don't need to activate any environments or install dependencies to analyze the target code.
It is based only on lexical and syntax parsing, so it doesn't need to install all your code dependencies.

### Interactive Visualization

![Interactive Code Visualization](docs/img/interactive_code_visualization.png)

**Zoom, Pan & Drag** - Use mouse wheel to zoom, drag background to pan, drag nodes to reposition them.

### Search & Highlight

![Node Search](docs/img/node_search.png)

**Search with Autocomplete** - Press `Ctrl+F` (or `Cmd+F` on Mac) to search. Results show node type with color coding.

![Highlight Nodes](docs/img/highlight_nodes.png)

**Highlight Connections** - Click on any node to highlight it and all connected nodes. Others will be dimmed.

### Node Information

![Node Information](docs/img/node_information.png)

**Tooltips** - Hover over any node to see details: type, parent module, full path, lines of code, and connection counts (links in/out).

### Links Count

![Links Count](docs/img/links_count.png)

**Links Count Panel** - Find nodes by their connection count. Filter by "links in" or "links out" with configurable threshold.

### Unlinked Modules

![Unlinked Nodes](docs/img/listing_unlinked_nodes.png)

**Unlinked Panel** - Shows modules with no connections. Click to navigate to them on the graph.

### Massive Objects Detection

![Massive Objects](docs/img/massive_objects_detection.png)

**Massive Objects Panel** - Find large code entities by lines of code. Filter by type (modules, classes, functions) with configurable threshold.

### Display Settings

![Display Settings](docs/img/graph_display_settings.png)

**Display Filters** - Show/hide nodes by type (Modules, Classes, Functions, External) and links by type (Module→Module, Module→Entity, Dependencies).

### UI Tips

![UI Tips](docs/img/tips_in_ui.png)

**Built-in Help** - Legend and keyboard shortcuts are always visible in the UI.

---

### Installation

```console
pip install codegraph
```

### Usage

```console
codegraph /path/to/your_python_code
```

This will generate an interactive HTML visualization and open it in your browser.

### CLI Options

| Option | Description |
|--------|-------------|
| `--output PATH` | Custom output path for HTML file (default: `./codegraph.html`) |
| `--csv PATH` | Export summary CSV (one row per node with connection counts) |
| `--csv-detail PATH` | Export detailed CSV (one row per dependency edge) |
| `--focus TARGET` | Focus on a class for method-level analysis (e.g., `engine.py:Game`) |
| `--exclude NAMES` | Comma-separated entity names to exclude (e.g., `logger,print`) |
| `--matplotlib` | Use legacy matplotlib visualization instead of D3.js |
| `-o, --object-only` | Print dependencies to console only, no visualization |

### Method-Level Focus

Drill into a specific class to see method-level dependencies:

```console
codegraph /path/to/code --focus engine.py:Game
```

The `--focus` option expands the target class into individual method nodes, detecting `self.method()` calls as edges. Non-focused classes remain collapsed at class level.

Combine with `--exclude` to filter out noisy entities:

```console
codegraph /path/to/code --focus core.py:CodeGraph --exclude logger,print
```

**What it detects:**
- `self.method_name()` calls within the focused class
- `ClassName.method_name()` calls (static/classmethod)

**Limitations:**
- Chained calls like `self.deck.shuffle()` do not resolve to `Deck.shuffle` (requires type inference)
- Inherited methods not defined on the focused class won't be resolved

### CSV Export

#### Summary (`--csv`)

Export node-level summary with connection counts:

```console
codegraph /path/to/code --csv output.csv
```

Columns: `name`, `type`, `parent_module`, `full_path`, `links_out`, `links_in`, `lines`

#### Detailed (`--csv-detail`)

Export every dependency edge with full source and target context:

```console
codegraph /path/to/code --csv-detail output.csv
```

One row per dependency edge. Example output:

| source_file | source_module | source_entity | source_type | target_file | target_module | target_entity | target_type |
|---|---|---|---|---|---|---|---|
| codegraph/main.py | main | main | function | codegraph/core.py | core | CodeGraph | class |
| codegraph/core.py | core | CodeGraph | class | codegraph/utils.py | utils | get_python_paths_list | function |
| codegraph/core.py | core | parse_code_file | function | codegraph/parser.py | parser | create_objects_array | function |

Columns:
- `source_file` - Relative path of the file containing the source entity
- `source_module` - Module name of the source
- `source_entity` - Name of the entity that has the dependency
- `source_type` - Type of the source (function / class / module)
- `target_file` - Relative path of the file containing the target entity
- `target_module` - Module name of the target
- `target_entity` - Name of the entity being depended on
- `target_type` - Type of the target (function / class / module / external)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for full version history.
