"""Independent safety check of a finished .cnc file.

Deliberately imports nothing from artisancam: it re-reads the output text and asserts the
rules that protect the bit, the stock and the machine. Returns a list of problems (empty =
the file passes). Run as: python tests/gcode_check.py file.cnc
"""

from __future__ import annotations

import re
import sys

ALLOWED = {"G0", "G1", "G4", "G21", "G90", "M3", "M5"}
_WORD = re.compile(r"([A-Z])(-?\d+(?:\.\d+)?)")
EPS = 1e-6


def check(data: bytes, *, stock_width: float, stock_length: float, depth: float, retract_z: float, edge_margin: float = 0.0) -> list[str]:
    problems: list[str] = []
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return ["file is not pure ASCII"]
    if "\n" in text.replace("\r\n", ""):
        problems.append("line endings are not CRLF")
    if not text.endswith("\r\n"):
        problems.append("file does not end with a line break")

    pos = {"X": 0.0, "Y": 0.0, "Z": retract_z}  # unknown start: assume the machine starts safely high
    units = absolute = spindle_on = False
    spindle_was_on_at_last_cut = True
    cut_count = 0
    last_code = None
    for number, raw in enumerate(text.split("\r\n"), 1):
        line = raw.split(";")[0].strip()
        if not line:
            continue
        words = _WORD.findall(line)
        code = words[0][0] + str(int(float(words[0][1])))
        last_code = code
        where = f"line {number} ({raw.strip()})"
        if code not in ALLOWED:
            problems.append(f"{where}: command {code} is not allowed (no arcs, no tool change, ...)")
            continue
        args = {letter: float(value) for letter, value in words[1:]}
        if code == "G21":
            units = True
        elif code == "G90":
            absolute = True
        elif code == "M3":
            if not 50 < args.get("P", 0) <= 100:
                problems.append(f"{where}: spindle percent must be above 50 and at most 100")
            spindle_on = True
        elif code == "M5":
            spindle_on = False
        elif code in ("G0", "G1"):
            if not (units and absolute):
                problems.append(f"{where}: motion before G21/G90")
            new = {k: args.get(k, pos[k]) for k in "XYZ"}
            xy_changes = abs(new["X"] - pos["X"]) > EPS or abs(new["Y"] - pos["Y"]) > EPS
            if code == "G1":
                if "F" not in args:
                    problems.append(f"{where}: G1 without a feed rate")
                if not spindle_on:
                    problems.append(f"{where}: cutting move with the spindle off")
                if xy_changes and abs(new["Z"] + depth) > EPS:
                    problems.append(f"{where}: XY move not at the engraving depth Z-{depth:g}")
                if xy_changes:
                    cut_count += 1
            elif xy_changes and (pos["Z"] < retract_z - EPS or new["Z"] < retract_z - EPS):
                problems.append(f"{where}: rapid XY move below retract height Z{retract_z:g}")
            if new["Z"] < -depth - EPS:
                problems.append(f"{where}: Z{new['Z']:g} is deeper than the allowed -{depth:g}")
            if not (edge_margin - EPS <= new["X"] <= stock_width - edge_margin + EPS and -(stock_length - edge_margin) - EPS <= new["Y"] <= -edge_margin + EPS):
                # The final G0 X0 Y0 park move and the start move are the only moves allowed on the origin.
                if not (code == "G0" and new["X"] == 0 and new["Y"] == 0 and new["Z"] >= retract_z):
                    problems.append(f"{where}: XY ({new['X']:g}, {new['Y']:g}) leaves the stock")
            pos = new
    if cut_count == 0:
        problems.append("the program contains no cutting moves")
    if last_code != "M5":
        problems.append("program does not end with M5")
    if pos["Z"] < retract_z - EPS:
        problems.append("tool does not end above retract height")
    return problems


if __name__ == "__main__":
    # Standalone use against the project's config.toml values.
    import tomllib
    from pathlib import Path

    cfg = tomllib.loads((Path(__file__).resolve().parents[1] / "config.toml").read_text())
    issues = check(
        Path(sys.argv[1]).read_bytes(),
        stock_width=cfg["stock"]["width"], stock_length=cfg["stock"]["length"],
        depth=cfg["engraving"]["depth"], retract_z=cfg["heights"]["retract"],
    )
    print("\n".join(issues) or "OK")
    raise SystemExit(1 if issues else 0)
