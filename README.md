# Notesheet

Notesheet captures full-screen images, lets you choose and order up to three, previews their layout on landscape A4, and prints through CUPS or saves a PDF.

## Screenshots

The preview shows three sample captures arranged on an A4 sheet. The print dialog lets you choose a CUPS printer or save the sheet as a PDF.

![Notesheet with three captures in the A4 preview](screenshots/notesheet-preview.png)

![Notesheet print and PDF options](screenshots/notesheet-print-options.png)

## Install and run

On Ubuntu, install the runtime dependencies:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 python3-pil cups-client xdg-user-dirs
```

Clone the repository, then launch the interface:

```bash
git clone https://github.com/nehuencabibbo/notesheet.git
cd notesheet
python3 notesheet.py ui
```

To assign the default **Alt+Print** capture shortcut, run:

```bash
python3 notesheet.py setup-shortcut
```

The current shortcut appears in the toolbar. Use **Change…** to choose a different combination. Press Escape to cancel. Run `python3 notesheet.py remove-shortcut` to restore GNOME’s previous window-screenshot shortcut.

## Use the app

- Captures are saved under `~/Pictures/NoteCaptures/Captures/`.
- Select one to three screenshots. Their order determines their positions on the page. Use **Move up** and **Move down** to reorder them.
- With three selected, **Move left** and **Move right** swap a screenshot between the left column and the rotated slot on the right.
- The A4 landscape preview updates as the selection changes. **Print selected** offers the system default printer, other CUPS queues, and **Save PDF…**. Created sheets are also kept under `~/Pictures/NoteCaptures/Sheets/`.
- Screenshots remain in the library after printing. **Delete focused** removes the focused screenshot after confirmation.

The layouts are:

1. One screenshot centered on the page.
2. Two upright screenshots stacked on the left.
3. Two upright screenshots on the left and the third rotated on the right.

## Terminal commands

```bash
python3 notesheet.py status
python3 notesheet.py open-latest
python3 notesheet.py print-latest
python3 notesheet.py remove-shortcut
```

`status` lists the capture count and latest sheet. `open-latest` opens the latest PDF. `print-latest` sends it to the system default CUPS printer. Use `lpstat -e` and `lpstat -d` to list installed printers and check the default.

## Page layout

The page is A4 landscape at 300 dpi, with 5 mm margins and 2 mm gaps. Each screenshot keeps its aspect ratio and targets up to 180 mm wide. A 16:9 desktop image fits at about 176 × 99 mm in the three-capture layout.
