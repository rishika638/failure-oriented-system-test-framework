import os
import platform
import re
import subprocess


_active_fault = None


def _run_tc(*args):
    if platform.system() != "Linux":
        raise OSError("tc/netem is available only on Linux")
    return subprocess.run(
        ["tc", *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )


def add_latency(delay_ms, interface=None):
    global _active_fault
    if not isinstance(delay_ms, int) or not 1 <= delay_ms <= 10_000:
        raise ValueError("delay_ms must be an integer between 1 and 10000")
    interface = interface or os.environ.get("NETEM_INTERFACE")
    if not interface:
        raise ValueError("Set NETEM_INTERFACE to the explicitly selected Linux interface")
    if not interface.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Invalid network interface name")
    if _active_fault is not None:
        raise RuntimeError("This process already owns an active netem fault")

    existing = _run_tc("qdisc", "show", "dev", interface).stdout
    if any(" root " in f" {line} " or line.strip().startswith("qdisc ") and " root" in line
           for line in existing.splitlines()):
        raise RuntimeError(
            f"{interface} already has a root qdisc; refusing to replace or remove it"
        )

    _run_tc("qdisc", "add", "dev", interface, "root", "netem", "delay", f"{delay_ms}ms")
    _active_fault = (interface, delay_ms)
    return _active_fault


def remove_latency():
    global _active_fault
    if _active_fault is None:
        return False
    interface, delay = _active_fault
    current = _run_tc("qdisc", "show", "dev", interface).stdout
    owned = any(
        "netem" in line
        and (match := re.search(r"\bdelay\s+(\d+(?:\.\d+)?)ms\b", line))
        and float(match.group(1)) == delay
        for line in current.splitlines()
    )
    if not owned:
        _active_fault = None
        raise RuntimeError(
            f"Refusing to remove a qdisc on {interface}: the active netem configuration changed"
        )
    _run_tc("qdisc", "del", "dev", interface, "root")
    _active_fault = None
    return True
