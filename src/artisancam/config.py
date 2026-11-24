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
class Settings:
    stock_width: float
    stock_length: float
    text_height: float
    top_margin: float
    letter_gap: float
    space_width: float
    edge_margin: float
    depth: float
    clearance_z: float
    retract_z: float
    feed_z: float
    cutting_feed: float
    plunge_feed: float
    retract_feed: float
    spindle_percent: float
    spindle_warmup_s: float


# (section, key) -> Settings field. This table is the whole file format.
_FIELDS = {
    ("stock", "width"): "stock_width",
    ("stock", "length"): "stock_length",
    ("text", "height"): "text_height",
    ("text", "top_margin"): "top_margin",
    ("text", "letter_gap"): "letter_gap",
    ("text", "space_width"): "space_width",
    ("text", "edge_margin"): "edge_margin",
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
_MAY_BE_ZERO = {"top_margin", "edge_margin", "spindle_warmup_s"}


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


def parse_settings(raw: dict) -> Settings:
    for section, table in raw.items():
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
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"[{section}] {key} must be a number, got {value!r}")
        value = float(value)
        if value != value or value in (float("inf"), float("-inf")):
            raise ConfigError(f"[{section}] {key} must be a finite number")
        if value < 0 or (value == 0 and field not in _MAY_BE_ZERO):
            raise ConfigError(f"[{section}] {key} must be {'>= 0' if field in _MAY_BE_ZERO else '> 0'}, got {value:g}")
        values[field] = value

    s = Settings(**values)
    if s.depth > MAX_DEPTH:
        raise ConfigError(f"[engraving] depth {s.depth:g} mm exceeds the sanity limit of {MAX_DEPTH:g} mm")
    if not s.clearance_z >= s.retract_z >= s.feed_z:
        raise ConfigError("Heights must satisfy clearance >= retract >= feed")
    if not 50 < s.spindle_percent <= 100:
        raise ConfigError(f"[spindle] percent must be above 50 and at most 100, got {s.spindle_percent:g}")
    if 2 * s.edge_margin >= min(s.stock_width, s.stock_length):
        raise ConfigError("[text] edge_margin is larger than the stock allows")
    return s
