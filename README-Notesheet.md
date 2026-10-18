# Notesheet

Notesheet captures full-screen images, lets you choose and order them, previews the A4 page, and prints through CUPS.

## Open the interface

Search for **Notesheet** in the Ubuntu app launcher, or run:

```bash
python3 /home/nehuen/Documents/Codex/2026-10-17/hey/outputs/notesheet.py ui
```

The left side lists every screenshot in `~/Pictures/NoteCaptures/Captures/`. Use the checkboxes to select up to three images. The selected order is their slot order. Click a selected row and use **Move up** or **Move down** to reorder it. **Move left** and **Move right** are grayed out until three images are selected; hover over them to see why. With three selected, they swap a left-column image with the rotated right-hand slot. To replace an image, uncheck it and check another. **Delete focused** removes the focused screenshot after confirmation; PDFs already created are kept.

The right side updates an A4 landscape preview as the selection changes:

- One screenshot is centered on the page.
- Two screenshots are upright, stacked on the left.
- Three screenshots use the two-left, one-rotated-right layout.

Click **Print selected** to choose a destination. **System default** uses the printer configured as the CUPS default; other available queues are listed by name. **Save PDF…** opens a file chooser so the sheet can be saved anywhere without printing. Printed PDFs are also kept in `~/Pictures/NoteCaptures/Sheets/`. You can print one or two shots; the unused page area stays blank. Screenshots remain in the library after printing.

## Capture

- Press the configured capture shortcut anywhere (Alt+Print by default) to save a full-screen PNG.
- The current capture shortcut is shown in the interface toolbar. Click **Change…** to record a different key combination; include a modifier such as Ctrl, Alt, Shift, or Super. Press Escape to cancel.

The interface refreshes the library when new screenshots appear. Use the shortcut while Notesheet is not in the foreground so the captured screen does not include the Notesheet window. The standard **Print** and **Shift+Print** shortcuts are unchanged.

## Terminal commands

```bash
python3 /home/nehuen/Documents/Codex/2026-10-17/hey/outputs/notesheet.py status
python3 /home/nehuen/Documents/Codex/2026-10-17/hey/outputs/notesheet.py open-latest
python3 /home/nehuen/Documents/Codex/2026-10-17/hey/outputs/notesheet.py print-latest
```

`status` lists the screenshot count and latest sheet. `open-latest` opens the latest PDF. `print-latest` sends it to the system default CUPS printer. To list available printers and inspect the default, use `lpstat -e` and `lpstat -d`. To restore GNOME's previous Alt+Print window-screenshot shortcut, run:

```bash
python3 /home/nehuen/Documents/Codex/2026-10-17/hey/outputs/notesheet.py remove-shortcut
```

## Layout details

The page is A4 landscape at 300 dpi, with 5 mm margins and 2 mm gaps. Each screenshot keeps its aspect ratio and targets up to 180 mm wide. A 16:9 desktop fits at about 176 × 99 mm when three are selected. The capture backend uses GNOME GDK on the current X11 desktop.
