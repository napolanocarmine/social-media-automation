export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
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
    const obj = detail as { code?: unknown; message?: unknown };
    if (typeof obj.message === "string" && obj.message.trim()) {
      return obj.message;
    }
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

export function isGoogleTokenError(error: unknown): boolean {
  if (error instanceof ApiError) {
    if (error.code === "google_token_expired") return true;
    const msg = error.message.toLowerCase();
    return msg.includes("invalid_grant") || msg.includes("scaduta o revocata");
  }
  if (error instanceof Error) {
    const msg = error.message.toLowerCase();
    return (
      msg.includes("invalid_grant") ||
      msg.includes("token has been expired or revoked") ||
      msg.includes("scaduta o revocata")
    );
  }
  return false;
}

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}
