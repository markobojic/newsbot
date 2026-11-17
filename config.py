"""Load and validate the YAML files in config/. Plain Python, no Claude.

A broken config is my bug, not a tool error: it raises at startup and never
reaches the model as a tool_result (the model can't fix my YAML).
"""

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parent / "config"  # independent of the working directory
CAMPS = {"sns", "student", "public", "world"}
OUTLET_FIELDS = ("name", "camp", "language", "url")
HOLDING_FIELDS = ("ticker", "name")


def _read(path: Path) -> dict:
    # safe_load, never load: load can build arbitrary Python objects from the file.
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources(path: Path = CONFIG_DIR / "sources.yaml") -> dict[str, dict]:
    """Return outlets as {key: {name, camp, language, url}}; raise ValueError if invalid."""
    outlets = _read(path)["outlets"]
    for key, outlet in outlets.items():
        missing = [f for f in OUTLET_FIELDS if f not in outlet]
        if missing:
            raise ValueError(f"{path.name}: outlet '{key}' is missing {missing}")
        if outlet["camp"] not in CAMPS:
            raise ValueError(
                f"{path.name}: outlet '{key}' has unknown camp '{outlet['camp']}', "
                f"expected one of {sorted(CAMPS)}"
            )
    return outlets


def load_holdings(path: Path = CONFIG_DIR / "holdings.yaml") -> dict:
    """Return {notable_move_pct, holdings: [{ticker, name}]}; raise ValueError if invalid."""
    data = _read(path)
    if not isinstance(data.get("notable_move_pct"), (int, float)):
        raise ValueError(f"{path.name}: notable_move_pct must be a number")
    for i, holding in enumerate(data["holdings"]):
        missing = [f for f in HOLDING_FIELDS if f not in holding]
        if missing:
            raise ValueError(f"{path.name}: holding #{i + 1} is missing {missing}")
    return data
