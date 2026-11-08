"""Validated server settings, loaded independently of the working directory."""
from dataclasses import dataclass
import math
from pathlib import Path
import tomllib


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


@dataclass(frozen=True)
class Settings:
    turn_timeout_seconds: float
    starting_stack: int
    small_blind: int
    big_blind: int


def load_config(path: Path | None = None) -> Settings:
    path = DEFAULT_CONFIG_PATH if path is None else Path(path)
    try:
        with path.open("rb") as file:
            values = tomllib.load(file)
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot load configuration {path}: {error}") from error

    expected = {"turn_timeout_seconds", "starting_stack", "small_blind", "big_blind"}
    if values.keys() != expected:
        raise ValueError(f"Configuration {path} must contain exactly: {', '.join(sorted(expected))}")
    timeout = values["turn_timeout_seconds"]
    stack = values["starting_stack"]
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("turn_timeout_seconds must be a finite positive number")
    for name in ("starting_stack", "small_blind", "big_blind"):
        if type(values[name]) is not int or values[name] <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if values["small_blind"] > values["big_blind"]:
        raise ValueError("small_blind must be less than or equal to big_blind")
    return Settings(turn_timeout_seconds=float(timeout), starting_stack=stack,
                    small_blind=values["small_blind"], big_blind=values["big_blind"])
