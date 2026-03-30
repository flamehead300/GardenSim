"""
agent.py - Garden Simulator class-structure summarizer.

Reads main.py from this directory, identifies every class definition and its
inheritance chain, and prints a structured report. If `ANTHROPIC_API_KEY` is
set and the `anthropic` package is installed, it also asks Claude for a richer
summary. Otherwise it falls back to a deterministic local summary.

Usage:
    python agent.py
"""

import ast
import os
import pathlib

try:
    import anthropic
except ImportError:
    anthropic = None


def _clip_text(text: str, limit: int = 72) -> str:
    text = " ".join(text.strip().split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _format_base_name(base_node: ast.expr) -> str:
    if isinstance(base_node, ast.Name):
        return base_node.id
    if isinstance(base_node, ast.Attribute) and isinstance(base_node.value, ast.Name):
        return f"{base_node.value.id}.{base_node.attr}"
    return ast.unparse(base_node)


def _iter_assigned_names(target_node: ast.expr) -> list[str]:
    if isinstance(target_node, ast.Name):
        return [target_node.id]
    if isinstance(target_node, (ast.Tuple, ast.List)):
        names = []
        for element in target_node.elts:
            names.extend(_iter_assigned_names(element))
        return names
    return []


def _value_summary(value_node: ast.expr) -> str:
    if isinstance(value_node, ast.Constant):
        return _clip_text(repr(value_node.value))
    if isinstance(value_node, ast.Dict):
        return f"dict with {len(value_node.keys)} entries"
    if isinstance(value_node, ast.Call):
        if isinstance(value_node.func, ast.Name):
            return f"computed via {value_node.func.id}()"
        if isinstance(value_node.func, ast.Attribute):
            return f"computed via {value_node.func.attr}()"
        return "computed value"
    if isinstance(value_node, (ast.List, ast.Tuple, ast.Set)):
        return f"{value_node.__class__.__name__.lower()} with {len(value_node.elts)} items"
    return _clip_text(ast.unparse(value_node))


def analyze_module(source_path: pathlib.Path) -> dict:
    """Collect top-level functions, constants, and classes from source_path."""
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))

    module_info = {
        "docstring": ast.get_docstring(tree),
        "functions": [],
        "constants": [],
        "classes": [],
    }

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_info["functions"].append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "doc": ast.get_docstring(node),
                }
            )
            continue

        if isinstance(node, ast.ClassDef):
            methods = []
            class_attributes = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(item.name)
                    continue
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        for name in _iter_assigned_names(target):
                            class_attributes.append(
                                {
                                    "name": name,
                                    "line": item.lineno,
                                    "value": _value_summary(item.value),
                                }
                            )
                elif isinstance(item, ast.AnnAssign) and item.value is not None:
                    for name in _iter_assigned_names(item.target):
                        class_attributes.append(
                            {
                                "name": name,
                                "line": item.lineno,
                                "value": _value_summary(item.value),
                            }
                        )

            module_info["classes"].append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "bases": [_format_base_name(base) for base in node.bases],
                    "methods": methods,
                    "class_attributes": class_attributes,
                }
            )
            continue

        if isinstance(node, ast.Assign):
            for target in node.targets:
                for name in _iter_assigned_names(target):
                    if name.isupper():
                        module_info["constants"].append(
                            {
                                "name": name,
                                "line": node.lineno,
                                "value": _value_summary(node.value),
                            }
                        )
            continue

        if isinstance(node, ast.AnnAssign) and node.value is not None:
            for name in _iter_assigned_names(node.target):
                if name.isupper():
                    module_info["constants"].append(
                        {
                            "name": name,
                            "line": node.lineno,
                            "value": _value_summary(node.value),
                        }
                    )

    return module_info


def find_classes(source_path: pathlib.Path) -> list[dict]:
    """
    Use Python's built-in AST to locate every class definition in source_path.
    Returns a list of dicts:
        {
            "name": str,
            "line": int,
            "bases": list[str],
            "methods": list[str],
        }
    """
    classes = analyze_module(source_path)["classes"]
    classes.sort(key=lambda item: item["line"])
    return classes


def build_class_report(source_path: pathlib.Path, classes: list[dict]) -> str:
    """Format the locally discovered class data as a plain-text report block."""
    lines = [f"File: {source_path}  ({source_path.stat().st_size} bytes)\n"]
    if not classes:
        lines.append("  (no class definitions found)")
        return "\n".join(lines)

    for class_info in classes:
        bases = ", ".join(class_info["bases"]) if class_info["bases"] else "object"
        lines.append(
            f"  class {class_info['name']}({bases})  - line {class_info['line']}"
        )
        for method_name in class_info["methods"]:
            lines.append(f"      def {method_name}")
        lines.append("")
    return "\n".join(lines)


def _infer_layer(class_info: dict) -> str:
    name = class_info["name"]
    bases = set(class_info["bases"])

    if name.endswith("Model"):
        return "Model"
    if name.endswith("Controller"):
        return "Controller"
    if name.endswith("App") or "App" in bases:
        return "Application"
    if name.endswith(("Canvas", "Panel", "Layout", "View")):
        return "View"
    if {"Widget", "BoxLayout", "GridLayout", "ScrollView"} & bases:
        return "View"
    return "Other"


def _infer_role(class_info: dict) -> str:
    name = class_info["name"]
    layer = _infer_layer(class_info)

    if layer == "Application":
        return "Application entrypoint that boots the Kivy UI."
    if layer == "Model":
        return "State model that stores the garden, selection, and sun settings."
    if layer == "Controller":
        return "Controller that translates user input into model mutations."
    if name.endswith("Layout"):
        return "Composite UI layout that coordinates controls and child widgets."
    if name.endswith("Canvas"):
        return "Interactive widget responsible for drawing and pointer handling."
    if name.endswith("Panel"):
        return "Editing panel that exposes controls for the selected shape."
    if layer == "View":
        return "View component that renders UI and reacts to application state."
    return "Project class defined in main.py."


def _consume_method_groups(
    methods: list[str], rules: list[tuple[str, object]]
) -> list[tuple[str, list[str]]]:
    remaining = list(methods)
    grouped = []

    for label, matcher in rules:
        if isinstance(matcher, set):
            matched = [name for name in remaining if name in matcher]
        else:
            matched = [name for name in remaining if matcher(name)]
        if matched:
            grouped.append((label, matched))
            remaining = [name for name in remaining if name not in matched]

    if remaining:
        grouped.append(("Other helpers", remaining))

    return grouped


def _categorize_methods(class_info: dict) -> list[tuple[str, list[str]]]:
    methods = class_info["methods"]
    name = class_info["name"]
    layer = _infer_layer(class_info)

    if not methods:
        return []

    if layer == "Controller":
        return _consume_method_groups(
            methods,
            [
                ("Lifecycle", {"__init__"}),
                ("Events", {"on_alert"}),
                (
                    "Configuration",
                    {
                        "apply_dimensions",
                        "zoom_in",
                        "zoom_out",
                        "update_sun",
                        "set_draw_category",
                    },
                ),
                (
                    "Drawing workflow",
                    {
                        "set_draw_mode",
                        "cancel_drawing",
                        "_clear_preview",
                        "on_mouse_press",
                        "on_mouse_drag",
                        "on_mouse_release",
                        "finish_polygon",
                    },
                ),
                (
                    "Selection and editing",
                    {
                        "clear_shapes",
                        "select_shape",
                        "deselect",
                        "delete_selected",
                        "toggle_move_mode",
                        "apply_prop_changes",
                        "_translate_shape",
                    },
                ),
                (
                    "Geometry and shadow math",
                    {
                        "shape_contains",
                        "_point_in_polygon",
                        "get_shadow_vector",
                        "get_shadow_poly",
                        "_convex_hull",
                    },
                ),
            ],
        )

    if name.endswith("Canvas"):
        return _consume_method_groups(
            methods,
            [
                ("Lifecycle and bindings", {"__init__", "_on_state_change"}),
                (
                    "Coordinate transforms",
                    {"world_to_canvas", "canvas_to_world", "_world_from_touch"},
                ),
                (
                    "Input handling",
                    {"on_touch_down", "on_touch_move", "on_touch_up"},
                ),
                (
                    "Rendering",
                    {
                        "_draw_text",
                        "_draw_polygon_fill",
                        "_draw_polygon_outline",
                        "redraw",
                    },
                ),
            ],
        )

    if name.endswith("Panel"):
        return _consume_method_groups(
            methods,
            [
                ("Lifecycle and layout", {"__init__", "_build_ui"}),
                (
                    "Model synchronization",
                    {"_on_shapes_changed", "_on_prop_cat_change", "populate", "update_geometry_fields"},
                ),
                (
                    "Editing controls",
                    {
                        "_apply_changes",
                        "_reset_geometry_grid",
                        "_add_geom_input",
                        "get_geometry_values",
                        "set_move_mode",
                    },
                ),
                ("Visibility", {"show", "hide"}),
            ],
        )

    if name.endswith("Layout"):
        return _consume_method_groups(
            methods,
            [
                ("Lifecycle and composition", {"__init__", "setup_ui"}),
                (
                    "Display synchronization",
                    {
                        "_update_zoom_label",
                        "_update_sun_label",
                        "_update_dimensions",
                        "_update_mode_ui",
                        "update_scrollregion",
                        "on_canvas_resize",
                    },
                ),
                (
                    "Selection and mode sync",
                    {"_on_selection_change", "_on_move_mode_change"},
                ),
                (
                    "User actions",
                    {
                        "_on_dimension_focus",
                        "apply_dimensions",
                        "apply_sun",
                        "_on_cat_press",
                        "show_alert",
                    },
                ),
                (
                    "Inspector integration",
                    {
                        "on_touch_down",
                        "_build_inspection_report",
                        "_build_shape_inspection_report",
                        "_shape_report",
                    },
                ),
            ],
        )

    if layer == "Application":
        return _consume_method_groups(methods, [("Bootstrapping", set(methods))])

    return _consume_method_groups(
        methods,
        [
            ("Lifecycle", {"__init__"}),
            ("Event handlers", lambda name: name.startswith(("on_", "_on_"))),
            (
                "State and actions",
                lambda name: name.startswith(
                    ("apply_", "set_", "update_", "toggle_", "select_", "delete_")
                ),
            ),
            (
                "Rendering and layout",
                lambda name: any(
                    token in name for token in ("draw", "render", "layout", "show", "hide")
                ),
            ),
        ],
    )


def _describe_function(function_info: dict) -> str:
    if function_info["doc"]:
        return _clip_text(function_info["doc"].splitlines()[0])
    if function_info["name"] == "main":
        return "Launches the GardenSimApp entrypoint."
    return "Top-level helper function."


def _format_constant_groups(constants: list[dict]) -> list[str]:
    color_constants = [item for item in constants if item["name"].startswith("COLOR_")]
    other_constants = [item for item in constants if not item["name"].startswith("COLOR_")]
    lines = []

    if color_constants:
        first_line = min(item["line"] for item in color_constants)
        names = ", ".join(item["name"] for item in color_constants)
        lines.append(
            f"- Color palette family (starting line {first_line}): {names}"
        )

    for constant in other_constants:
        lines.append(
            f"- {constant['name']} (line {constant['line']}): {constant['value']}"
        )

    return lines


def _format_class_summary(class_info: dict) -> list[str]:
    bases = ", ".join(class_info["bases"]) if class_info["bases"] else "object"
    layer = _infer_layer(class_info)
    lines = [
        f"- {class_info['name']} (line {class_info['line']}) inherits {bases}.",
        f"  Role: {_infer_role(class_info)}",
    ]

    visible_attributes = [
        attribute["name"]
        for attribute in class_info["class_attributes"]
        if not (
            attribute["name"].startswith("__") and attribute["name"].endswith("__")
        )
    ]
    if visible_attributes:
        attribute_label = "State properties" if layer == "Model" else "Class attributes"
        attribute_names = ", ".join(
            attribute_name for attribute_name in visible_attributes
        )
        lines.append(f"  {attribute_label}: {attribute_names}")

    for label, method_names in _categorize_methods(class_info):
        lines.append(f"  {label}: {', '.join(method_names)}")

    return lines


def build_local_architecture_summary(source_path: pathlib.Path, module_info: dict) -> str:
    """Create a deterministic architecture summary without external services."""
    lines = [f"Local summary for {source_path.name}"]

    docstring = module_info.get("docstring")
    if docstring:
        lines.append("")
        lines.append("Module overview")
        lines.append(f"- {_clip_text(docstring.splitlines()[0])}")

    functions = module_info["functions"]
    if functions:
        lines.append("")
        lines.append("Top-level functions")
        for function_info in functions:
            lines.append(
                f"- {function_info['name']} (line {function_info['line']}): {_describe_function(function_info)}"
            )

    constants = module_info["constants"]
    if constants:
        lines.append("")
        lines.append("Top-level constants")
        lines.extend(_format_constant_groups(constants))

    classes = module_info["classes"]
    if not classes:
        lines.append("")
        lines.append("Architecture layers")
        lines.append("- No classes were found.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Architecture layers")

    grouped_classes = {"Model": [], "Controller": [], "View": [], "Application": [], "Other": []}
    for class_info in classes:
        grouped_classes[_infer_layer(class_info)].append(class_info)

    for layer_name in ("Model", "Controller", "View", "Application", "Other"):
        layer_classes = grouped_classes[layer_name]
        if not layer_classes:
            continue
        lines.append(f"{layer_name} layer")
        for class_info in layer_classes:
            lines.extend(_format_class_summary(class_info))
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def summarize_with_claude(source_path: pathlib.Path, class_report: str) -> str:
    """
    Send main.py source + the pre-parsed class report to Claude.
    Returns Claude's full summary string.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. "
            "Run without the key to use the local summary fallback instead."
        )
    if anthropic is None:
        raise ImportError(
            "The anthropic package is not installed. "
            "Install it to enable Claude-based summaries."
        )

    client = anthropic.Anthropic(api_key=api_key)
    source_code = source_path.read_text(encoding="utf-8")

    system_prompt = (
        "You are a Python code analyst. "
        "When given source code and a pre-parsed class inventory, you produce a "
        "clear, structured summary that explains:\n"
        "  - How to locate each class in the file (line numbers, naming patterns)\n"
        "  - The inheritance hierarchy and what each subclass adds or overrides\n"
        "  - The main responsibilities of each class\n"
        "  - Key methods grouped by purpose (setup, drawing, event handling, etc.)\n"
        "Be concise but complete. Use Markdown headings and bullet points."
    )

    user_message = (
        "## Pre-parsed class inventory\n\n"
        f"```\n{class_report}\n```\n\n"
        "## Full source code\n\n"
        f"```python\n{source_code}\n```\n\n"
        "Please produce the structured architecture summary described in the system prompt."
    )

    summary_parts: list[str] = []
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=64000,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for event in stream.text_stream:
            summary_parts.append(event)
            print(event, end="", flush=True)

    print()
    return "".join(summary_parts)


def _print_local_summary(source_path: pathlib.Path, module_info: dict, reason: str):
    print("=" * 60)
    print(f"LOCAL ARCHITECTURE SUMMARY ({reason})")
    print("=" * 60)
    print(build_local_architecture_summary(source_path, module_info))


def main():
    here = pathlib.Path(__file__).parent.resolve()
    target = here / "main.py"

    if not target.exists():
        raise FileNotFoundError(f"Could not find {target}")

    print(f"Scanning {target} ...\n")
    module_info = analyze_module(target)
    classes = module_info["classes"]
    report = build_class_report(target, classes)

    print("=" * 60)
    print("LOCAL CLASS INVENTORY (via AST)")
    print("=" * 60)
    print(report)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        _print_local_summary(target, module_info, "ANTHROPIC_API_KEY not set")
        return

    if anthropic is None:
        _print_local_summary(target, module_info, "anthropic package not installed")
        return

    print("=" * 60)
    print("CLAUDE ARCHITECTURE SUMMARY (streaming)")
    print("=" * 60 + "\n")
    try:
        summarize_with_claude(target, report)
    except Exception as exc:
        print(f"\nClaude summary failed: {exc}\n")
        _print_local_summary(target, module_info, "Claude summary unavailable")


if __name__ == "__main__":
    main()
