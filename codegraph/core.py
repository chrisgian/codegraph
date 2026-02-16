import logging
import os
import re
from argparse import Namespace
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Text, Tuple

from codegraph.parser import Class, Function, AsyncFunction, Import, create_objects_array
from codegraph.utils import get_python_paths_list

logger = logging.getLogger(__name__)

aliases = {}


@dataclass
class FocusConfig:
    focus_file: Optional[str] = None     # e.g., "engine.py"
    focus_class: Optional[str] = None    # e.g., "Game"
    exclude_names: Set[str] = field(default_factory=set)

    @classmethod
    def from_args(cls, focus, exclude):
        config = cls()
        if focus:
            parts = focus.split(":")
            config.focus_file = parts[0]
            config.focus_class = parts[1] if len(parts) > 1 else None
        if exclude:
            config.exclude_names = {n.strip() for n in exclude.split(",")}
        return config


def read_file_content(path: Text) -> Text:
    with open(path, "r+") as file_read:
        return file_read.read()


def parse_code_file(path: Text) -> List:
    """read module source and parse to get objects array"""
    source = read_file_content(path)
    parsed_module = create_objects_array(source=source, fname=os.path.basename(path))
    return parsed_module


def get_code_objects(paths_list: List) -> Dict:
    """
        get all code files data for paths list
    :param paths_list: list with paths to code files to parse
    :return:
    """
    all_data = {}
    for path in paths_list:
        content = parse_code_file(path)
        all_data[path] = content
    return all_data


class CodeGraph:
    def __init__(self, args: Namespace):
        self.paths_list = get_python_paths_list(args.paths)
        # get py modules list data
        self.modules_data = get_code_objects(self.paths_list)
        self.focus_config = FocusConfig.from_args(
            getattr(args, 'focus', None),
            getattr(args, 'exclude', None),
        )

    def get_lines_numbers(self):
        """
           return data with entities names and start and end line
        :return: Example: {'/Users/user/package/module_name.py':
                {'function': (1, 2), 'function_with_constant_return_int': (5, 6),
                'function_with_constant_return_float': (9, 10),
                'function_with_statement_return': (13, 14)..}}

                first number in tuple - start line, second - last line
        """
        data = {}
        for module in self.modules_data:
            data[module] = {}
            for func in self.modules_data[module]:
                data[module][func.name] = (func.lineno, func.endno)
        return data

    def get_entity_metadata(self) -> Dict:
        """
        Return metadata for all entities including line counts and types.
        :return: {module_path: {entity_name: {'lines': int, 'type': 'function'|'class'}}}
        """
        data = {}
        for module_path in self.modules_data:
            data[module_path] = {}
            module_name = os.path.basename(module_path)
            for entity in self.modules_data[module_path]:
                if isinstance(entity, Import):
                    continue
                lines = 0
                if entity.lineno and entity.endno:
                    lines = entity.endno - entity.lineno + 1

                entity_type = "function"
                if isinstance(entity, Class):
                    entity_type = "class"
                elif isinstance(entity, (Function, AsyncFunction)):
                    entity_type = "function"

                data[module_path][entity.name] = {
                    "lines": lines,
                    "entity_type": entity_type,
                    "lineno": entity.lineno,
                    "endno": entity.endno
                }

                # For focused class, also emit method-level metadata
                if (isinstance(entity, Class)
                        and self.focus_config.focus_class == entity.name
                        and (not self.focus_config.focus_file
                             or self.focus_config.focus_file == module_name)):
                    all_methods = {}
                    all_methods.update(entity.methods)
                    all_methods.update(entity.async_methods)
                    for method_name, method_obj in all_methods.items():
                        m_lines = 0
                        if method_obj.lineno and method_obj.endno:
                            m_lines = method_obj.endno - method_obj.lineno + 1
                        data[module_path][f"{entity.name}.{method_name}"] = {
                            "lines": m_lines,
                            "entity_type": "method",
                            "lineno": method_obj.lineno,
                            "endno": method_obj.endno
                        }
        return data

    def usage_graph(self) -> Dict:
        """
            module name: function
        :return:
        """
        entities_lines, imports, modules_names_map = get_imports_and_entities_lines(
            self.modules_data
        )
        # Expand focused class into per-method entries
        expand_entities_lines_for_focus(
            entities_lines, self.modules_data, self.focus_config
        )
        entities_usage_in_modules = collect_entities_usage_in_modules(
            self.modules_data, imports, modules_names_map
        )
        # Detect self.method() calls within focused class
        self_calls = detect_self_method_calls(
            self.modules_data, self.focus_config
        )
        for path in self_calls:
            if path not in entities_usage_in_modules:
                entities_usage_in_modules[path] = defaultdict(list)
            for entity_name, lines in self_calls[path].items():
                entities_usage_in_modules[path][entity_name].extend(lines)
        # create edges
        dependencies = defaultdict(dict)
        for module in entities_usage_in_modules:
            dependencies[module] = defaultdict(list)
            for method_that_used in entities_usage_in_modules[module]:
                method_usage_lines = entities_usage_in_modules[module][method_that_used]
                for method_usage_line in method_usage_lines:
                    for entity in entities_lines[module]:
                        if entity[0] <= method_usage_line <= entity[1]:
                            dependencies[module][entities_lines[module][entity]].append(
                                method_that_used
                            )
                            break
                    else:
                        # mean in global of module
                        dependencies[module]["_"].append(method_that_used)
        dependencies = populate_free_nodes(
            self.modules_data, dependencies, imports, modules_names_map,
            self.focus_config
        )
        # Apply exclusions
        if self.focus_config.exclude_names:
            dependencies = apply_exclusions(dependencies, self.focus_config.exclude_names)
        return dependencies

    def get_dependencies(self, file_path: str, distance: int) -> Dict[str, Set[str]]:
        """
        Get dependencies that are 'distance' nodes away from the given file.

        :param file_path: Path of the file to start from
        :param distance: Number of edges to traverse
        :return: Dictionary with distances as keys and sets of dependent files as values
        """
        dependencies = {i: set() for i in range(1, distance + 1)}
        graph = self.usage_graph()

        if file_path not in graph:
            return dependencies

        queue = deque([(file_path, 0)])
        visited = set()

        while queue:
            current_file, current_distance = queue.popleft()

            if current_distance >= distance:
                continue

            if current_file not in visited:
                visited.add(current_file)

                for entity, used_entities in graph[current_file].items():
                    for used_entity in used_entities:
                        if "." in used_entity:
                            dependent_file = used_entity.split(".")[0] + ".py"
                            if dependent_file != current_file:
                                dependencies[current_distance + 1].add(dependent_file)
                                queue.append((dependent_file, current_distance + 1))

        return dependencies


def expand_entities_lines_for_focus(
    entities_lines: Dict, code_objects: Dict, focus_config: FocusConfig
) -> None:
    """For the focused class, replace the single class-level entry with per-method entries."""
    if not focus_config.focus_class:
        return
    for path in code_objects:
        module_name = os.path.basename(path)
        if focus_config.focus_file and focus_config.focus_file != module_name:
            continue
        for entity in code_objects[path]:
            if isinstance(entity, Class) and entity.name == focus_config.focus_class:
                # Remove the class-level entry
                class_key = None
                for key in list(entities_lines[path].keys()):
                    if entities_lines[path][key] == entity.name:
                        class_key = key
                        break
                if class_key:
                    del entities_lines[path][class_key]
                # Add per-method entries
                all_methods = {}
                all_methods.update(entity.methods)
                all_methods.update(entity.async_methods)
                for method_name, method_obj in all_methods.items():
                    if method_obj.lineno and method_obj.endno:
                        entities_lines[path][
                            (method_obj.lineno, method_obj.endno)
                        ] = f"{entity.name}.{method_name}"


def detect_self_method_calls(
    code_objects: Dict, focus_config: FocusConfig
) -> Dict:
    """Scan focused class for self.method() and ClassName.method() patterns."""
    result = defaultdict(lambda: defaultdict(list))
    if not focus_config.focus_class:
        return result
    self_pattern = re.compile(r'self\.(\w+)\s*\(')
    for path in code_objects:
        module_name = os.path.basename(path)
        if focus_config.focus_file and focus_config.focus_file != module_name:
            continue
        for entity in code_objects[path]:
            if isinstance(entity, Class) and entity.name == focus_config.focus_class:
                all_method_names = set(entity.methods.keys()) | set(entity.async_methods.keys())
                source = read_file_content(path)
                lines = source.split("\n")
                class_start = entity.lineno
                class_end = entity.endno or len(lines)
                for line_idx in range(class_start - 1, min(class_end, len(lines))):
                    line = lines[line_idx]
                    # Detect self.method()
                    for match in self_pattern.finditer(line):
                        method_name = match.group(1)
                        if method_name in all_method_names:
                            qualified = f"{entity.name}.{method_name}"
                            result[path][qualified].append(line_idx + 1)
                    # Detect ClassName.method() for static/classmethod calls
                    static_pattern = re.compile(
                        rf'{re.escape(entity.name)}\.(\w+)\s*\('
                    )
                    for match in static_pattern.finditer(line):
                        method_name = match.group(1)
                        if method_name in all_method_names:
                            qualified = f"{entity.name}.{method_name}"
                            result[path][qualified].append(line_idx + 1)
    return result


def apply_exclusions(dependencies: Dict, exclude_names: Set[str]) -> Dict:
    """Remove excluded entities from the dependency graph."""
    filtered = defaultdict(dict)
    for module, entities in dependencies.items():
        filtered[module] = defaultdict(list)
        for entity_name, deps in entities.items():
            # Check if entity itself should be excluded
            base_name = entity_name.split(".")[-1] if "." in entity_name else entity_name
            if base_name in exclude_names:
                continue
            # Filter deps
            filtered_deps = []
            for dep in deps:
                dep_base = dep.split(".")[-1] if "." in dep else dep
                if dep_base not in exclude_names:
                    filtered_deps.append(dep)
            filtered[module][entity_name] = filtered_deps
    return filtered


def get_module_name(code_path: Text) -> Text:
    module_name = os.path.basename(code_path).replace(".py", "")
    return module_name


def module_name_in_imports(imports: List, module_name: Text) -> bool:
    for import_ in imports:
        if module_name in import_:
            return True
    return False


def get_imports_and_entities_lines(  # noqa: C901
    code_objects: Dict,
) -> Tuple[Dict, Dict, Dict]:
    # todo: need to do optimization
    """
    joined together to avoid iteration several time
    imports - list of modules in code_objects Dict that used in current module
    """
    entities_lines = defaultdict(dict)
    imports = defaultdict(list)
    modules_ = code_objects.keys()
    names_map = {}
    # Build a set of all module names for quick lookup
    module_names_set = {os.path.basename(m).replace(".py", "") for m in modules_}

    for path in code_objects:
        names_map[get_module_name(path)] = path
        # for each module in list
        if code_objects[path] and isinstance(code_objects[path][-1], Import):
            # extract imports if exist
            for import_ in code_objects[path].pop(-1).modules:
                pathed_import = import_
                alias = None
                if " as " in pathed_import:
                    pathed_import, alias = pathed_import.split(" as ")

                parts = pathed_import.split(".")
                matched = False

                # Try each part from right to left to find a module match
                # e.g., simple_ddl_parser.output.dialects.dialect_by_name
                # -> try: dialect_by_name (no), dialects (yes!)
                for i in range(len(parts) - 1, -1, -1):
                    candidate = parts[i]

                    # Check if this part matches a module name
                    if candidate in module_names_set:
                        for module_ in modules_:
                            if candidate in module_:
                                if alias:
                                    aliases[candidate] = alias
                                imports[path].append(candidate)
                                matched = True
                                break
                        if matched:
                            break

                    # Check for __init__.py - if the candidate is a package name
                    # e.g., from simple_ddl_parser import X -> simple_ddl_parser/__init__.py
                    if not matched:
                        for module_ in modules_:
                            # Check if this is a package __init__.py
                            if f"/{candidate}/__init__.py" in module_ or module_.endswith(f"{candidate}/__init__.py"):
                                if alias:
                                    aliases[candidate] = alias
                                imports[path].append("__init__")
                                matched = True
                                break
                        if matched:
                            break

        for entity in code_objects[path]:
            # create a dict with lines of start and end for each entity in module
            entities_lines[path][(entity.lineno, entity.endno)] = entity.name
    return entities_lines, imports, names_map


def search_entities_from_list_in_code(
    entities_list: List, module_name: Text, line: Text
) -> Text:
    for entity in entities_list:
        if search_entity_usage(module_name, entity.name, line):
            yield entity


def search_entities_from_module_in_code(
    _module: Text, _path: Text, code_objects: Dict, code: List, current: bool = False
) -> Dict:
    found_entities = defaultdict(list)
    for num, line in enumerate(code):
        if (
            not line.startswith("#")
            and not line.startswith('"')
            and not line.startswith("'")
        ):
            entities_in_line = [
                x
                for x in search_entities_from_list_in_code(
                    code_objects[_path], _module, line
                )
            ]
            for entity in entities_in_line:
                prefix = f"{_module}." if not current else ""
                found_entities[f"{prefix}{entity.name}"].append(num + 1)
    return found_entities


def collect_entities_usage_in_modules(
    code_objects: Dict, imports: Dict, modules_names_map: Dict
) -> Dict:
    entities_usage_in_modules = defaultdict(dict)
    for path in code_objects:
        entities_usage_in_modules[path] = defaultdict(list)
        logger.debug(f"Processing module: {path}")
        logger.debug(f"Imports in module: {imports[path]}")
        module_content = read_file_content(path)
        # to reduce count of iteration, we not need lines with functions and classes defenitions
        module_content = (
            module_content.replace("async ", "# async ")
            .replace("def ", "# def ")
            .replace("class ", "# class ")
        )
        # split by line
        code = module_content.split("\n")
        for _module in imports[path]:
            # search entities from other modules (skip if not in analyzed codebase)
            if _module not in modules_names_map:
                continue
            _path = modules_names_map[_module]
            entities_usage_in_modules[path].update(
                search_entities_from_module_in_code(_module, _path, code_objects, code)
            )
        # search entities from current module
        entities_usage_in_modules[path].update(
            search_entities_from_module_in_code(
                get_module_name(path), path, code_objects, code, current=True
            )
        )
    return entities_usage_in_modules


def populate_free_nodes(code_objects: Dict, dependencies: Dict, imports: Dict,
                        modules_names_map: Dict, focus_config: FocusConfig = None) -> Dict:
    if focus_config is None:
        focus_config = FocusConfig()

    for path in code_objects:
        module_name = os.path.basename(path)
        # Create module-to-module connections based on imports
        # This ensures we show connections even when specific entities aren't detected
        # (e.g., when importing variables or when entity usage detection misses something)
        if imports.get(path):
            if "_" not in dependencies[path]:
                dependencies[path]["_"] = []
            for imp in imports[path]:
                import_dep = f"{imp}._"
                if import_dep not in dependencies[path]["_"]:
                    dependencies[path]["_"].append(import_dep)

        for entity in code_objects[path]:
            if entity.name not in dependencies[path]:
                dependencies[path][entity.name] = []

            # For focused class, also add free nodes for methods
            if (isinstance(entity, Class)
                    and focus_config.focus_class == entity.name
                    and (not focus_config.focus_file
                         or focus_config.focus_file == module_name)):
                all_methods = {}
                all_methods.update(entity.methods)
                all_methods.update(entity.async_methods)
                for method_name in all_methods:
                    qualified = f"{entity.name}.{method_name}"
                    if qualified not in dependencies[path]:
                        dependencies[path][qualified] = []

            # Add inheritance connections for classes
            if isinstance(entity, Class) and entity.super:
                for base_class in entity.super:
                    # Try to find the base class in imports or local module
                    base_found = False

                    # Check if it's a dotted name (e.g., module.ClassName)
                    if "." in base_class:
                        # Already qualified, add as-is
                        dependencies[path][entity.name].append(base_class)
                        base_found = True
                    else:
                        # Search in imports for this module
                        for imp in imports.get(path, []):
                            # Import could be like "dialects.HQL" or "simple_ddl_parser.dialects.HQL"
                            if imp.endswith("." + base_class) or imp.endswith("." + base_class.split(" as ")[0]):
                                # Found the import, extract module name
                                parts = imp.split(".")
                                if len(parts) >= 2:
                                    module_name = parts[-2]  # e.g., "dialects" from "simple_ddl_parser.dialects.HQL"
                                    dependencies[path][entity.name].append(f"{module_name}.{base_class}")
                                    base_found = True
                                    break

                        # If not found in imports, check if it's a local class
                        if not base_found:
                            for local_entity in code_objects[path]:
                                if local_entity.name == base_class:
                                    # It's a local class, add without module prefix
                                    dependencies[path][entity.name].append(base_class)
                                    base_found = True
                                    break

                        # If still not found, add as-is (might be external)
                        if not base_found:
                            dependencies[path][entity.name].append(base_class)

    return dependencies


def search_entity_usage(module_name: Text, name: Text, line: Text) -> bool:
    """check exist method or entity usage in line or not"""
    method_call = name + "("
    dot_access = name + "."
    if (
        method_call in line
        or " " + dot_access in line
        or f"{module_name}." + method_call in line
        or f"{module_name}." + dot_access in line
    ):
        return True
    elif module_name in aliases:
        if aliases[module_name] + "." + method_call in line:
            return True
    return False
