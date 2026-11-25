"""Load and validate config.toml into one frozen Settings object.

Every value is required, unknown keys are rejected (typo guard), and nonsensical values
fail with a message that names the key. A bad config must never turn into a bad G-code file.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.toml"
# Known-good values ("factory defaults") that the Settings dialog can restore. Never written by the app.
DEFAULTS_PATH = Path(__file__).resolve().parents[2] / "config.defaults.toml"

# Sanity limit for the V-bit engraving depth: guards against a 0.2 -> 2 typo.
MAX_DEPTH = 1.0
# Most covers side by side or above each other on one fixture.
MAX_SLOTS_PER_AXIS = 10


class ConfigError(ValueError):
    """The configuration file is missing, incomplete or has an invalid value."""


@dataclass(frozen=True)
class Cutout:
    """A hole or opening in the cover that is cut by a separate program.

    Used only to DRAW the hole in red on the preview; it never blocks or changes the engraving.
    Coordinates are millimetres in the stock frame: origin top-left corner, x right, y downward.
      rect:   (x, y) is the top-left corner, with width and height.
      circle: (x, y) is the centre, with diameter.
      d:      a circle with one flat side. (x, y) is the centre, `flat` is the distance from the
              centre to the flat, `flat_side` says where the flat is: left, right, top or bottom.
              Without `flat` it is drawn as a plain circle.
    A cut-out belongs to a `version` (for example "1xD"); the window shows one version at a time.
    """

    name: str
    version: str
    shape: str  # "rect", "circle" or "d"
    x: float
    y: float
    width: float = 0.0
    height: float = 0.0
    diameter: float = 0.0
    flat: float = 0.0
    flat_side: str = ""


@dataclass(frozen=True)
class Settings:
    stock_width: float
    stock_length: float
    letter_gap: float
    space_width: float
    edge_margin: float
    top_height: float
    top_margin: float
    bottom_height: float
    bottom_margin: float
    depth: float
    clearance_z: float
    retract_z: float
    feed_z: float
    cutting_feed: float
    plunge_feed: float
    retract_feed: float
    spindle_percent: float
    spindle_warmup_s: float
    fixture_columns: float
    fixture_rows: float
    pitch_x: float
    pitch_y: float
    cutouts: tuple[Cutout, ...] = ()

    @property
    def columns(self) -> int:
        return int(self.fixture_columns)

    @property
    def rows(self) -> int:
        return int(self.fixture_rows)

    @property
    def slot_count(self) -> int:
        """How many covers the fixture holds (1 = the single-cover setup)."""
        return self.columns * self.rows

    @property
    def cutout_versions(self) -> tuple[str, ...]:
        """The version names used by the cut-outs, in order of first appearance."""
        return tuple(dict.fromkeys(c.version for c in self.cutouts))


@dataclass(frozen=True)
class FieldSpec:
    """One number in config.toml: where it lives, which Settings field it fills, and how the
    Settings dialog shows it (label, unit, tab, decimals, upper limit of the input box)."""

    section: str
    key: str
    field: str
    label: str
    unit: str
    tab: str  # "layout", "fixture" or "machine"
    decimals: int
    maximum: float
    may_be_zero: bool = False


# This table is the whole file format (apart from [[cutout]]) and also the content of the
# Settings dialog, in this order. A new setting needs one line here and one field in Settings.
FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("stock", "width", "stock_width", "Cover width", "mm", "layout", 2, 1000),
    FieldSpec("stock", "length", "stock_length", "Cover length", "mm", "layout", 2, 1000),
    FieldSpec("text_top", "height", "top_height", "Top text: letter height", "mm", "layout", 2, 100),
    FieldSpec("text_top", "margin", "top_margin", "Top text: distance from the top edge", "mm", "layout", 2, 1000, True),
    FieldSpec("text_bottom", "height", "bottom_height", "Bottom text: letter height", "mm", "layout", 2, 100),
    FieldSpec("text_bottom", "margin", "bottom_margin", "Bottom text: baseline above the bottom edge", "mm", "layout", 2, 1000, True),
    FieldSpec("text", "letter_gap", "letter_gap", "Gap between letters", "font units", "layout", 0, 5000),
    FieldSpec("text", "space_width", "space_width", "Extra width of a space", "font units", "layout", 0, 5000),
    FieldSpec("text", "edge_margin", "edge_margin", "Minimum distance to the edges", "mm", "layout", 2, 100, True),
    FieldSpec("fixture", "columns", "fixture_columns", "Covers side by side (columns)", "", "fixture", 0, MAX_SLOTS_PER_AXIS),
    FieldSpec("fixture", "rows", "fixture_rows", "Covers above each other (rows)", "", "fixture", 0, MAX_SLOTS_PER_AXIS),
    FieldSpec("fixture", "pitch_x", "pitch_x", "Slot pitch along X (corner to corner)", "mm", "fixture", 2, 1000),
    FieldSpec("fixture", "pitch_y", "pitch_y", "Slot pitch along Y (corner to corner)", "mm", "fixture", 2, 1000),
    FieldSpec("engraving", "depth", "depth", "Engraving depth", "mm", "machine", 3, MAX_DEPTH),
    FieldSpec("heights", "clearance", "clearance_z", "Clearance height (start and end)", "mm", "machine", 2, 100),
    FieldSpec("heights", "retract", "retract_z", "Retract height (between strokes)", "mm", "machine", 2, 100),
    FieldSpec("heights", "feed", "feed_z", "Feed height (plunge starts here)", "mm", "machine", 2, 100),
    FieldSpec("feeds", "cutting", "cutting_feed", "Cutting feed", "mm/min", "machine", 1, 20000),
    FieldSpec("feeds", "plunge", "plunge_feed", "Plunge feed", "mm/min", "machine", 1, 20000),
    FieldSpec("feeds", "retract", "retract_feed", "Retract feed", "mm/min", "machine", 1, 20000),
    FieldSpec("spindle", "percent", "spindle_percent", "Spindle power", "%", "machine", 0, 100),
    FieldSpec("spindle", "warmup_s", "spindle_warmup_s", "Spindle warm-up", "s", "machine", 1, 60, True),
)

# (section, key) -> Settings field, and the fields that may be zero (every other one must be > 0).
_FIELDS = {(f.section, f.key): f.field for f in FIELDS}
_MAY_BE_ZERO = {f.field for f in FIELDS if f.may_be_zero}

# Keys of one [[cutout]] entry: required numbers per shape, and optional ones.
_CUTOUT_KEYS = {"rect": ("x", "y", "width", "height"), "circle": ("x", "y", "diameter"), "d": ("x", "y", "diameter")}
_CUTOUT_OPTIONAL = {"d": ("flat", "flat_side")}
_CUTOUT_POSITIVE = {"width", "height", "diameter", "flat"}
_FLAT_SIDES = ("left", "right", "top", "bottom")


def load_settings(path: Path | str | None = None) -> Settings:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file {path} is not valid TOML: {exc}") from None
    return parse_settings(raw)


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label} must be a number, got {value!r}")
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise ConfigError(f"{label} must be a finite number")
    return value


def _parse_cutout(entry: object, index: int) -> Cutout:
    where = f"[[cutout]] entry {index}"
    if not isinstance(entry, dict):
        raise ConfigError(f"{where} must be a table")
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{where} needs a name, e.g. name = \"D hole\"")
    where = f"[[cutout]] '{name}'"
    version = entry.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ConfigError(f"{where} needs a version, e.g. version = \"1xD\"")
    shape = entry.get("shape")
    if shape not in _CUTOUT_KEYS:
        raise ConfigError(f"{where}: shape must be \"rect\", \"circle\" or \"d\", got {shape!r}")
    optional = _CUTOUT_OPTIONAL.get(shape, ())
    allowed = {"name", "version", "shape", *_CUTOUT_KEYS[shape], *optional}
    for key in entry:
        if key not in allowed:
            raise ConfigError(f"{where}: unknown key {key} for a {shape}")
    numbers: dict[str, float] = {}  # x, y, width, height, diameter: always numbers
    for key in _CUTOUT_KEYS[shape]:
        if key not in entry:
            raise ConfigError(f"{where}: missing key {key}")
        value = _number(entry[key], f"{where} {key}")
        if key in _CUTOUT_POSITIVE and value <= 0:
            raise ConfigError(f"{where} {key} must be > 0, got {value:g}")
        numbers[key] = value
    flat, flat_side = 0.0, ""  # the flat side of a D is optional
    if shape == "d" and ("flat" in entry or "flat_side" in entry):
        if "flat" not in entry or "flat_side" not in entry:
            raise ConfigError(f"{where}: flat and flat_side belong together; give both or neither")
        flat = _number(entry["flat"], f"{where} flat")
        if not 0 < flat < numbers["diameter"] / 2:
            raise ConfigError(f"{where}: flat must be between 0 and the radius ({numbers['diameter'] / 2:g} mm), got {flat:g}")
        if entry["flat_side"] not in _FLAT_SIDES:
            raise ConfigError(f"{where}: flat_side must be one of {', '.join(_FLAT_SIDES)}, got {entry['flat_side']!r}")
        flat_side = str(entry["flat_side"])
    return Cutout(name=name.strip(), version=version.strip(), shape=shape, flat=flat, flat_side=flat_side, **numbers)


def parse_settings(raw: dict) -> Settings:
    for section, table in raw.items():
        if section == "cutout":
            if not isinstance(table, list):
                raise ConfigError("Cut-outs are written as [[cutout]] entries (double brackets).")
            continue
        if not isinstance(table, dict):
            raise ConfigError(f"Unexpected top-level key '{section}'; values belong in a [section].")
        for key in table:
            if (section, key) not in _FIELDS:
                raise ConfigError(f"Unknown config key [{section}] {key}")

    values: dict[str, float] = {}
    for (section, key), field in _FIELDS.items():
        try:
            value = raw[section][key]
        except KeyError:
            raise ConfigError(f"Missing config key [{section}] {key}") from None
        value = _number(value, f"[{section}] {key}")
        if value < 0 or (value == 0 and field not in _MAY_BE_ZERO):
            raise ConfigError(f"[{section}] {key} must be {'>= 0' if field in _MAY_BE_ZERO else '> 0'}, got {value:g}")
        values[field] = value

    cutouts = tuple(_parse_cutout(entry, i) for i, entry in enumerate(raw.get("cutout", []), 1))
    s = Settings(**values, cutouts=cutouts)
    if s.depth > MAX_DEPTH:
        raise ConfigError(f"[engraving] depth {s.depth:g} mm exceeds the sanity limit of {MAX_DEPTH:g} mm")
    if not s.clearance_z >= s.retract_z >= s.feed_z:
        raise ConfigError("Heights must satisfy clearance >= retract >= feed")
    if not 50 < s.spindle_percent <= 100:
        raise ConfigError(f"[spindle] percent must be above 50 and at most 100, got {s.spindle_percent:g}")
    if 2 * s.edge_margin >= min(s.stock_width, s.stock_length):
        raise ConfigError("[text] edge_margin is larger than the stock allows")
    for key, value in (("columns", s.fixture_columns), ("rows", s.fixture_rows)):
        if not value.is_integer() or not 1 <= value <= MAX_SLOTS_PER_AXIS:
            raise ConfigError(f"[fixture] {key} must be a whole number from 1 to {MAX_SLOTS_PER_AXIS}, got {value:g}")
    if s.columns > 1 and s.pitch_x < s.stock_width:
        raise ConfigError(
            f"[fixture] pitch_x {s.pitch_x:g} mm is smaller than the cover width {s.stock_width:g} mm: the covers would overlap"
        )
    if s.rows > 1 and s.pitch_y < s.stock_length:
        raise ConfigError(
            f"[fixture] pitch_y {s.pitch_y:g} mm is smaller than the cover length {s.stock_length:g} mm: the covers would overlap"
        )
    return s


def values_of(settings: Settings) -> dict[str, float]:
    """The numbers the Settings dialog edits, as {Settings field name: value}."""
    return {f.field: getattr(settings, f.field) for f in FIELDS}


def load_defaults(path: Path | str | None = None) -> Settings:
    """The known-good settings from config.defaults.toml (only read, never written)."""
    return load_settings(path or DEFAULTS_PATH)


def save_settings(values: Mapping[str, float], path: Path | str | None = None) -> Settings:
    """Write `values` ({Settings field name: number}) into the config file and return the new Settings.

    Only those numbers change: comments, layout and the [[cutout]] blocks stay exactly as they were.
    The new content is validated with parse_settings BEFORE anything is written, so an invalid value
    raises ConfigError and leaves the file untouched. The previous file is kept as <name>.bak, and the
    new text goes to a temporary file that then replaces the original in one step.
    """
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    unknown = set(values) - {f.field for f in FIELDS}
    if unknown:
        raise ValueError(f"Not a settings field: {', '.join(sorted(unknown))}")
    try:
        old_text = path.read_bytes().decode("utf-8")  # bytes keep the file's own line endings
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    try:
        doc = tomlkit.parse(old_text)
    except TOMLKitError as exc:
        raise ConfigError(f"Config file {path} is not valid TOML: {exc}") from None

    for spec in FIELDS:
        if spec.field not in values:
            continue
        if spec.section not in doc:
            raise ConfigError(f"Config file has no [{spec.section}] section")
        table = doc[spec.section]
        old = table.get(spec.key)  # type: ignore[union-attr]
        value = float(values[spec.field])
        # Keep whole numbers that were written without a decimal point (1600, not 1600.0).
        keep_int = isinstance(old, int) and not isinstance(old, bool) and value.is_integer()
        table[spec.key] = int(value) if keep_int else value  # type: ignore[index]

    new_text = tomlkit.dumps(doc)
    settings = parse_settings(tomllib.loads(new_text))  # raises ConfigError; nothing written yet
    if new_text != old_text:
        path.with_name(path.name + ".bak").write_bytes(old_text.encode("utf-8"))
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(new_text.encode("utf-8"))
        os.replace(temporary, path)
    return settings
