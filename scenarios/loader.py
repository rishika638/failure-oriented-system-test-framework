import json
from pathlib import Path

from scenarios.schema import Scenario


_ROOT = Path(__file__).with_name("fixtures")


def load_scenario(name: str) -> Scenario:
    if name not in {"latency", "timeout", "dependency"}:
        raise ValueError(f"Unsupported scenario: {name}")
    path = _ROOT / f"{name}.json"
    return Scenario.model_validate(json.loads(path.read_text(encoding="utf-8")))
