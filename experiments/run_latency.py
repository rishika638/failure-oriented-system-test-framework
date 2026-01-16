print("=== SCRIPT STARTED ===")

from failures.latency import add_latency, remove_latency
from traffic.runner import run_load
import time

print("=== BASELINE ===")
baseline = run_load(
    url="http://localhost:8080/ping",
    rps=10,
    duration=10
)
print(baseline)

print("\n=== ADDING LATENCY ===")
add_latency(300)
time.sleep(2)

degraded = run_load(
    url="http://localhost:8080/ping",
    rps=10,
    duration=10
)
print(degraded)

print("\n=== REMOVING LATENCY ===")
remove_latency()

print("\n=== RECOVERY ===")
recovery = run_load(
    url="http://localhost:8080/ping",
    rps=10,
    duration=10
)
print(recovery)