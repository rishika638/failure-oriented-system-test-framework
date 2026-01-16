from runner import run_load

if __name__ == "__main__":
    result = run_load(
        url="http://localhost:8080/ping",
        rps=10,
        duration=20,
        timeout=1.0
    )

    print("\n=== BASELINE METRICS ===")
    for k, v in result.items():
        print(f"{k}: {v}")