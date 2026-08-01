export const DRIVE_SESSION_KEY = "story-drive-session-v1";

export type DriveSessionState = {
  category: string;
  year: number;
  month: number;
  selectedIds: string[];
  platform: string;
  format: string;
  objectives: string[];
  inputFidelity: string;
  loaded: boolean;
};

export function loadDriveSession(): Partial<DriveSessionState> | null {
  try {
    const raw = sessionStorage.getItem(DRIVE_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<DriveSessionState>;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function saveDriveSession(state: DriveSessionState): void {
  try {
    sessionStorage.setItem(DRIVE_SESSION_KEY, JSON.stringify(state));
  } catch {
    // sessionStorage pieno o disabilitato — ignora
  }
}

export function driveAssetsQueryKey(category: string, year: number, month: number) {
  return ["drive", "assets", category, year, month] as const;
}
