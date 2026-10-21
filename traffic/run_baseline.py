import argparse

from traffic.runner import run_load

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Measure a controlled HTTP target")
    parser.add_argument("--url", default="http://127.0.0.1:8080/ping")
    parser.add_argument("--rps", type=float, default=10)
    parser.add_argument("--duration", type=float, default=20)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--concurrency", type=int, default=32)
    args = parser.parse_args()
    result = run_load(
        url=args.url,
        rps=args.rps,
        duration=args.duration,
        timeout=args.timeout,
        concurrency=args.concurrency,
    )

    print("\n=== BASELINE METRICS ===")
    for k, v in result.items():
        print(f"{k}: {v}")