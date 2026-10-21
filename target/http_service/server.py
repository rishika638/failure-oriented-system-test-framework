import time
import logging
import os
from flask import Flask, jsonify, request
from fault_injection.policy import apply_delay, parse_fault

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
        header = request.headers.get("X-Engine-Fault", "") if os.environ.get("ENABLE_TEST_FAULTS") == "true" else ""
        try:
            fault = parse_fault(header)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        if fault and fault.kind == "dependency":
            return jsonify({"error": "synthetic dependency unavailable"}), 503
        if fault:
            apply_delay(fault)
        start = time.monotonic()

        # Simulated processing delay (baseline)
        time.sleep(0.05)

        latency_ms = int((time.monotonic() - start) * 1000)

        logging.info(f"PING handled | latency={latency_ms}ms")

        return jsonify({
            "message": "pong",
            "latency_ms": latency_ms
        }), 200

    @app.route("/dependency")
    def dependency():
        enabled = os.environ.get("ENABLE_TEST_FAULTS") == "true"
        try:
            fault = parse_fault(request.headers.get("X-Engine-Fault", "") if enabled else "")
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        if fault and fault.kind == "dependency":
            return jsonify({"error": "synthetic dependency unavailable"}), 503
        return jsonify({"dependency": "ok"}), 200

    return app