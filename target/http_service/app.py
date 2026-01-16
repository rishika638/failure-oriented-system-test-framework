import signal
import sys
from server import create_app

app = create_app()

def shutdown_handler(sig, frame):
    print("Graceful shutdown initiated")
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080,
        threaded=True
    )