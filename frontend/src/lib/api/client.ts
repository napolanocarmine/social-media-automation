import { ApiError, formatApiErrorBody } from "./errors";

export type ImageMediaUrls = {
  processed: string;
  original: string;
};

export type ImageSummary = {
  id: number;
  name: string;
  path: string;
  business_category: string | null;
  approval_status: "pending" | "approved" | "rejected";
  visual_score: number | null;
  visual_status: string | null;
  editing_required: boolean | null;
  visual_method: string | null;
  has_processed_file: boolean;
  has_original_file: boolean;
  media: ImageMediaUrls;
  created_at: string;
  updated_at: string;
};

export type ImageListResponse = {
  items: ImageSummary[];
  total: number;
  limit?: number;
  offset?: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
};

export type ApprovalAction = "approve" | "reject" | "use_original";

export type DriveAsset = {
  file_id: string;
  name: string;
  mime_type: string;
  category: string | null;
  path_segments: string[];
  path_hint: string;
};

export type DriveAssetListResponse = {
  items: DriveAsset[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type BatchSummary = {
  id: number;
  status: string;
  category: string | null;
  platform: string | null;
  media_format: string | null;
  requested_count: number;
  completed_count: number;
  failed_count: number;
  done_count: number;
  progress_pct: number;
  started_at: string;
  finished_at: string;
  runner_pid: number | null;
  stop_requested_at: string | null;
  stop_reason: string | null;
  last_error: string | null;
  note: string | null;
  updated_at: string;
};

export type BatchDetailResponse = {
  batch: BatchSummary;
  items: Array<{
    id: number;
    batch_id: number;
    item_index: number;
    status: string;
    source_asset_name: string | null;
    error_message: string | null;
    image_id: number | null;
  }>;
};

export type DashboardStats = {
  processed_visual: number;
  pending_approval: number;
  ready_to_plan: number;
  due_dispatch: number;
  running_batches: number;
};

export type SuggestedNextStep = {
  page: string;
};

export type CopyPack = {
  instagram_caption?: string;
  facebook_caption?: string;
  story_text?: string;
  hashtags?: string[] | string;
  [key: string]: unknown;
};

export type SuggestSlot = {
  platform: string;
  scheduled_for: string;
  scheduled_date: string;
  scheduled_time: string;
  weekday: string;
  weekday_label: string;
  time_hhmm: string;
  timezone: string;
};

export type CalendarEvent = {
  id: number;
  image_id: number;
  image_name: string;
  platform: string;
  event_type: string;
  scheduled_for: string;
  time_label: string;
  day: number | null;
  external_id: string | null;
  detail: string | null;
  caption: string | null;
  media_format: string;
  media: ImageMediaUrls;
};

export type CalendarResponse = {
  year: number;
  month: number;
  total: number;
  items: CalendarEvent[];
  by_day: Record<string, CalendarEvent[]>;
};

export type PlanActionResponse = {
  message: string;
  event_id?: number | null;
  image_id: number;
  platform: string;
  scheduled_for?: string | null;
};

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(formatApiErrorBody(response.status, text), response.status);
  }
  return response.json() as Promise<T>;
}

export async function fetchDashboardStats(): Promise<DashboardStats> {
  return parseJson(await fetch("/api/v1/dashboard/stats"));
}

export async function fetchSuggestedNextStep(): Promise<SuggestedNextStep> {
  return parseJson(await fetch("/api/v1/dashboard/suggested-next-step"));
}

export async function fetchHealth(): Promise<{ status: string }> {
  return parseJson(await fetch("/api/v1/health"));
}

export async function fetchAiOutput(
  filter: string,
  limit = 24,
  offset = 0,
): Promise<ImageListResponse> {
  const params = new URLSearchParams({
    filter,
    limit: String(limit),
    offset: String(offset),
  });
  return parseJson(await fetch(`/api/v1/images/ai-output?${params}`));
}

export async function fetchPendingApproval(params: {
  platform: string;
  format: string;
  category: string;
  page: number;
  pageSize?: number;
}): Promise<ImageListResponse> {
  const qs = new URLSearchParams({
    platform: params.platform,
    format: params.format,
    category: params.category,
    page: String(params.page),
    page_size: String(params.pageSize ?? 20),
  });
  return parseJson(await fetch(`/api/v1/images/pending-approval?${qs}`));
}

export async function fetchImageCategories(): Promise<{ categories: string[] }> {
  return parseJson(await fetch("/api/v1/config/categories"));
}

export async function fetchDriveAssets(params: {
  category: string;
  year?: number;
  month?: number;
  page: number;
  pageSize?: number;
  refreshCache?: boolean;
}): Promise<DriveAssetListResponse> {
  const qs = new URLSearchParams({
    category: params.category,
    page: String(params.page),
    page_size: String(params.pageSize ?? 12),
  });
  if (params.year != null) qs.set("year", String(params.year));
  if (params.month != null) qs.set("month", String(params.month));
  if (params.refreshCache) qs.set("refresh_cache", "true");
  return parseJson(await fetch(`/api/v1/drive/assets?${qs}`));
}

export function driveThumbnailUrl(fileId: string, mimeType: string): string {
  const qs = new URLSearchParams({ mime_type: mimeType });
  return `/api/v1/drive/thumbnails/${encodeURIComponent(fileId)}?${qs}`;
}

export async function startAiBatch(body: {
  category: string;
  platform: string;
  media_format: string;
  assets: DriveAsset[];
  marketing_objectives?: string[];
  channels?: string[];
  clear_thumb_cache?: boolean;
}): Promise<{ batch_id: number }> {
  return parseJson(
    await fetch("/api/v1/batches/ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function fetchActiveBatch(): Promise<BatchSummary | null> {
  const response = await fetch("/api/v1/batches/active");
  if (response.status === 204) return null;
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(formatApiErrorBody(response.status, text), response.status);
  }
  const data = (await response.json()) as BatchSummary | null;
  return data;
}

export async function fetchBatchDetail(batchId: number): Promise<BatchDetailResponse> {
  return parseJson(await fetch(`/api/v1/batches/${batchId}`));
}

export async function stopBatch(batchId: number, reason?: string): Promise<void> {
  await parseJson(
    await fetch(`/api/v1/batches/${batchId}/stop`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason ?? null }),
    }),
  );
}

export async function postImageApproval(
  imageId: number,
  action: ApprovalAction,
): Promise<{ id: number; approval_status: string }> {
  return parseJson(
    await fetch(`/api/v1/images/${imageId}/approval`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    }),
  );
}

export async function fetchPlannableImages(params: {
  platform: string;
  format: string;
  category: string;
  page: number;
  pageSize?: number;
}): Promise<ImageListResponse> {
  const qs = new URLSearchParams({
    platform: params.platform,
    format: params.format,
    category: params.category,
    page: String(params.page),
    page_size: String(params.pageSize ?? 10),
  });
  return parseJson(await fetch(`/api/v1/images/plannable?${qs}`));
}

export async function fetchImageCopy(imageId: number): Promise<{ copy: CopyPack } | null> {
  const response = await fetch(`/api/v1/images/${imageId}/copy`);
  if (response.status === 404) return null;
  return parseJson(response);
}

export async function generateImageCopy(
  imageId: number,
  body: {
    platform: string;
    media_format: string;
    marketing_objectives?: string[];
    marketing_objective?: string | null;
    channels?: string[];
  },
): Promise<{ copy: CopyPack }> {
  return parseJson(
    await fetch(`/api/v1/images/${imageId}/copy/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function fetchMarketingObjectives(): Promise<{ objectives: string[] }> {
  return parseJson(await fetch("/api/v1/config/marketing-objectives"));
}

export type DispatchConfig = {
  manual_enabled: boolean;
  auto_enabled: boolean;
  auto_interval_seconds: number;
  auto_interval_minutes: number;
  manual_endpoints: {
    run: string;
    dry_run: string;
    due: string;
  };
  cli_command: string;
};

export async function fetchDispatchConfig(): Promise<DispatchConfig> {
  return parseJson(await fetch("/api/v1/config/dispatch"));
}

export async function suggestPlanSlot(platform: string): Promise<SuggestSlot | null> {
  const response = await fetch("/api/v1/plans/suggest-slot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ platform }),
  });
  if (response.status === 204 || response.status === 404) return null;
  const data = await parseJson<SuggestSlot | null>(response);
  return data;
}

export async function createPlan(body: {
  image_id: number;
  platform: string;
  media_format: string;
  scheduled_date?: string;
  scheduled_time?: string;
  caption?: string;
  story_schedule?: {
    mode: string;
    weekday: number;
    time_local: string;
    timezone?: string | null;
  };
}): Promise<PlanActionResponse> {
  return parseJson(
    await fetch("/api/v1/plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function reschedulePlan(
  imageId: number,
  platform: string,
  body: { scheduled_date: string; scheduled_time: string; caption?: string },
): Promise<PlanActionResponse> {
  return parseJson(
    await fetch(`/api/v1/plans/${imageId}/${platform}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function cancelPlan(imageId: number, platform: string): Promise<PlanActionResponse> {
  return parseJson(
    await fetch(`/api/v1/plans/${imageId}/${platform}`, {
      method: "DELETE",
    }),
  );
}

export async function fetchCalendar(params: {
  year: number;
  month: number;
  platform?: string;
  category?: string;
}): Promise<CalendarResponse> {
  const qs = new URLSearchParams({
    year: String(params.year),
    month: String(params.month),
  });
  if (params.platform && params.platform !== "tutti") qs.set("platform", params.platform);
  if (params.category && params.category !== "tutte") qs.set("category", params.category);
  return parseJson(await fetch(`/api/v1/calendar?${qs}`));
}

export async function fetchCalendarEvents(params: {
  allActive?: boolean;
  year?: number;
  month?: number;
  platform?: string;
}): Promise<CalendarEvent[]> {
  const qs = new URLSearchParams();
  if (params.allActive) qs.set("all_active", "true");
  if (params.year != null) qs.set("year", String(params.year));
  if (params.month != null) qs.set("month", String(params.month));
  if (params.platform && params.platform !== "tutti") qs.set("platform", params.platform);
  return parseJson(await fetch(`/api/v1/calendar/events?${qs}`));
}

export type DuePlanningEvent = {
  id: number;
  image_id: number;
  image_name: string;
  platform: string;
  event_type: string;
  scheduled_for: string;
  dispatch_gate: string;
};

export type DueStoryRule = {
  rule_id: number;
  image_id: number;
  platform: string;
  schedule_mode: string;
  occurrence_key: string;
  slot_label: string;
  scheduled_for: string;
};

export type DueEventsResponse = {
  planning_events: DuePlanningEvent[];
  story_rules: DueStoryRule[];
  planning_count: number;
  story_count: number;
};

export type DispatchRunResponse = {
  dry_run: boolean;
  message: string;
  planning_published?: number;
  planning_failed?: number;
  planning_skipped?: number;
  story_published?: number;
  story_failed?: number;
  story_skipped_reserve?: number;
  skip_reasons?: string[];
  planning_events?: DuePlanningEvent[];
  story_rules?: DueStoryRule[];
  planning_count?: number;
  story_count?: number;
};

export type PrepareWeekResponse = {
  message: string;
  dry_run: boolean;
  schedule_path: string;
  planned: number;
  processed: number;
  rendered: number;
  auto_approved: number;
  vision_evaluated: number;
  skipped_borderline: number;
  errors: string[];
  assignments: Array<Record<string, unknown>>;
};

export async function fetchDueEvents(params: {
  platform?: string;
  limit?: number;
}): Promise<DueEventsResponse> {
  const qs = new URLSearchParams({ limit: String(params.limit ?? 50) });
  if (params.platform && params.platform !== "tutti") qs.set("platform", params.platform);
  return parseJson(await fetch(`/api/v1/dispatch/due?${qs}`));
}

export async function dispatchDryRun(body: {
  platform?: string;
  limit?: number;
}): Promise<DispatchRunResponse> {
  return parseJson(
    await fetch("/api/v1/dispatch/dry-run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function dispatchRun(body: {
  platform?: string;
  limit?: number;
}): Promise<DispatchRunResponse> {
  return parseJson(
    await fetch("/api/v1/dispatch/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function prepareWeek(body: {
  days: number;
  dry_run: boolean;
  try_render: boolean;
}): Promise<PrepareWeekResponse> {
  return parseJson(
    await fetch("/api/v1/automation/prepare-week", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function fetchBatchList(params: {
  status?: string;
  platform?: string;
  format?: string;
  limit?: number;
}): Promise<BatchSummary[]> {
  const qs = new URLSearchParams({ limit: String(params.limit ?? 50) });
  if (params.status && params.status !== "tutti") qs.set("status", params.status);
  if (params.platform && params.platform !== "tutti") qs.set("platform", params.platform);
  if (params.format && params.format !== "tutti") qs.set("format", params.format);
  return parseJson(await fetch(`/api/v1/batches?${qs}`));
}
