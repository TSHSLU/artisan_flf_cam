# ArtisanCAM

Minimal prototype: type a top text and/or a bottom text, get G-code for the Snapmaker Artisan.
Single-line (stroke) engraving with a 60° V-bit. Nothing else: the D-cut and screw holes are cut
by a separate program, never by this one.

## Run

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m artisancam
```

or run start.bat

Fill in the top text, the bottom text, or both (a blank line is skipped), click **Create program**,
review the G-code, **Save as…** to write a `.cnc` file.

## Configure

Everything machine- or job-specific is in [config.toml](config.toml): stock size, engraving
depth, height and placement of the top and bottom line, heights, feeds, spindle percent, and
the cut-outs. Origin is the top-left
corner of the stock, Z = 0 is the top of the stock. Bad values fail with a message naming the key.

**Cut-outs** (the D hole and screw holes of a cover version) are `[[cutout]]` blocks in
`config.toml`: circles, rectangles or D shapes, measured from the top-left corner (x right, y down).
They are cut by a separate program; here they are only drawn in red on the preview, and a dropdown
in the window chooses which version (for example `1xD`) is shown. They never block the text or
change the G-code. Values marked `ASSUMED` in the file are guesses; 2xD was measured on a real cover except
for its x position.

## Several covers in one run

The `[fixture]` section of `config.toml` (also on the *Fixture* tab of the Settings dialog) sets
how many covers the fixture holds: `columns` x `rows` slots, `pitch_x` / `pitch_y` apart (corner
to corner, from the fixture plate). Slot 1 is the top-left slot, numbered row by row; X0 Y0 is
set once, on slot 1's top-left corner.

The window shows one table row per slot (top and bottom text). Empty slots are skipped and drawn
dashed in the preview; **Copy slot 1 to all** fills every slot with the same text. One `.cnc`
file engraves all filled slots. With `columns = rows = 1` it is the single-cover program as before
(byte-identical; a golden-file test checks this).

## Settings dialog

**Settings…** in the main window edits every number of `config.toml` (not the cut-outs) on three
tabs: *Cover and text*, *Fixture* and *Machine*. **Save** checks the values with the same rules as at
startup, then writes them back into `config.toml`. Only the changed numbers are replaced:
comments, layout and the cut-outs stay as they are. The previous file is kept as
`config.toml.bak`. The window uses the new values at once; a program shown before is faded
and must be created again.

**Restore Defaults** fills in the known-good values from
[config.defaults.toml](config.defaults.toml) (a snapshot of the settings that ran successfully
on the machine). Nothing is written until you click Save. The app never writes the defaults file.

## Test

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python tests\gcode_check.py path\to\file.cnc
```

`tests/gcode_check.py` is an independent checker: it reads only the finished `.cnc` text.
If `reference/HDMI_OUT_v4.cnc` (the program that ran on the machine) is present, extra tests
compare the output against it. The `reference/` folder content is gitignored.

## Layout

```
config.toml                 all job/machine values (edited by hand or by the Settings dialog)
config.defaults.toml        known-good values for "Restore Defaults" (read only)
src/artisancam/
  config.py                 load + validate config.toml
  font.py                   bundled stroke font -> strokes (arcs flattened)
  layout.py                 strokes -> millimetres, top/bottom line, edge-margin check
  fixture.py                slot positions; moving a cover into its slot
  toolpath.py               strokes -> ordered cuts
  gcode.py                  cuts -> G-code (machine dialect and origin live here)
  preview.py                G-code text -> moves, for the preview
  ui/window.py              the main window
  ui/preview_view.py        the 2D preview
  ui/settings_dialog.py     the Settings dialog
tests/                      pytest + independent G-code checker
```

Ran on the machine with the default settings. Still review each program in the preview, and do
an air test after changing machine values.
