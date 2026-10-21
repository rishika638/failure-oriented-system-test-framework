const SECRET_KEY = /(authorization|cookie|password|passwd|secret|token|api[-_]?key|credential)/i;

export function redact(value: unknown, maxBytes = 16_384): unknown {
  const budget = { remaining: maxBytes };
  const visit = (item: unknown, depth: number): unknown => {
    if (budget.remaining <= 0 || depth > 6) return "[TRUNCATED]";
    if (typeof item === "string") {
      const limit = Math.min(1024, budget.remaining);
      const bytes = Buffer.from(item, "utf8");
      let value = bytes.subarray(0, limit).toString("utf8");
      if (bytes.length > limit && value.endsWith("\uFFFD")) value = value.slice(0, -1);
      budget.remaining -= Buffer.byteLength(value, "utf8");
      return value.replace(/(Bearer\s+)[A-Za-z0-9._~+/-]+=*/gi, "$1[REDACTED]");
    }
    if (item === null || typeof item === "number" || typeof item === "boolean") {
      budget.remaining -= 16;
      return item;
    }
    if (Array.isArray(item)) return item.slice(0, 50).map((child) => visit(child, depth + 1));
    if (typeof item === "object") {
      const result: Record<string, unknown> = {};
      for (const [originalKey, child] of Object.entries(item as Record<string, unknown>).slice(0, 50)) {
        const key = originalKey.slice(0, 100);
        budget.remaining -= Buffer.byteLength(key, "utf8") + 4;
        if (budget.remaining <= 0) break;
        result[key] = SECRET_KEY.test(key) ? "[REDACTED]" : visit(child, depth + 1);
      }
      return result;
    }
    return undefined;
  };
  return visit(value, 0);
}
