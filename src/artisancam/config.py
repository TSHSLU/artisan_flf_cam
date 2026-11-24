"""Load and validate config.toml into one frozen Settings object.

Every value is required, unknown keys are rejected (typo guard), and nonsensical values
fail with a message that names the key. A bad config must never turn into a bad G-code file.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.toml"

# Sanity limit for the V-bit engraving depth: guards against a 0.2 -> 2 typo.
MAX_DEPTH = 1.0


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
    cutouts: tuple[Cutout, ...] = ()

    @property
    def cutout_versions(self) -> tuple[str, ...]:
        """The version names used by the cut-outs, in order of first appearance."""
        return tuple(dict.fromkeys(c.version for c in self.cutouts))


# (section, key) -> Settings field. This table is the whole file format, apart from [[cutout]].
_FIELDS = {
    ("stock", "width"): "stock_width",
    ("stock", "length"): "stock_length",
    ("text", "letter_gap"): "letter_gap",
    ("text", "space_width"): "space_width",
    ("text", "edge_margin"): "edge_margin",
    ("text_top", "height"): "top_height",
    ("text_top", "margin"): "top_margin",
    ("text_bottom", "height"): "bottom_height",
    ("text_bottom", "margin"): "bottom_margin",
    ("engraving", "depth"): "depth",
    ("heights", "clearance"): "clearance_z",
    ("heights", "retract"): "retract_z",
    ("heights", "feed"): "feed_z",
    ("feeds", "cutting"): "cutting_feed",
    ("feeds", "plunge"): "plunge_feed",
    ("feeds", "retract"): "retract_feed",
    ("spindle", "percent"): "spindle_percent",
    ("spindle", "warmup_s"): "spindle_warmup_s",
}

# Fields that may be zero; every other field must be > 0.
_MAY_BE_ZERO = {"top_margin", "bottom_margin", "edge_margin", "spindle_warmup_s"}

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
    values: dict[str, float | str] = {}
    for key in _CUTOUT_KEYS[shape]:
        if key not in entry:
            raise ConfigError(f"{where}: missing key {key}")
        value = _number(entry[key], f"{where} {key}")
        if key in _CUTOUT_POSITIVE and value <= 0:
            raise ConfigError(f"{where} {key} must be > 0, got {value:g}")
        values[key] = value
    if shape == "d" and ("flat" in entry or "flat_side" in entry):
        if "flat" not in entry or "flat_side" not in entry:
            raise ConfigError(f"{where}: flat and flat_side belong together; give both or neither")
        flat = _number(entry["flat"], f"{where} flat")
        if not 0 < flat < (values["diameter"] / 2):
            raise ConfigError(f"{where}: flat must be between 0 and the radius ({values['diameter'] / 2:g} mm), got {flat:g}")
        if entry["flat_side"] not in _FLAT_SIDES:
            raise ConfigError(f"{where}: flat_side must be one of {', '.join(_FLAT_SIDES)}, got {entry['flat_side']!r}")
        values["flat"], values["flat_side"] = flat, entry["flat_side"]
    return Cutout(name=name.strip(), version=version.strip(), shape=shape, **values)


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
    return s
