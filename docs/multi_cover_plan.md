# Design: engraving several FLF covers in one run (3 or 6)

Status: **plan only, nothing implemented.** Decisions taken:

- every cover (slot) gets its **own** top and bottom text; an empty slot is skipped;
- **one** `.cnc` file engraves all slots one after another;
- **one** zero point: X0 Y0 on the top-left corner of slot 1, Z0 on the cover top (as today).

## The key idea: lay out per cover, then shift

Today everything in `layout.py` works in the frame of **one** cover: the text is centred on
`stock_width`, the bottom line hangs from `stock_length`, the edge check uses both. That stays
exactly as it is. A multi-cover job is just:

```
for each slot with text:
    strokes = layout_lines(top, bottom, font, settings)    # unchanged, one cover's frame
    strokes = shifted by the slot's offset (dx, dy)         # new, a few lines
all strokes -> build_toolpath -> generate_gcode             # unchanged, one file
```

So the font, layout, toolpath and G-code dialect need no change. A 1 x 1 fixture must give
**byte-identical** G-code to today; that is the main safety test.

## Slot geometry (config)

The fixture plate defines where the covers sit. A regular grid is enough:

```toml
[fixture]
columns = 3      # covers side by side along X
rows    = 2      # covers above each other along Y
pitch_x = 45.0   # X distance between the top-left corners of neighbouring slots (mm)
pitch_y = 70.0   # Y distance (downward) between the top-left corners of slots (mm)
```

- Slot numbering is row by row from the reference slot:
  ```
  slot 1 (0,0)      slot 2 (45,0)      slot 3 (90,0)        <- X0 Y0 on slot 1's top-left corner
  slot 4 (0,70)     slot 5 (45,70)     slot 6 (90,70)
  ```
  Offset of slot *i* (0-based): `dx = (i % columns) * pitch_x`, `dy = (i // columns) * pitch_y`
  in the stock frame (y down), which becomes machine Y = -y as today.
- `columns = rows = 1` is today's behaviour.
- Validation (in `config.py`, same style as now): columns and rows are whole numbers 1..10;
  with more than one column `pitch_x >= stock width`, with more than one row
  `pitch_y >= stock length` (covers must not overlap).
- The pitch values are **not** chosen in software: they are copied from the fixture plate design.
  The example numbers above are placeholders (37.25 + about 8 mm gap, 62.5 + about 8 mm gap).

## Changes per file

| File | Change |
|---|---|
| `config.toml`, `config.defaults.toml` | New `[fixture]` section (default 1 x 1, so nothing changes until you set it). |
| `config.py` | Four `FieldSpec` rows for `[fixture]` (shown on a new "Fixture" tab of the Settings dialog), the overlap checks, and a `slot_offsets(settings) -> list[(dx, dy)]` helper. |
| `fixture.py` (new, small, no Qt) | `shift(strokes, dx, dy)` and the loop above. Keeps "where is slot 4" out of layout and G-code. |
| `__init__.py` | `create_program_for_slots(slots, settings)` where `slots` is a list of `(top, bottom)`, one per slot. Blank slots are skipped; all blank raises "Nothing to engrave". Errors are prefixed with the slot, e.g. `Slot 4: Bottom text: too wide …`. The existing `create_program(top, settings, bottom=…)` stays as the 1-slot shortcut, so current callers and tests keep working. |
| `gcode.py` | Only the header comments: one `;Slot n: top / bottom` line per engraved slot, and the fixture size instead of a single stock size. No change to moves. Between slots the tool travels at retract height (5 mm), the same as between letters. |
| `ui/window.py` | The two text fields become a **table**: one row per slot, columns *Slot*, *Top text*, *Bottom text*. A "Copy row 1 to all" button covers the common "same label everywhere" case. Editing any cell marks the program stale, as today. The save file name is built from the filled slots. |
| `ui/preview_view.py` | Draw one cover outline per slot, with its slot number; draw the chosen cut-out version in every slot; slots without text drawn dashed/grey; the reference-point symbol only on slot 1's corner; the view fits the whole fixture. |
| `ui/settings_dialog.py` | Nothing by hand: the new `FieldSpec` rows appear automatically. When rows/columns change, the window rebuilds the table and keeps the texts it can. |
| `tests/gcode_check.py` | The XY bounds become the whole fixture: X from 0 to `(columns-1)*pitch_x + width`, Y from 0 down to `-((rows-1)*pitch_y + length)`. Its command-line mode reads `[fixture]` too. |
| `docs/fixture_fusion360_brief.md` | Needs a multi-slot variant: N openings on the same pitch, one shared reference corner. |

## Order of work (each step testable on its own)

1. `[fixture]` in config + `slot_offsets`; default 1 x 1. Tests: offsets for 1x1, 3x1, 3x2; overlap rejected.
2. `fixture.py` + `create_program_for_slots`. Tests: **1 x 1 output byte-identical to today**;
   slot 2's moves equal slot 1's moves shifted by `pitch_x`; blank slots skipped; error names the slot.
3. Checker bounds. Tests: 6-slot programs pass; a move beyond the fixture fails.
4. Preview: slot outlines, cut-outs per slot, one reference symbol. Tests: N outlines, 1 marker.
5. Window table + "Copy row 1 to all". Tests: row count = slots, edits make the program stale,
   only filled rows are engraved.
6. Settings dialog: verify the Fixture tab appears and the table follows a rows/columns change.
7. Update the fixture brief for a multi-slot plate.

## Things to know before running it

- **Axis directions matter more.** With one cover a wrong Y direction mirrors the text on the
  cover; with six it sends slot 4-6 off the fixture. Confirm the axes and do an **air test**
  with all slots before cutting.
- **The fixture must not stick up anywhere.** The tool crosses the whole plate at 5 mm above
  the cover top between slots.
- **Pitch accuracy is the fixture's accuracy.** A printed plate can be off by a few tenths;
  measure a printed plate and put the measured pitch in the config.
- **Re-doing one cover is easy:** fill in only that slot's row and leave the others blank.
- **Run time** grows with the number of covers; about six times one cover for six slots.
- **Cut-out version** is the same for all slots in this design. Mixing 1xD and 2xD in one
  run would need a version column in the table (a later step, display only).
