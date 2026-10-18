# Notesheet

Notesheet captures full-screen images, lets you choose and order them, previews the A4 page, and prints the selection on the Epson L395.

## Open the interface

Search for **Notesheet** in the Ubuntu app launcher, or run:

```bash
python3 /home/nehuen/Documents/Codex/2026-10-17/hey/outputs/notesheet.py ui
```

The left side lists every screenshot in `~/Pictures/NoteCaptures/Captures/`. Use the checkboxes to select up to three images. The selected order is their slot order. Click a selected row and use **Move up** or **Move down** to reorder it. With three selected, **Move right** swaps a left-column image into the rotated right-hand slot; **Move left** swaps that image back into the lower-left slot. To replace an image, uncheck it and check another. **Delete focused** removes the focused screenshot after confirmation; PDFs already created are kept.

The right side updates an A4 landscape preview as the selection changes:

- One screenshot is centered on the page.
- Two screenshots are upright, stacked on the left.
- Three screenshots use the two-left, one-rotated-right layout.

Click **Print selected** to save the sheet PDF in `~/Pictures/NoteCaptures/Sheets/` and send it to the L395. You can print one or two shots; the unused page area stays blank. Screenshots remain in the library after printing.

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

`status` lists the screenshot count and latest sheet. `open-latest` opens the latest PDF. `print-latest` sends it to the L395. To restore GNOME's previous Alt+Print window-screenshot shortcut, run:

```bash
python3 /home/nehuen/Documents/Codex/2026-10-17/hey/outputs/notesheet.py remove-shortcut
```

## Layout details

The page is A4 landscape at 300 dpi, with 5 mm margins and 2 mm gaps. Each screenshot keeps its aspect ratio and targets up to 180 mm wide. A 16:9 desktop fits at about 176 × 99 mm when three are selected. The capture backend uses GNOME GDK on the current X11 desktop.
