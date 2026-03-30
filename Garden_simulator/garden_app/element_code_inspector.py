import inspect
import linecache
from pathlib import Path

from kivy.uix.widget import Widget


_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = None
_ORIGIN_ATTR = "_code_inspector_origin"
_ADD_SITE_ATTR = "_code_inspector_add_site"
_ORIGINAL_WIDGET_INIT = None
_ORIGINAL_ADD_WIDGET = None
_TRACKER_INSTALLED = False


def _resolve_path(path_value):
    try:
        return Path(path_value).resolve()
    except (OSError, RuntimeError, TypeError):
        return None


def _is_relative_to(path_value, parent_value):
    try:
        path_value.relative_to(parent_value)
        return True
    except ValueError:
        return False


def _project_frames():
    """Walk the call stack and return frames whose source file lives under _PROJECT_ROOT."""
    frame = inspect.currentframe()
    if frame is None:
        return []

    frames = []
    frame = frame.f_back
    while frame is not None:
        path_value = _resolve_path(frame.f_code.co_filename)
        if (
            path_value is not None
            and path_value != _THIS_FILE
            and _PROJECT_ROOT is not None
            and _is_relative_to(path_value, _PROJECT_ROOT)
        ):
            frames.append(
                {
                    "path": path_value,
                    "line": frame.f_lineno,
                    "function": frame.f_code.co_name,
                    "source_line": linecache.getline(str(path_value), frame.f_lineno).rstrip(),
                }
            )
        frame = frame.f_back
    return frames


def _find_creation_origin(class_name):
    """Find the project frame that instantiated class_name."""
    candidates = _project_frames()
    if not candidates:
        return None

    for candidate in candidates:
        source_line = candidate["source_line"].replace(" ", "")
        if f"{class_name}(" in source_line and "super().__init__(" not in source_line:
            return candidate

    for candidate in candidates:
        if "super().__init__(" not in candidate["source_line"].replace(" ", ""):
            return candidate

    return candidates[0]


def _find_add_site():
    """Find the project frame that called add_widget for this element."""
    candidates = _project_frames()
    if not candidates:
        return None
    for candidate in candidates:
        if "add_widget(" in candidate["source_line"].replace(" ", ""):
            return candidate
    return candidates[0] if candidates else None


def install_widget_creation_tracker(project_root):
    """Patch Widget.__init__ and Widget.add_widget to record creation and
    placement sites for every new element added to the widget tree."""
    global _ORIGINAL_WIDGET_INIT, _ORIGINAL_ADD_WIDGET, _PROJECT_ROOT, _TRACKER_INSTALLED

    _PROJECT_ROOT = _resolve_path(project_root)
    if _TRACKER_INSTALLED:
        return

    # Capture originals in local variables so the closures below never call None.
    original_init = Widget.__init__
    original_add_widget = Widget.add_widget

    _ORIGINAL_WIDGET_INIT = original_init
    _ORIGINAL_ADD_WIDGET = original_add_widget

    def tracked_widget_init(widget, *args, **kwargs):
        original_init(widget, *args, **kwargs)
        if getattr(widget, _ORIGIN_ATTR, None) is not None:
            return
        origin = _find_creation_origin(widget.__class__.__name__)
        if origin is not None:
            setattr(widget, _ORIGIN_ATTR, origin)

    def tracked_add_widget(self, widget, *args, **kwargs):
        original_add_widget(self, widget, *args, **kwargs)
        # Only record the first time a widget is added to any parent.
        if getattr(widget, _ADD_SITE_ATTR, None) is not None:
            return
        add_site = _find_add_site()
        if add_site is not None:
            setattr(widget, _ADD_SITE_ATTR, add_site)

    Widget.__init__ = tracked_widget_init
    Widget.add_widget = tracked_add_widget
    _TRACKER_INSTALLED = True


# ---------------------------------------------------------------------------
# Report building
# ---------------------------------------------------------------------------

def _format_lines(lines, start_line):
    return "\n".join(
        f"{line_number:4}: {line_text.rstrip()}"
        for line_number, line_text in enumerate(lines, start_line)
    )


def _read_source_lines(path_value):
    try:
        return path_value.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return path_value.read_text(encoding="utf-8", errors="replace").splitlines()


def make_report(title, details=None, snippets=None):
    return {
        "title": title,
        "details": list(details or []),
        "snippets": [snippet for snippet in (snippets or []) if snippet is not None],
    }


def snippet_from_file(path_value, line_number, header, context=4):
    resolved_path = _resolve_path(path_value)
    if resolved_path is None or not resolved_path.exists():
        return None

    lines = _read_source_lines(resolved_path)
    start_line = max(1, line_number - context)
    end_line = min(len(lines), line_number + context)
    excerpt_lines = lines[start_line - 1 : end_line]

    return {
        "header": header,
        "path": str(resolved_path),
        "start_line": start_line,
        "body": _format_lines(excerpt_lines, start_line),
    }


def snippet_from_callable(callable_obj, header, highlight=None, context=6, max_lines=80):
    try:
        source_lines, start_line = inspect.getsourcelines(callable_obj)
        source_path = inspect.getsourcefile(callable_obj)
    except (OSError, IOError, TypeError):
        return None

    if source_path is None:
        return None

    selected_start = start_line
    selected_lines = source_lines

    if highlight is not None:
        for index, line_text in enumerate(source_lines):
            if highlight in line_text:
                clip_start = max(0, index - context)
                clip_end = min(len(source_lines), index + context + 1)
                selected_start = start_line + clip_start
                selected_lines = source_lines[clip_start:clip_end]
                break

    if len(selected_lines) > max_lines:
        selected_lines = selected_lines[:max_lines]
        selected_lines.append("    ...\n")

    return {
        "header": header,
        "path": str(_resolve_path(source_path) or source_path),
        "start_line": selected_start,
        "body": _format_lines(selected_lines, selected_start),
    }


def build_widget_report(widget):
    """Build a full inspection report for a widget, including creation and add sites."""
    details = [
        f"Widget class: {widget.__class__.__name__}",
        f"Widget module: {widget.__class__.__module__}",
        f"Widget id: {hex(id(widget))}",
    ]

    widget_text = getattr(widget, "text", None)
    if isinstance(widget_text, str) and widget_text.strip():
        details.append(f"Widget text: {widget_text!r}")

    snippets = []

    origin = getattr(widget, _ORIGIN_ATTR, None)
    if origin is not None:
        details.append(
            f"Creation site: {origin['path']}:{origin['line']} in {origin['function']}()"
        )
        snippets.append(
            snippet_from_file(origin["path"], origin["line"], "Widget creation site")
        )
    else:
        details.append("Creation site: unavailable")

    add_site = getattr(widget, _ADD_SITE_ATTR, None)
    if add_site is not None:
        details.append(
            f"Added to parent at: {add_site['path']}:{add_site['line']} in {add_site['function']}()"
        )
        snippets.append(
            snippet_from_file(add_site["path"], add_site["line"], "add_widget call site")
        )

    try:
        class_path = inspect.getsourcefile(widget.__class__)
        _, class_line = inspect.getsourcelines(widget.__class__)
    except (OSError, IOError, TypeError):
        class_path = None
        class_line = None

    if class_path is not None and class_line is not None:
        details.append(f"Class source: {class_path}:{class_line}")
        resolved_class_path = _resolve_path(class_path)
        if resolved_class_path is not None and _PROJECT_ROOT is not None:
            if _is_relative_to(resolved_class_path, _PROJECT_ROOT):
                snippets.append(
                    snippet_from_callable(
                        widget.__class__,
                        "Widget class definition",
                        highlight=f"class {widget.__class__.__name__}",
                        context=4,
                        max_lines=60,
                    )
                )

    return make_report(
        title=f"Right-click inspector: {widget.__class__.__name__}",
        details=details,
        snippets=snippets,
    )


# ---------------------------------------------------------------------------
# Output: console + in-app popup
# ---------------------------------------------------------------------------

def _print_report(report):
    print("\n=== Code Inspector ===")
    print(report["title"])
    for detail in report.get("details", []):
        print(f"- {detail}")
    for snippet in report.get("snippets", []):
        print(
            f"\n--- {snippet['header']} ({snippet['path']}:{snippet['start_line']}) ---"
        )
        print(snippet["body"])
    print("=== End Code Inspector ===\n")


def _show_report_popup(report):
    """Display an inspection report as a scrollable in-app popup."""
    try:
        from kivy.uix.popup import Popup
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.label import Label
    except Exception:
        _print_report(report)
        return

    lines = [f"=== {report['title']} ===", ""]
    for detail in report.get("details", []):
        lines.append(f"  {detail}")
    lines.append("")
    for snippet in report.get("snippets", []):
        lines.append(
            f"--- {snippet['header']}  [{snippet['path']}:{snippet['start_line']}] ---"
        )
        lines.append(snippet["body"])
        lines.append("")

    full_text = "\n".join(lines)

    lbl = Label(
        text=full_text,
        font_size=11,
        halign="left",
        valign="top",
        markup=False,
        size_hint_y=None,
    )
    # When the label gets a width from the ScrollView layout pass, enable word
    # wrap at that width; when the texture is re-computed, stretch the height
    # so the ScrollView can scroll the full content.
    lbl.bind(width=lambda *_: setattr(lbl, "text_size", (lbl.width, None)))
    lbl.bind(texture_size=lambda *_: setattr(lbl, "height", lbl.texture_size[1]))

    sv = ScrollView(size_hint=(1, 1), do_scroll_x=False)
    sv.add_widget(lbl)

    popup = Popup(
        title="Code Inspector",
        content=sv,
        size_hint=(0.95, 0.85),
    )
    popup.open()


# ---------------------------------------------------------------------------
# Entry point used by GardenLayout
# ---------------------------------------------------------------------------

def _find_deepest_widget(widget, pos):
    if not widget.collide_point(*pos):
        return None
    for child in widget.children:
        candidate = _find_deepest_widget(child, pos)
        if candidate is not None:
            return candidate
    return widget


def handle_right_click(root_widget, touch, report_builder=None):
    if getattr(touch, "button", None) != "right":
        return False

    target_widget = _find_deepest_widget(root_widget, touch.pos) or root_widget
    report = None
    if report_builder is not None:
        report = report_builder(target_widget, touch)
    if report is None:
        report = build_widget_report(target_widget)

    _print_report(report)
    _show_report_popup(report)
    return True
