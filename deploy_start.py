import os
import signal
import subprocess
import sys
import time

processes = []
stopping = False


def stop_all(*_):
    global stopping
    stopping = True

    for _, process in reversed(processes):
        if process.poll() is None:
            process.terminate()


signal.signal(signal.SIGTERM, stop_all)
signal.signal(signal.SIGINT, stop_all)


def start(name, command, env=None):
    print(f"[startup] starting {name}", flush=True)
    process = subprocess.Popen(command, env=env)
    processes.append((name, process))

    time.sleep(2)

    if process.poll() is not None:
        raise RuntimeError(f"{name} exited during startup")

    return process


try:
    subprocess.run(["alembic", "upgrade", "head"], check=True)

    target_env = os.environ.copy()
    target_env["ENABLE_TEST_FAULTS"] = "true"
    target_env["PYTHONPATH"] = "/app"

    start(
        "synthetic-target",
        [sys.executable, "target/http_service/app.py"],
        target_env,
    )

    start(
        "fault-proxy",
        [
            sys.executable, "-m", "uvicorn",
            "fault_injection.proxy:app",
            "--host", "127.0.0.1",
            "--port", "8081",
        ],
    )

    start(
        "replay-worker",
        [sys.executable, "-m", "worker.main"],
    )

    start(
        "api",
        [
            sys.executable, "-m", "uvicorn",
            "api.main:app",
            "--host", "0.0.0.0",
            "--port", os.environ.get("PORT", "8000"),
        ],
    )

    while not stopping:
        for name, process in processes:
            code = process.poll()
            if code is not None:
                raise RuntimeError(f"{name} exited with code {code}")
        time.sleep(1)

except Exception as error:
    print(f"[startup] fatal: {error}", file=sys.stderr, flush=True)
    stop_all()
    sys.exit(1)

finally:
    stop_all()

    for name, process in reversed(processes):
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
