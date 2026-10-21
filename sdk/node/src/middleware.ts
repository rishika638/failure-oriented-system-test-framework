import { randomUUID } from "node:crypto";
import { performance } from "node:perf_hooks";
import type { NextFunction, Request, Response } from "express";
import { sendCapture } from "./client";
import { redact } from "./redaction";
import type { CaptureOptions, CapturePayload } from "./types";

export function captureMiddleware(options: CaptureOptions) {
  const maxPayloadBytes = options.maxPayloadBytes ?? 16_384;
  const timeoutMs = options.timeoutMs ?? 1_000;
  if (!Number.isInteger(maxPayloadBytes) || maxPayloadBytes < 1024 || maxPayloadBytes > 65_536) {
    throw new RangeError("maxPayloadBytes must be between 1024 and 65536");
  }
  if (!Number.isInteger(timeoutMs) || timeoutMs < 50 || timeoutMs > 10_000) {
    throw new RangeError("timeoutMs must be between 50 and 10000");
  }
  const report = (error: unknown): void => {
    try {
      options.onCaptureError?.(error);
    } catch {
      // Error reporting is best-effort too; it must not affect the application.
    }
  };

  return (request: Request, response: Response, next: NextFunction): void => {
    const requestId = request.get("X-Request-ID")?.slice(0, 128) || randomUUID();
    response.setHeader("X-Request-ID", requestId);
    const started = performance.now();
    response.once("finish", () => {
      const latencyMs = Math.max(0, performance.now() - started);
      if (request.method !== "GET") return;
      let scenario: ReturnType<CaptureOptions["scenarioForRequest"]>;
      try {
        scenario = options.scenarioForRequest(request, response.statusCode, latencyMs);
      } catch (error) {
        report(error);
        return;
      }
      if (!scenario) return;

      const payload = redact({
        scenario,
        method: "GET",
        path: request.path,
        status_code: response.statusCode,
        latency_ms: Number(latencyMs.toFixed(2)),
        request_id: requestId,
        headers: {
          "content-type": request.get("content-type") ?? "",
          "user-agent": request.get("user-agent") ?? "",
        },
        body: options.captureBody === true && request.body && typeof request.body === "object"
          ? request.body
          : undefined,
        occurred_at: new Date().toISOString(),
      }, maxPayloadBytes) as CapturePayload;

      void sendCapture(options.apiUrl, options.apiKey, payload, timeoutMs)
        .catch(report);
    });
    next();
  };
}
