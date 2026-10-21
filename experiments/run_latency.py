import argparse
import json

from failures.latency import add_latency, remove_latency
from traffic.runner import run_load


def _run(args):
    baseline = run_load(args.url, args.rps, args.duration, args.timeout, args.concurrency)
    result = {"baseline": baseline, "degraded": None, "recovery": None, "fault_effect_confirmed": None}
    if args.netem_delay_ms is None:
        return result

    add_latency(args.netem_delay_ms, interface=args.interface)
    try:
        result["degraded"] = run_load(
            args.url, args.rps, args.duration, args.timeout, args.concurrency
        )
    finally:
        remove_latency()
    result["recovery"] = run_load(args.url, args.rps, args.duration, args.timeout, args.concurrency)

    baseline_p95 = baseline.get("p95_ms")
    degraded_p95 = result["degraded"].get("p95_ms")
    result["fault_effect_confirmed"] = (
        baseline_p95 is not None
        and degraded_p95 is not None
        and degraded_p95 - baseline_p95 >= args.netem_delay_ms * 0.5
    )
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Measure a controlled target; optional tc/netem is Linux-only and path-dependent."
    )
    parser.add_argument("--url", default="http://127.0.0.1:8080/ping")
    parser.add_argument("--rps", type=float, default=10)
    parser.add_argument("--duration", type=float, default=10)
    parser.add_argument("--timeout", type=float, default=3)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--netem-delay-ms", type=int)
    parser.add_argument("--interface", help="Linux interface name; required with --netem-delay-ms")
    args = parser.parse_args()
    try:
        result = _run(args)
    finally:
        remove_latency()
    print(json.dumps(result, indent=2))
    if result["fault_effect_confirmed"] is False:
        print("Configured netem did not measurably affect this traffic path.")


if __name__ == "__main__":
    main()
