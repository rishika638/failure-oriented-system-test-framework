import type { Request } from "express";

export type FailureScenario = "latency" | "timeout" | "dependency";

export interface CaptureOptions {
  apiUrl: string;
  apiKey: string;
  scenarioForRequest: (request: Request, statusCode: number, latencyMs: number) => FailureScenario | undefined;
  captureBody?: boolean;
  maxPayloadBytes?: number;
  timeoutMs?: number;
  onCaptureError?: (error: unknown) => void;
}

export interface CapturePayload {
  scenario: FailureScenario;
  method: "GET";
  path: string;
  status_code: number;
  latency_ms: number;
  request_id: string;
  headers: Record<string, string>;
  body?: Record<string, unknown>;
  occurred_at: string;
}
