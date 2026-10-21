import type { CapturePayload } from "./types";

export async function sendCapture(
  apiUrl: string,
  apiKey: string,
  payload: CapturePayload,
  timeoutMs: number,
): Promise<void> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${apiUrl.replace(/\/+$/, "")}/v1/captures`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        "X-Request-ID": payload.request_id,
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Capture API returned HTTP ${response.status}`);
  } finally {
    clearTimeout(timeout);
  }
}
