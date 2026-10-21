import random
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Fault:
    kind: str
    delay_ms: int = 0
    jitter_max_ms: int = 0


def parse_fault(header: str) -> Fault | None:
    if not header:
        return None
    if header == "dependency":
        return Fault(kind="dependency")
    if header == "abort":
        return Fault(kind="abort")
    if header.startswith("latency:") or header.startswith("timeout:"):
        kind, raw_delay = header.split(":", 1)
        try:
            delay = int(raw_delay)
        except ValueError as error:
            raise ValueError("Fault delay must be an integer") from error
        if not 0 <= delay <= 30_000:
            raise ValueError("Fault delay must be between 0 and 30000 ms")
        return Fault(kind=kind, delay_ms=delay)
    if header.startswith("jitter:"):
        try:
            minimum, maximum = (int(value) for value in header.split(":")[1:])
        except (ValueError, TypeError) as error:
            raise ValueError("Jitter requires integer minimum and maximum delays") from error
        if not 0 <= minimum <= maximum <= 10_000:
            raise ValueError("Jitter must satisfy 0 <= minimum <= maximum <= 10000 ms")
        return Fault(kind="jitter", delay_ms=minimum, jitter_max_ms=maximum)
    raise ValueError("Unsupported synthetic fault")


def apply_delay(fault: Fault) -> None:
    if fault.kind == "jitter":
        delay_ms = random.SystemRandom().randint(fault.delay_ms, fault.jitter_max_ms)
    else:
        delay_ms = fault.delay_ms
    if delay_ms:
        time.sleep(delay_ms / 1000)
