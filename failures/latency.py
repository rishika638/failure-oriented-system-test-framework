import subprocess

INTERFACE = "enp0s3"   # change if needed

def add_latency(delay_ms):
    subprocess.run(
        ["tc", "qdisc", "add", "dev", INTERFACE, "root", "netem", "delay", f"{delay_ms}ms"],
        check=True
    )

def remove_latency():
    subprocess.run(
        ["tc", "qdisc", "del", "dev", INTERFACE, "root"],
        check=True
    )