import re
from typing import Any


_SECRET_KEY = re.compile(
    r"(authorization|cookie|password|passwd|secret|token|api[-_]?key|credential)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*")
_MAX_STRING = 4096
_MAX_ITEMS = 100


def redact(value: Any, depth: int = 0, budget=None) -> Any:
    if budget is None:
        budget = {"nodes": 1000, "bytes": 64 * 1024}
    if depth > 8 or budget["nodes"] <= 0 or budget["bytes"] <= 0:
        return "[TRUNCATED]"
    budget["nodes"] -= 1
    if isinstance(value, dict):
        result = {}
        for key, item in list(value.items())[:_MAX_ITEMS]:
            key = str(key)[:128]
            budget["bytes"] -= len(key.encode("utf-8"))
            if budget["bytes"] <= 0:
                result[key] = "[TRUNCATED]"
                break
            result[key] = "[REDACTED]" if _SECRET_KEY.search(key) else redact(item, depth + 1, budget)
        return result
    if isinstance(value, (list, tuple)):
        return [redact(item, depth + 1, budget) for item in value[:_MAX_ITEMS]]
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        encoded = encoded[: min(_MAX_STRING, budget["bytes"])]
        value = encoded.decode("utf-8", errors="ignore")
        budget["bytes"] -= len(value.encode("utf-8"))
        return _SECRET_VALUE.sub(r"\1[REDACTED]", value)
    if value is None or isinstance(value, (bool, int, float)):
        budget["bytes"] -= 16
        return value
    budget["bytes"] -= 128
    return str(value)[:_MAX_STRING]
