#!/usr/bin/python3
"""Capture full-screen notes and arrange up to three on landscape A4 sheets."""

from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw


APP_NAME = "Notesheet"
SHORTCUT = "<Alt>Print"
CUSTOM_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/notesheet/"
MEDIA_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
SHELL_KEYS_SCHEMA = "org.gnome.shell.keybindings"

# Physical page geometry. The third screenshot is turned 90 degrees counterclockwise.
A4_WIDTH_MM = 297.0
A4_HEIGHT_MM = 210.0
PAGE_MARGIN_MM = 5.0
GAP_MM = 0.0
TARGET_WIDTH_MM = 180.0
OUTPUT_DPI = 300
PREVIEW_WIDTH = 620
PREVIEW_HEIGHT = 438


def pictures_dir() -> Path:
    """Use the XDG Pictures location when available, with a safe default."""
    try:
        result = subprocess.run(
            ["xdg-user-dir", "PICTURES"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        candidate = Path(result.stdout.strip()).expanduser()
        if candidate.is_absolute():
            return candidate
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / "Pictures"


ROOT = pictures_dir() / "NoteCaptures"
CAPTURES_DIR = ROOT / "Captures"
SHEETS_DIR = ROOT / "Sheets"
STATE_PATH = ROOT / ".notesheet-state.json"


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def capture_display_name(path: Path) -> str:
    """Return the user-provided name when a capture has one."""
    match = re.fullmatch(r"screen-\d{8}-\d{6}-\d+-(.+)", path.stem)
    return match.group(1) if match else path.name


def capture_datetime(path: Path) -> datetime:
    """Read the capture timestamp from its filename, falling back to file time."""
    match = re.match(r"screen-(\d{8}-\d{6}-\d{6})(?:-|$)", path.stem)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S-%f")
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime)


def safe_capture_name(name: str) -> str:
    """Keep a capture name readable while removing path separators and controls."""
    name = "".join(character for character in name.strip() if character.isprintable())
    name = name.replace("/", "-").replace("\\", "-")
    return re.sub(r"\s+", " ", name).strip(" .")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"pending": [], "sheets": []}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state is not an object")
        data.setdefault("pending", [])
        data.setdefault("sheets", [])
        return data
    except (OSError, ValueError, json.JSONDecodeError):
        raise RuntimeError(
            f"Could not read {STATE_PATH}. Move it aside and try again."
        )


def save_state(state: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, STATE_PATH)


def notify(title: str, body: str) -> None:
    try:
        subprocess.run(
            ["notify-send", "--urgency=critical", title, body],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def dialog_error(message: str) -> None:
    try:
        subprocess.run(
            ["zenity", "--error", "--title", APP_NAME, "--text", message],
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        print(f"{APP_NAME}: {message}", file=sys.stderr)


def get_shortcut_binding() -> str:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    return Gio.Settings.new_with_path(CUSTOM_SCHEMA, CUSTOM_PATH).get_string("binding")


def format_shortcut(binding: str) -> str:
    if not binding:
        return "Disabled"
    modifier_labels = {
        "Primary": "Ctrl",
        "Control": "Ctrl",
        "Ctrl": "Ctrl",
        "Alt": "Alt",
        "Shift": "Shift",
        "Super": "Super",
        "Meta": "Meta",
        "Hyper": "Hyper",
    }
    modifiers = []
    while binding.startswith("<") and ">" in binding:
        token, binding = binding[1:].split(">", 1)
        modifiers.append(modifier_labels.get(token, token))

    key_labels = {
        "Print": "Print Screen",
        "space": "Space",
        "Page_Up": "Page Up",
        "Page_Down": "Page Down",
        "KP_Enter": "Keypad Enter",
        "KP_Add": "Keypad +",
        "KP_Subtract": "Keypad −",
        "KP_Multiply": "Keypad ×",
        "KP_Divide": "Keypad ÷",
        "KP_Decimal": "Keypad .",
    }
    key = key_labels.get(binding, binding.replace("_", " "))
    if len(key) == 1 and key.isalpha():
        key = key.upper()
    return "+".join([*modifiers, key]) if modifiers else key


def canonical_shortcut_binding(binding: str) -> str:
    """Use accelerator modifier names that GNOME settings accept consistently."""
    return binding.replace("<Primary>", "<Control>").replace("<Ctrl>", "<Control>")


def set_shortcut_binding(binding: str) -> None:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    binding = canonical_shortcut_binding(binding)
    state = load_state()
    restore = state.get("shortcut_backup", [SHORTCUT])
    shell_keys = Gio.Settings.new(SHELL_KEYS_SCHEMA)
    shell_keys.set_strv("screenshot-window", [key for key in restore if key != binding])

    media_keys = Gio.Settings.new(MEDIA_KEYS_SCHEMA)
    custom = Gio.Settings.new_with_path(CUSTOM_SCHEMA, CUSTOM_PATH)
    custom.set_string("name", "Notesheet full-screen capture")
    custom.set_string(
        "command",
        shlex.join([sys.executable, str(Path(__file__).resolve()), "capture"]),
    )
    custom.set_string("binding", binding)
    paths = media_keys.get_strv("custom-keybindings")
    if CUSTOM_PATH not in paths:
        media_keys.set_strv("custom-keybindings", paths + [CUSTOM_PATH])


def request_capture_name(Gtk) -> str | None:
    dialog = Gtk.Dialog(title="Save screenshot", modal=True)
    dialog.add_button("Cancel capture", Gtk.ResponseType.CANCEL)
    dialog.add_button("Save", Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)
    dialog.set_default_size(420, 130)

    content = dialog.get_content_area()
    content.set_border_width(16)
    content.set_spacing(10)
    instruction = Gtk.Label(
        label=(
            "Leave the name blank to use the default format: "
            "screen-YYYYMMDD-HHMMSS-microseconds.png "
            "(for example, screen-20261020-132932-359695.png)."
        )
    )
    instruction.set_xalign(0)
    content.pack_start(instruction, False, False, 0)
    name_entry = Gtk.Entry()
    name_entry.set_placeholder_text("Screenshot name (optional)")
    name_entry.set_max_length(100)
    name_entry.set_activates_default(True)
    content.pack_start(name_entry, False, False, 0)

    dialog.show_all()
    name_entry.grab_focus()
    response = dialog.run()
    name = name_entry.get_text().strip() if response == Gtk.ResponseType.ACCEPT else None
    dialog.destroy()
    return name


def capture_full_screen() -> Path | None:
    """Capture the X11 desktop root window through GNOME's GDK bindings."""
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk

        Gtk.init([])
        display = Gdk.Display.get_default()
        if display is None:
            raise RuntimeError("No graphical display is available.")
        screen = display.get_default_screen()
        root_window = screen.get_root_window()
        if root_window is None:
            raise RuntimeError("Could not access the desktop screenshot surface.")
        width = root_window.get_width()
        height = root_window.get_height()
        pixbuf = Gdk.pixbuf_get_from_window(root_window, 0, 0, width, height)
        if pixbuf is None:
            raise RuntimeError("The desktop did not provide a screenshot image.")
        name = request_capture_name(Gtk)
        if name is None:
            return None
        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = safe_capture_name(name)
        name_suffix = f"-{safe_name}" if safe_name else ""
        output = CAPTURES_DIR / f"screen-{timestamp()}{name_suffix}.png"
        pixbuf.savev(str(output), "png", [], [])
        return output
    except Exception as exc:
        raise RuntimeError(f"Screenshot capture failed: {exc}") from exc


def compose_page(image_paths: list[str], dpi: int = OUTPUT_DPI) -> Image.Image:
    """Render one to three shots on the same A4 layout used by the preview."""
    if not 1 <= len(image_paths) <= 3:
        raise ValueError("Choose between one and three screenshots.")
    sources = [Image.open(path).convert("RGB") for path in image_paths]
    try:
        aspects = [source.width / source.height for source in sources]
        printable_w = A4_WIDTH_MM - 2 * PAGE_MARGIN_MM
        printable_h = A4_HEIGHT_MM - 2 * PAGE_MARGIN_MM
        if len(sources) == 1:
            image_w_mm = min(TARGET_WIDTH_MM, printable_w, printable_h * aspects[0])
        elif len(sources) == 2:
            max_by_stack = (printable_h - GAP_MM) / (1 / aspects[0] + 1 / aspects[1])
            image_w_mm = min(TARGET_WIDTH_MM, printable_w, max_by_stack)
        elif len(sources) == 3:
            max_by_stack = (printable_h - GAP_MM) / (1 / aspects[0] + 1 / aspects[1])
            max_by_right_column = (printable_w - GAP_MM) / (1 + 1 / aspects[2])
            image_w_mm = min(TARGET_WIDTH_MM, max_by_stack, max_by_right_column, printable_h)

        px_per_mm = dpi / 25.4
        page_w = round(A4_WIDTH_MM * px_per_mm)
        page_h = round(A4_HEIGHT_MM * px_per_mm)
        margin = round(PAGE_MARGIN_MM * px_per_mm)
        gap = round(GAP_MM * px_per_mm)
        image_w = round(image_w_mm * px_per_mm)
        image_heights = [round((image_w_mm / aspect) * px_per_mm) for aspect in aspects]

        page = Image.new("RGB", (page_w, page_h), "white")
        seam_width = max(1, round(0.3 * px_per_mm))
        seams: list[tuple[tuple[int, int], tuple[int, int]]] = []
        if len(sources) == 1:
            x = (page_w - image_w) // 2
            y = (page_h - image_heights[0]) // 2
            resized = sources[0].resize(
                (image_w, image_heights[0]), Image.Resampling.LANCZOS
            )
            page.paste(resized, (x, y))
        else:
            stack_height = sum(image_heights[:2]) + gap
            first_y = margin + (page_h - 2 * margin - stack_height) // 2
            left_positions = ((0, first_y), (1, first_y + image_heights[0] + gap))
            for index, y in left_positions:
                resized = sources[index].resize(
                    (image_w, image_heights[index]), Image.Resampling.LANCZOS
                )
                page.paste(resized, (margin, y))
            first_bottom = left_positions[0][1] + image_heights[0]
            second_y = left_positions[1][1]
            if first_bottom == second_y:
                seams.append(((margin, second_y), (margin + image_w - 1, second_y)))

            if len(sources) == 3:
                turned = sources[2].resize(
                    (image_w, image_heights[2]), Image.Resampling.LANCZOS
                ).rotate(90, expand=True)
                right_x = margin + image_w + gap
                right_y = (page_h - turned.height) // 2
                page.paste(turned, (right_x, right_y))
                left_bottom = left_positions[1][1] + image_heights[1]
                shared_top = max(first_y, right_y)
                shared_bottom = min(left_bottom, right_y + turned.height)
                if right_x == margin + image_w and shared_top < shared_bottom:
                    seams.append(((right_x, shared_top), (right_x, shared_bottom - 1)))
        if seams:
            draw = ImageDraw.Draw(page)
            for start, end in seams:
                draw.line((start, end), fill="black", width=seam_width)
        return page
    finally:
        for source in sources:
            source.close()


def create_sheet_pdf(
    image_paths: list[str], output_path: Path | None = None
) -> Path:
    page = compose_page(image_paths, OUTPUT_DPI)
    output = output_path or SHEETS_DIR / f"notesheet-{timestamp()}.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    page.save(output, "PDF", resolution=OUTPUT_DPI)
    page.close()
    return output


def query_printers() -> tuple[str | None, list[str]]:
    """Return the CUPS default destination and available printer queues."""
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    default_result = subprocess.run(
        ["lpstat", "-d"], capture_output=True, text=True, timeout=5, env=env
    )
    default_printer = None
    for line in default_result.stdout.splitlines():
        prefix = "system default destination:"
        if line.lower().startswith(prefix):
            default_printer = line.split(":", 1)[1].strip() or None
            break

    list_result = subprocess.run(
        ["lpstat", "-e"], capture_output=True, text=True, timeout=5, env=env
    )
    if list_result.returncode != 0 and default_result.returncode != 0:
        details = (list_result.stderr or default_result.stderr).strip()
        raise RuntimeError(details or "Could not query CUPS printer queues.")
    printers = {line.strip() for line in list_result.stdout.splitlines() if line.strip()}
    if default_printer:
        printers.add(default_printer)
    return default_printer, sorted(printers, key=str.casefold)


def submit_to_printer(pdf_path: Path, printer: str | None = None) -> str:
    command = ["lp"]
    if printer:
        command.extend(["-d", printer])
    command.extend(["-o", "media=A4", str(pdf_path)])
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() or "Print job submitted to CUPS."


def remember_sheet(pdf_path: Path, image_paths: list[str]) -> None:
    state = load_state()
    state["sheets"].append(
        {
            "pdf": str(pdf_path),
            "images": image_paths,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "printed": False,
        }
    )
    save_state(state)


def mark_printed(pdf_path: Path) -> None:
    state = load_state()
    for sheet in state.get("sheets", []):
        if sheet.get("pdf") == str(pdf_path):
            sheet["printed"] = True
            sheet["printed_at"] = datetime.now().isoformat(timespec="seconds")
            break
    save_state(state)


def capture() -> int:
    try:
        shot = capture_full_screen()
        if shot is None:
            return 0
        notify("Screenshot saved", f"Open Notesheet to choose shots and print.\n{shot}")
        return 0
    except Exception as exc:
        dialog_error(str(exc))
        return 1


def latest_sheet(state: dict) -> Path | None:
    for sheet in reversed(state.get("sheets", [])):
        candidate = Path(sheet.get("pdf", ""))
        if candidate.is_file():
            return candidate
    if SHEETS_DIR.exists():
        candidates = sorted(SHEETS_DIR.glob("notesheet-*.pdf"), key=lambda p: p.stat().st_mtime)
        if candidates:
            return candidates[-1]
    return None


def print_latest() -> int:
    pdf_path = latest_sheet(load_state())
    if pdf_path is None:
        print("No Notesheet PDF exists yet. Select one or more screenshots in Notesheet.", file=sys.stderr)
        return 1
    try:
        print(submit_to_printer(pdf_path))
        mark_printed(pdf_path)
        return 0
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Could not print {pdf_path}: {exc}", file=sys.stderr)
        return 1


def open_latest() -> int:
    pdf_path = latest_sheet(load_state())
    if pdf_path is None:
        print("No Notesheet PDF exists yet. Select one or more screenshots in Notesheet.", file=sys.stderr)
        return 1
    subprocess.Popen(["xdg-open", str(pdf_path)])
    return 0


def run_ui() -> int:
    try:
        import gi

        gi.require_version("Gdk", "3.0")
        gi.require_version("Gtk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
    except Exception as exc:
        print(f"Could not load the Notesheet interface: {exc}", file=sys.stderr)
        return 1

    class NotesheetWindow(Gtk.Window):
        def __init__(self) -> None:
            super().__init__(title="Notesheet")
            self.set_wmclass("notesheet", "Notesheet")
            self.set_icon_name("notesheet")
            self.set_default_size(1120, 760)
            self.set_border_width(14)
            self.selected_paths: list[str] = []
            self.focus_path: str | None = None
            self.checks: dict[str, Gtk.CheckButton] = {}
            self.row_paths: dict[Gtk.ListBoxRow, str] = {}
            self.date_from: date | None = None
            self.date_to: date | None = None
            self.date_picker_buttons: dict[str, Gtk.Button] = {}
            self.date_picker_signal_ids: dict[str, int] = {}
            self.date_picker_popovers: dict[str, Gtk.Popover] = {}
            self.inventory: tuple = ()
            self.rebuilding = False

            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            self.add(outer)

            heading = Gtk.Label()
            heading.set_markup("<span size='x-large' weight='bold'>Notesheet</span>\nChoose one to three captures, then print an A4 preview.")
            heading.set_xalign(0)
            outer.pack_start(heading, False, False, 0)

            toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            outer.pack_start(toolbar, False, False, 0)
            self.shortcut_label = Gtk.Label()
            self.update_shortcut_label()
            toolbar.pack_start(self.shortcut_label, False, False, 0)
            shortcut_button = Gtk.Button(label="Change…")
            shortcut_button.connect("clicked", self.change_shortcut)
            toolbar.pack_start(shortcut_button, False, False, 0)
            folder_button = Gtk.Button(label="Open capture folder")
            folder_button.connect("clicked", lambda *_: subprocess.Popen(["xdg-open", str(CAPTURES_DIR)]))
            toolbar.pack_end(folder_button, False, False, 0)

            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            outer.pack_start(content, True, True, 0)

            library = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            library.set_size_request(385, -1)
            content.pack_start(library, False, True, 0)
            library_heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            library_title = Gtk.Label(label="Saved screenshots")
            library_title.set_xalign(0)
            library_title.set_hexpand(True)
            library_heading.pack_start(library_title, True, True, 0)
            refresh_button = Gtk.Button(label="Refresh")
            refresh_button.connect("clicked", lambda *_: self.refresh_library(force=True))
            library_heading.pack_end(refresh_button, False, False, 0)
            library.pack_start(library_heading, False, False, 0)

            self.search_entry = Gtk.SearchEntry()
            self.search_entry.set_placeholder_text("Search screenshots by name")
            self.search_entry.connect(
                "search-changed", lambda *_: self.refresh_library(force=True)
            )
            library.pack_start(self.search_entry, False, False, 0)

            date_title = Gtk.Label(label="Capture date")
            date_title.set_xalign(0)
            library.pack_start(date_title, False, False, 0)
            date_filter_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            for bound, caption in (("from", "From"), ("to", "To")):
                date_field = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                date_caption = Gtk.Label(label=caption)
                date_caption.set_xalign(0)
                date_field.pack_start(date_caption, False, False, 0)
                date_button = Gtk.Button(label="Any date")
                date_button.set_tooltip_text(f"Choose the {caption.lower()} date")
                date_popover = Gtk.Popover.new(date_button)
                date_popover.set_position(Gtk.PositionType.BOTTOM)
                date_calendar = Gtk.Calendar()
                date_popover.add(date_calendar)
                date_button.connect(
                    "clicked", self.toggle_date_picker, bound, date_popover, date_calendar
                )
                signal_id = date_calendar.connect(
                    "day-selected", self.on_date_bound_selected, bound, date_popover
                )
                date_field.pack_start(date_button, False, False, 0)
                date_filter_row.pack_start(date_field, True, True, 0)
                self.date_picker_buttons[bound] = date_button
                self.date_picker_signal_ids[bound] = signal_id
                self.date_picker_popovers[bound] = date_popover
            self.clear_date_button = Gtk.Button(label="Clear")
            self.clear_date_button.set_tooltip_text("Clear both date limits")
            self.clear_date_button.set_size_request(56, 30)
            self.clear_date_button.set_valign(Gtk.Align.CENTER)
            self.clear_date_button.set_no_show_all(True)
            self.clear_date_button.connect("clicked", self.clear_date_filter)
            clear_style = Gtk.CssProvider()
            clear_style.load_from_data(
                b"""
                button.date-filter-clear {
                    padding: 2px 7px;
                    min-width: 0;
                    min-height: 0;
                    color: #c1cbd5;
                    background-image: none;
                    background-color: #39434d;
                    border: 1px solid #4c5966;
                    border-radius: 5px;
                }
                button.date-filter-clear:hover {
                    background-color: #46535f;
                }
                button.delete-selection {
                    color: #ffffff;
                    background-image: none;
                    background-color: #873c42;
                    border: 1px solid #a45157;
                    border-radius: 5px;
                }
                button.delete-selection:hover {
                    background-color: #9b474d;
                }
                button.delete-selection:active {
                    background-color: #713238;
                }
                button.delete-selection:disabled {
                    color: #c0aeb0;
                    background-color: #51383b;
                    border-color: #604447;
                }
                row:selected:not(.capture-selected) {
                    background-image: none;
                    background-color: transparent;
                    box-shadow: none;
                    color: #f2f2f2;
                }
                row.capture-selected {
                    background-image: none;
                    background-color: #246db0;
                    color: #ffffff;
                }
                row.capture-selected label {
                    color: #ffffff;
                }
                row.capture-selected label.dim-label {
                    color: #dceafa;
                }
                """
            )
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                clear_style,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            self.clear_date_button.get_style_context().add_class("date-filter-clear")
            date_filter_row.pack_end(self.clear_date_button, False, False, 0)
            library.pack_start(date_filter_row, False, False, 0)

            self.listbox = Gtk.ListBox()
            self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
            self.listbox.connect("row-selected", self.on_row_selected)
            self.listbox.set_filter_func(self.filter_capture_row)
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroll.add(self.listbox)
            library.pack_start(scroll, True, True, 0)

            library_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            library_actions.set_margin_top(12)
            library.pack_start(library_actions, False, False, 0)
            clear_button = Gtk.Button(label="Clear selection")
            clear_button.connect("clicked", self.clear_selection)
            library_actions.pack_start(clear_button, True, True, 0)
            self.delete_selected_button = Gtk.Button(label="Delete selection")
            self.delete_selected_button.connect("clicked", self.delete_selected)
            self.delete_selected_button.set_sensitive(False)
            self.delete_selected_button.get_style_context().add_class("delete-selection")
            library_actions.pack_start(self.delete_selected_button, True, True, 0)

            preview_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            content.pack_start(preview_column, True, True, 0)
            self.preview_title = Gtk.Label(label="A4 landscape preview")
            self.preview_title.set_xalign(0)
            preview_column.pack_start(self.preview_title, False, False, 0)
            preview_frame = Gtk.Frame()
            preview_frame.set_shadow_type(Gtk.ShadowType.IN)
            preview_column.pack_start(preview_frame, True, True, 0)
            self.preview_image = Gtk.Image()
            self.preview_image.set_size_request(PREVIEW_WIDTH, PREVIEW_HEIGHT)
            self.preview_image.set_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG)
            preview_frame.add(self.preview_image)

            self.layout_label = Gtk.Label(label="Select screenshots to see their paper layout.")
            self.layout_label.set_xalign(0)
            preview_column.pack_start(self.layout_label, False, False, 0)
            preview_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            preview_column.pack_start(preview_actions, False, False, 0)
            self.print_button = Gtk.Button(label="Print selected")
            self.print_button.get_style_context().add_class("suggested-action")
            self.print_button.set_sensitive(False)
            self.print_button.connect("clicked", self.print_selected)
            preview_actions.pack_end(self.print_button, False, False, 0)

            self.status_label = Gtk.Label()
            self.status_label.set_xalign(0)
            outer.pack_start(self.status_label, False, False, 0)
            self.update_date_filter_label()

            self.connect("destroy", lambda *_args: Gtk.main_quit())
            self.refresh_library(force=True)
            GLib.timeout_add_seconds(2, self.periodic_refresh)
            self.show_all()
            self.update_preview()

        def list_capture_paths(self) -> list[Path]:
            if not CAPTURES_DIR.exists():
                return []
            paths = sorted(
                CAPTURES_DIR.glob("screen-*.png"),
                key=lambda path: (capture_datetime(path), path.stat().st_mtime_ns),
                reverse=True,
            )
            has_filter = (
                bool(self.search_entry.get_text().strip())
                or self.date_from is not None
                or self.date_to is not None
            )
            if not has_filter:
                return paths

            paths_by_text = {str(path): path for path in paths}
            selected = [
                paths_by_text[path_text]
                for path_text in self.selected_paths
                if path_text in paths_by_text
            ]
            selected_text = {str(path) for path in selected}
            return selected + [path for path in paths if str(path) not in selected_text]

        def inventory_key(self, paths: list[Path]) -> tuple:
            return tuple(
                sorted(
                    (str(path), path.stat().st_mtime_ns, path.stat().st_size)
                    for path in paths
                )
            )

        def filter_capture_row(self, row, *_args) -> bool:
            query = self.search_entry.get_text().strip().casefold()
            path_text = self.row_paths.get(row)
            if not path_text:
                return False
            if path_text in self.selected_paths:
                return True
            path = Path(path_text)
            if query and not (
                query in capture_display_name(path).casefold()
                or query in path.name.casefold()
            ):
                return False
            captured_on = capture_datetime(path).date()
            if self.date_from and captured_on < self.date_from:
                return False
            if self.date_to and captured_on > self.date_to:
                return False
            return True

        def toggle_date_picker(self, _button, bound: str, popover, calendar) -> None:
            if popover.get_visible():
                popover.popdown()
            else:
                selected = self.date_from if bound == "from" else self.date_to
                signal_id = self.date_picker_signal_ids[bound]
                calendar.handler_block(signal_id)
                if selected:
                    calendar.select_month(selected.month - 1, selected.year)
                    calendar.select_day(selected.day)
                else:
                    calendar.select_day(0)
                calendar.handler_unblock(signal_id)
                popover.show_all()
                popover.popup()

        def update_date_filter_label(self) -> None:
            for bound, selected in (("from", self.date_from), ("to", self.date_to)):
                label = selected.isoformat() if selected else "Any date"
                self.date_picker_buttons[bound].set_label(label)
            if self.date_from is not None or self.date_to is not None:
                self.clear_date_button.show()
            else:
                self.clear_date_button.hide()

        def on_date_bound_selected(self, calendar, bound: str, popover) -> None:
            year, month, day = calendar.get_date()
            selected = date(year, month + 1, day)
            if bound == "from":
                self.date_from = selected
            else:
                self.date_to = selected
            if self.date_from and self.date_to and self.date_from > self.date_to:
                self.date_from, self.date_to = self.date_to, self.date_from
            self.update_date_filter_label()
            self.refresh_library(force=True)
            popover.popdown()

        def clear_date_filter(self, *_args) -> None:
            self.date_from = None
            self.date_to = None
            self.update_date_filter_label()
            self.refresh_library(force=True)
            for popover in self.date_picker_popovers.values():
                popover.popdown()

        def periodic_refresh(self) -> bool:
            self.refresh_library()
            return True

        def refresh_library(self, force: bool = False) -> None:
            paths = self.list_capture_paths()
            current_inventory = self.inventory_key(paths)
            if not force and current_inventory == self.inventory:
                return
            self.inventory = current_inventory
            valid = {str(path) for path in paths}
            self.selected_paths = [path for path in self.selected_paths if path in valid]
            if self.focus_path not in valid:
                self.focus_path = None

            self.rebuilding = True
            for child in self.listbox.get_children():
                self.listbox.remove(child)
            self.checks.clear()
            self.row_paths.clear()

            for path in paths:
                path_text = str(path)
                row = Gtk.ListBoxRow()
                if path_text in self.selected_paths:
                    row.get_style_context().add_class("capture-selected")
                row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
                row_box.set_border_width(6)
                row.add(row_box)
                check = Gtk.CheckButton()
                check.set_active(path_text in self.selected_paths)
                check.connect("toggled", self.on_toggled, path_text)
                row_box.pack_start(check, False, False, 0)
                self.checks[path_text] = check

                content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
                content_click_area = Gtk.EventBox()
                content_click_area.set_visible_window(False)
                content_click_area.set_hexpand(True)
                content_click_area.add(content_box)
                content_click_area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
                content_click_area.connect(
                    "button-press-event", self.on_row_content_clicked, row, path_text
                )
                row_box.pack_start(content_click_area, True, True, 0)
                rename_button = Gtk.Button.new_from_icon_name(
                    "document-edit-symbolic", Gtk.IconSize.BUTTON
                )
                rename_button.set_relief(Gtk.ReliefStyle.NONE)
                rename_button.set_size_request(30, 30)
                rename_button.set_tooltip_text("Rename screenshot")
                rename_button.connect("clicked", self.rename_capture, path_text)
                row_box.pack_end(rename_button, False, False, 0)

                try:
                    thumbnail = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        path_text, 128, 76, True
                    )
                    image = Gtk.Image.new_from_pixbuf(thumbnail)
                except Exception:
                    image = Gtk.Image.new_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG)
                content_box.pack_start(image, False, False, 0)

                text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
                content_box.pack_start(text_box, True, True, 0)
                name = Gtk.Label(label=capture_display_name(path))
                name.set_xalign(0)
                text_box.pack_start(name, False, False, 0)
                try:
                    detail = capture_datetime(path).strftime("%Y-%m-%d %H:%M:%S")
                except OSError:
                    detail = "Capture time unavailable"
                details = Gtk.Label(label=detail)
                details.set_xalign(0)
                details.get_style_context().add_class("dim-label")
                text_box.pack_start(details, False, False, 0)

                self.row_paths[row] = path_text
                self.listbox.add(row)

            self.rebuilding = False
            self.listbox.show_all()
            if self.focus_path:
                for row, path_text in self.row_paths.items():
                    if path_text == self.focus_path:
                        self.listbox.select_row(row)
                        break
            self.update_preview()

        def on_row_selected(self, _listbox, row) -> None:
            self.focus_path = self.row_paths.get(row) if row else None

        def on_row_content_clicked(self, _widget, event, row, path_text: str) -> bool:
            if event.button != 1:
                return False
            self.listbox.select_row(row)
            self.set_capture_selected(
                path_text, path_text not in self.selected_paths
            )
            return True

        def rename_capture(self, _button, path_text: str) -> None:
            path = Path(path_text)
            if not path.is_file():
                self.show_error("This screenshot is no longer available.")
                self.refresh_library(force=True)
                return

            custom_name_match = re.fullmatch(
                r"screen-\d{8}-\d{6}-\d+-(.+)", path.stem
            )
            dialog = Gtk.Dialog(title="Rename screenshot", transient_for=self, modal=True)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.add_button("Save", Gtk.ResponseType.ACCEPT)
            dialog.set_default_response(Gtk.ResponseType.ACCEPT)
            content = dialog.get_content_area()
            content.set_border_width(16)
            content.set_spacing(10)
            instruction = Gtk.Label(
                label="Enter a name, or leave it blank to use the capture timestamp."
            )
            instruction.set_xalign(0)
            content.pack_start(instruction, False, False, 0)
            name_entry = Gtk.Entry()
            name_entry.set_placeholder_text("Screenshot name (optional)")
            name_entry.set_max_length(100)
            if custom_name_match:
                name_entry.set_text(custom_name_match.group(1))
                name_entry.select_region(0, -1)
            name_entry.set_activates_default(True)
            content.pack_start(name_entry, False, False, 0)
            dialog.show_all()
            name_entry.grab_focus()
            response = dialog.run()
            new_name = safe_capture_name(name_entry.get_text())
            dialog.destroy()
            if response != Gtk.ResponseType.ACCEPT:
                return

            capture_stamp = capture_datetime(path).strftime("%Y%m%d-%H%M%S-%f")
            suffix = f"-{new_name}" if new_name else ""
            target = path.with_name(f"screen-{capture_stamp}{suffix}.png")
            if target == path:
                return
            if target.exists():
                self.show_error("A screenshot with that timestamp and name already exists.")
                return

            try:
                path.rename(target)
            except OSError as exc:
                self.show_error(f"Could not rename the screenshot: {exc}")
                return

            old_path = str(path)
            new_path = str(target)
            self.selected_paths = [new_path if item == old_path else item for item in self.selected_paths]
            if self.focus_path == old_path:
                self.focus_path = new_path
            history_error = None
            try:
                state = load_state()
                state["pending"] = [
                    new_path if item == old_path else item
                    for item in state.get("pending", [])
                ]
                for sheet in state.get("sheets", []):
                    sheet["images"] = [
                        new_path if item == old_path else item
                        for item in sheet.get("images", [])
                    ]
                save_state(state)
            except Exception as exc:
                history_error = str(exc)

            self.refresh_library(force=True)
            if history_error:
                self.show_error(
                    f"The screenshot was renamed, but its saved history could not be updated: {history_error}"
                )
            else:
                display_name = new_name or target.name
                self.status_label.set_text(f"Screenshot renamed to {display_name}.")

        def on_toggled(self, button, path_text: str) -> None:
            if self.rebuilding:
                return
            self.set_capture_selected(path_text, button.get_active())

        def set_capture_selected(self, path_text: str, selected: bool) -> None:
            self.focus_path = path_text
            is_selected = path_text in self.selected_paths
            if selected and not is_selected:
                if len(self.selected_paths) >= 3:
                    selected = False
                    self.status_label.set_text("A sheet holds up to three screenshots.")
                else:
                    self.selected_paths.append(path_text)
            elif not selected and is_selected:
                self.selected_paths.remove(path_text)

            check = self.checks.get(path_text)
            if check and check.get_active() != selected:
                was_rebuilding = self.rebuilding
                self.rebuilding = True
                check.set_active(selected)
                self.rebuilding = was_rebuilding

            for row, row_path in self.row_paths.items():
                if row_path == path_text:
                    style = row.get_style_context()
                    if selected:
                        style.add_class("capture-selected")
                    else:
                        style.remove_class("capture-selected")
                    break
            self.listbox.invalidate_filter()
            self.update_preview()

        def update_shortcut_label(self) -> None:
            try:
                binding = get_shortcut_binding()
                shortcut = html.escape(format_shortcut(binding))
                self.shortcut_label.set_markup(f"Capture shortcut: <b>{shortcut}</b>")
            except Exception:
                self.shortcut_label.set_text("Capture shortcut: unavailable")

        def change_shortcut(self, *_args) -> None:
            try:
                old_binding = get_shortcut_binding()
                # Disable the global accelerator while this window listens for a new chord.
                import gi

                gi.require_version("Gio", "2.0")
                from gi.repository import Gio

                Gio.Settings.new_with_path(CUSTOM_SCHEMA, CUSTOM_PATH).set_string(
                    "binding", ""
                )
            except Exception as exc:
                self.show_error(f"Could not temporarily disable the capture shortcut: {exc}")
                return

            from gi.repository import Gdk

            dialog = Gtk.Dialog(
                title="Change capture shortcut",
                transient_for=self,
                modal=True,
            )
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            accept_button = dialog.add_button("Use shortcut", Gtk.ResponseType.ACCEPT)
            accept_button.set_sensitive(False)
            dialog.set_default_size(390, 150)

            content = dialog.get_content_area()
            content.set_border_width(18)
            content.set_spacing(10)
            instruction = Gtk.Label(
                label="Press the key combination to capture a full screen.\nInclude a modifier such as Ctrl, Alt, Shift, or Super. Escape cancels."
            )
            instruction.set_line_wrap(True)
            content.pack_start(instruction, False, False, 0)
            captured_label = Gtk.Label(label="Waiting for a shortcut…")
            captured_label.get_style_context().add_class("title-3")
            capture_area = Gtk.EventBox()
            capture_area.set_can_focus(True)
            capture_area.add_events(Gdk.EventMask.KEY_PRESS_MASK)
            capture_area.add(captured_label)
            content.pack_start(capture_area, False, False, 0)

            chosen = {"binding": None}
            modifier_keys = {
                Gdk.KEY_Shift_L, Gdk.KEY_Shift_R,
                Gdk.KEY_Control_L, Gdk.KEY_Control_R,
                Gdk.KEY_Meta_L, Gdk.KEY_Meta_R,
                Gdk.KEY_Alt_L, Gdk.KEY_Alt_R,
                Gdk.KEY_Super_L, Gdk.KEY_Super_R,
                Gdk.KEY_Hyper_L, Gdk.KEY_Hyper_R,
            }
            modifier_keys.update(
                keyval
                for keyval in (
                    getattr(Gdk, f"KEY_{name}", None)
                    for name in (
                        "Shift_Lock", "Caps_Lock", "Num_Lock", "Scroll_Lock",
                        "Mode_switch", "ISO_Lock", "ISO_Level2_Latch",
                        "ISO_Level3_Shift", "ISO_Level3_Latch", "ISO_Level3_Lock",
                        "ISO_Level5_Shift", "ISO_Level5_Latch", "ISO_Level5_Lock",
                        "ISO_Group_Latch", "ISO_Group_Lock", "ISO_Next_Group",
                        "ISO_Prev_Group", "ISO_First_Group", "ISO_Last_Group",
                    )
                )
                if keyval is not None
            )

            def on_key_press(_widget, event) -> bool:
                if event.keyval == Gdk.KEY_Escape:
                    dialog.response(Gtk.ResponseType.CANCEL)
                    return True
                if event.keyval in modifier_keys:
                    return True
                modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
                if not modifiers:
                    chosen["binding"] = None
                    captured_label.set_text("Add a modifier key")
                    accept_button.set_sensitive(False)
                    return True
                keyval = Gdk.keyval_to_lower(event.keyval)
                # GTK rejects some valid system shortcuts (for example Ctrl+Tab
                # and Ctrl+Sys_Req). Accept any named, non-modifier key that GTK
                # can serialize, while keeping Escape reserved for cancel.
                key_name = Gdk.keyval_name(keyval)
                if not key_name or keyval == Gdk.KEY_VoidSymbol:
                    chosen["binding"] = None
                    captured_label.set_text("That key cannot be used")
                    accept_button.set_sensitive(False)
                    return True
                binding = Gtk.accelerator_name(keyval, modifiers)
                if not binding:
                    chosen["binding"] = None
                    captured_label.set_text("That key cannot be used")
                    accept_button.set_sensitive(False)
                    return True
                chosen["binding"] = canonical_shortcut_binding(binding)
                captured_label.set_text(format_shortcut(chosen["binding"]))
                accept_button.set_sensitive(True)
                return True

            capture_area.connect("key-press-event", on_key_press)
            dialog.show_all()
            capture_area.grab_focus()

            committed = False
            error = None
            try:
                response = dialog.run()
                if response == Gtk.ResponseType.ACCEPT and chosen["binding"]:
                    set_shortcut_binding(chosen["binding"])
                    committed = True
            except Exception as exc:
                error = str(exc)
            finally:
                if not committed:
                    try:
                        set_shortcut_binding(old_binding)
                    except Exception as exc:
                        error = error or f"Could not restore the previous shortcut: {exc}"
                dialog.destroy()

            if error:
                self.show_error(f"Could not change the capture shortcut: {error}")
                return
            self.update_shortcut_label()
            if committed:
                self.status_label.set_text("Capture shortcut updated.")

        def clear_selection(self, *_args) -> None:
            self.selected_paths = []
            self.refresh_library(force=True)
            self.status_label.set_text("Selection cleared. Your screenshot files are still saved.")

        def delete_selected(self, *_args) -> None:
            paths = [path_text for path_text in self.selected_paths if Path(path_text).is_file()]
            if not paths:
                self.status_label.set_text("Select one or more screenshots first.")
                return
            self.delete_paths(paths)

        def delete_paths(self, paths: list[str]) -> None:
            names = [capture_display_name(Path(path_text)) for path_text in paths]
            count = len(paths)
            prompt = "Delete this screenshot?" if count == 1 else f"Delete these {count} screenshots?"
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.CANCEL,
                text=prompt,
            )
            dialog.format_secondary_text("\n".join(names))
            dialog.add_button("Delete", Gtk.ResponseType.YES)
            response = dialog.run()
            dialog.destroy()
            if response != Gtk.ResponseType.YES:
                return

            deleted = []
            failures = []
            for path_text in paths:
                try:
                    Path(path_text).unlink()
                    deleted.append(path_text)
                except OSError as exc:
                    failures.append(f"{Path(path_text).name}: {exc}")

            if deleted:
                self.selected_paths = [p for p in self.selected_paths if p not in deleted]
                state = load_state()
                state["pending"] = [p for p in state.get("pending", []) if p not in deleted]
                save_state(state)
                if self.focus_path in deleted:
                    self.focus_path = None
            self.refresh_library(force=True)
            if failures:
                self.show_error("Could not delete some screenshots:\n" + "\n".join(failures))
            elif count == 1:
                self.status_label.set_text("Screenshot deleted. Existing PDFs are unchanged.")
            else:
                self.status_label.set_text(
                    f"{len(deleted)} screenshots deleted. Existing PDFs are unchanged."
                )

        def update_preview(self) -> None:
            count = len(self.selected_paths)
            self.print_button.set_sensitive(count > 0)
            self.print_button.set_label(f"Print selected ({count})")
            self.delete_selected_button.set_sensitive(count > 0)
            if count == 0:
                self.preview_image.set_from_icon_name("image-x-generic", Gtk.IconSize.DIALOG)
                self.layout_label.set_text("Select one to three screenshots to preview the A4 sheet.")
                return
            try:
                page = compose_page(self.selected_paths, dpi=90)
                buffer = io.BytesIO()
                page.save(buffer, format="PNG")
                page.close()
                loader = GdkPixbuf.PixbufLoader.new_with_type("png")
                loader.write(buffer.getvalue())
                loader.close()
                pixbuf = loader.get_pixbuf()
                scaled = pixbuf.scale_simple(
                    PREVIEW_WIDTH, PREVIEW_HEIGHT, GdkPixbuf.InterpType.BILINEAR
                )
                self.preview_image.set_from_pixbuf(scaled)
                placements = {
                    1: "one centered capture",
                    2: "two upright captures stacked on the left",
                    3: "two upright on the left, third rotated on the right",
                }
                self.layout_label.set_text(
                    f"A4 landscape · {count} screenshot(s) · {placements[count]}"
                )
            except Exception as exc:
                self.layout_label.set_text(f"Preview error: {exc}")

        def print_selected(self, *_args) -> None:
            if not self.selected_paths:
                return
            selected = list(self.selected_paths)
            printer_error = None
            try:
                default_printer, printers = query_printers()
            except Exception as exc:
                default_printer, printers = None, []
                printer_error = str(exc)

            dialog = Gtk.Dialog(
                title="Print or save A4 sheet",
                transient_for=self,
                modal=True,
            )
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.add_button("Save PDF…", Gtk.ResponseType.APPLY)
            print_button = dialog.add_button("Print", Gtk.ResponseType.ACCEPT)

            content = dialog.get_content_area()
            content.set_border_width(16)
            content.set_spacing(10)
            description = Gtk.Label(
                label=f"{len(selected)} screenshot(s) are ready on an A4 landscape sheet."
            )
            description.set_xalign(0)
            content.pack_start(description, False, False, 0)
            destination_label = Gtk.Label(label="Printer destination")
            destination_label.set_xalign(0)
            content.pack_start(destination_label, False, False, 0)
            printer_combo = Gtk.ComboBoxText()
            destinations: list[tuple[str, str | None]] = []
            if default_printer:
                destinations.append(("default", None))
                printer_combo.append("default", f"System default ({default_printer})")
            for printer_name in printers:
                if printer_name == default_printer:
                    continue
                destination_id = f"printer:{printer_name}"
                destinations.append((destination_id, printer_name))
                printer_combo.append(destination_id, printer_name)
            if destinations:
                printer_combo.set_active_id(destinations[0][0])
            else:
                printer_combo.set_sensitive(False)
            content.pack_start(printer_combo, False, False, 0)
            info_text = (
                f"Printer list unavailable: {printer_error}. You can still save the PDF."
                if printer_error
                else "No CUPS printers are available. You can still save the PDF."
                if not destinations
                else "Choose the system default or another CUPS printer, or save a PDF."
            )
            info = Gtk.Label(label=info_text)
            info.set_xalign(0)
            info.set_line_wrap(True)
            info.get_style_context().add_class("dim-label")
            content.pack_start(info, False, False, 0)
            print_button.set_sensitive(bool(destinations))
            dialog.show_all()
            response = dialog.run()
            destination_id = printer_combo.get_active_id()
            dialog.destroy()
            if response == Gtk.ResponseType.APPLY:
                self.save_pdf(selected)
                return
            if response != Gtk.ResponseType.ACCEPT:
                return

            try:
                pdf_path = create_sheet_pdf(selected)
                remember_sheet(pdf_path, selected)
                printer = None
                destination_name = f"system default ({default_printer})"
                if destination_id != "default":
                    printer = destination_id.removeprefix("printer:")
                    destination_name = printer
                job = submit_to_printer(pdf_path, printer)
                mark_printed(pdf_path)
                self.status_label.set_text(f"Sent to {destination_name}: {job}")
            except Exception as exc:
                self.show_error(f"Could not create or print the sheet: {exc}")

        def choose_pdf_path(self) -> Path | None:
            SHEETS_DIR.mkdir(parents=True, exist_ok=True)
            dialog = Gtk.FileChooserDialog(
                title="Save A4 sheet as PDF",
                transient_for=self,
                action=Gtk.FileChooserAction.SAVE,
            )
            dialog.add_buttons(
                "Cancel", Gtk.ResponseType.CANCEL,
                "Save PDF", Gtk.ResponseType.ACCEPT,
            )
            dialog.set_do_overwrite_confirmation(True)
            dialog.set_current_folder(str(SHEETS_DIR))
            dialog.set_current_name(f"notesheet-{timestamp()}.pdf")
            pdf_filter = Gtk.FileFilter()
            pdf_filter.set_name("PDF files")
            pdf_filter.add_mime_type("application/pdf")
            pdf_filter.add_pattern("*.pdf")
            dialog.add_filter(pdf_filter)
            response = dialog.run()
            filename = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None
            dialog.destroy()
            if not filename:
                return None
            output = Path(filename)
            if output.suffix.lower() != ".pdf":
                output = Path(f"{output}.pdf")
            return output

        def save_pdf(self, selected: list[str]) -> None:
            output_path = self.choose_pdf_path()
            if output_path is None:
                return
            try:
                pdf_path = create_sheet_pdf(selected, output_path)
                remember_sheet(pdf_path, selected)
                self.status_label.set_text(f"Saved PDF: {pdf_path}")
            except Exception as exc:
                self.show_error(f"Could not save the PDF: {exc}")

        def show_error(self, message: str) -> None:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text="Notesheet",
            )
            dialog.format_secondary_text(message)
            dialog.run()
            dialog.destroy()

    try:
        Gtk.init([])
        NotesheetWindow()
        Gtk.main()
        return 0
    except Exception as exc:
        print(f"Could not open Notesheet: {exc}", file=sys.stderr)
        return 1


def status() -> int:
    state = load_state()
    print(f"Capture folder: {ROOT}")
    captures = list(CAPTURES_DIR.glob("screen-*.png")) if CAPTURES_DIR.exists() else []
    print(f"Saved screenshots: {len(captures)}")
    sheet = latest_sheet(state)
    print(f"Latest sheet: {sheet if sheet else 'none yet'}")
    return 0


def setup_shortcut() -> int:
    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio

        media_keys = Gio.Settings.new(MEDIA_KEYS_SCHEMA)
        shell_keys = Gio.Settings.new(SHELL_KEYS_SCHEMA)
        state = load_state()
        if "shortcut_backup" not in state:
            state["shortcut_backup"] = shell_keys.get_strv("screenshot-window")

        # Free Alt+Print from GNOME's window-screenshot action, then register
        # this app's shortcut without disturbing any other custom shortcuts.
        shell_keys.set_strv(
            "screenshot-window",
            [key for key in state["shortcut_backup"] if key != SHORTCUT],
        )
        custom = Gio.Settings.new_with_path(CUSTOM_SCHEMA, CUSTOM_PATH)
        custom.set_string("name", "Notesheet full-screen capture")
        custom.set_string(
            "command",
            shlex.join([sys.executable, str(Path(__file__).resolve()), "capture"]),
        )
        custom.set_string("binding", SHORTCUT)
        paths = media_keys.get_strv("custom-keybindings")
        if CUSTOM_PATH not in paths:
            media_keys.set_strv("custom-keybindings", paths + [CUSTOM_PATH])
        save_state(state)
        print("Alt+Print is now bound to Notesheet full-screen capture.")
        return 0
    except Exception as exc:
        print(f"Could not configure the GNOME shortcut: {exc}", file=sys.stderr)
        return 1


def remove_shortcut() -> int:
    try:
        import gi

        gi.require_version("Gio", "2.0")
        from gi.repository import Gio

        media_keys = Gio.Settings.new(MEDIA_KEYS_SCHEMA)
        shell_keys = Gio.Settings.new(SHELL_KEYS_SCHEMA)
        paths = media_keys.get_strv("custom-keybindings")
        media_keys.set_strv("custom-keybindings", [p for p in paths if p != CUSTOM_PATH])
        Gio.Settings.new_with_path(CUSTOM_SCHEMA, CUSTOM_PATH).reset("name")
        Gio.Settings.new_with_path(CUSTOM_SCHEMA, CUSTOM_PATH).reset("command")
        Gio.Settings.new_with_path(CUSTOM_SCHEMA, CUSTOM_PATH).reset("binding")
        state = load_state()
        restore = state.pop("shortcut_backup", [SHORTCUT])
        shell_keys.set_strv("screenshot-window", restore)
        save_state(state)
        print("Notesheet shortcut removed; GNOME's previous window-screenshot key was restored.")
        return 0
    except Exception as exc:
        print(f"Could not remove the GNOME shortcut: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage full-screen captures and print selected shots on A4."
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="capture",
        choices=("capture", "ui", "print-latest", "open-latest", "status", "setup-shortcut", "remove-shortcut"),
        help="action to perform (default: capture)",
    )
    action = parser.parse_args().action
    return {
        "capture": capture,
        "ui": run_ui,
        "print-latest": print_latest,
        "open-latest": open_latest,
        "status": status,
        "setup-shortcut": setup_shortcut,
        "remove-shortcut": remove_shortcut,
    }[action]()


if __name__ == "__main__":
    sys.exit(main())
