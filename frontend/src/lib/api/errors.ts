export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function formatFastApiDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const loc = "loc" in item && Array.isArray(item.loc) ? item.loc.join(".") : "";
          return loc ? `${loc}: ${String(item.msg)}` : String(item.msg);
        }
        return JSON.stringify(item);
      })
      .join("\n");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail, null, 2);
  }
  return String(detail);
}

export function formatApiErrorBody(status: number, body: string): string {
  const trimmed = body.trim();
  if (!trimmed) return `HTTP ${status}`;

  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown; message?: unknown };
    if (parsed.detail !== undefined) {
      return formatFastApiDetail(parsed.detail);
    }
    if (typeof parsed.message === "string" && parsed.message.trim()) {
      return parsed.message;
    }
  } catch {
    // Plain-text response (e.g. nginx default page).
  }

  return trimmed;
}

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}
