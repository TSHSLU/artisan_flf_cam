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

or run startup.bat

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
change the G-code. Versions 1xD and 2xD currently use assumed numbers (see the comments in the file) until
they are checked against the Fusion cut-out programs.

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
config.toml                 all job/machine values
src/artisancam/
  config.py                 load + validate config.toml
  font.py                   bundled stroke font -> strokes (arcs flattened)
  layout.py                 strokes -> millimetres, top/bottom line, edge-margin check
  toolpath.py               strokes -> ordered cuts
  gcode.py                  cuts -> G-code (machine dialect and origin live here)
  ui/window.py              the single window
tests/                      pytest + independent G-code checker
```

Not yet run on a real machine. Review the first program and do a dry run before cutting.
