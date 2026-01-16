import time
import logging
from flask import Flask, jsonify

def create_app():
    app = Flask(__name__)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/ping")
    def ping():
        start = time.time()

        # Simulated processing delay (baseline)
        time.sleep(0.05)

        latency_ms = int((time.time() - start) * 1000)

        logging.info(f"PING handled | latency={latency_ms}ms")

        return jsonify({
            "message": "pong",
            "latency_ms": latency_ms
        }), 200

    return app