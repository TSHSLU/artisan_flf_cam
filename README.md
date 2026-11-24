# ArtisanCAM

Minimal prototype: type a text, get G-code for the Snapmaker Artisan. Single-line (stroke)
engraving with a 60° V-bit. Nothing else.

## Run

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m artisancam
```

Type a text, click **Create program**, review the G-code, **Save as…** to write a `.cnc` file.

## Configure

Everything machine- or job-specific is in [config.toml](config.toml): stock size, engraving
depth, text height and placement, heights, feeds, spindle percent. Origin is the top-left
corner of the stock, Z = 0 is the top of the stock. Bad values fail with a message naming the key.

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
  layout.py                 strokes -> millimetres on the stock, fit checks
  toolpath.py               strokes -> ordered cuts
  gcode.py                  cuts -> G-code (machine dialect and origin live here)
  ui/window.py              the single window
tests/                      pytest + independent G-code checker
```

Not yet run on a real machine. Review the first program and do a dry run before cutting.
