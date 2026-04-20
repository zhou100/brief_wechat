import { deleteCloudFile, request, uploadAudioFile, uploadAudioFileToCloudBase } from "./api";
import { RECLASSIFY_TIMEOUT_MS, USE_CLOUDBASE_UPLOAD } from "../env";
import type {
  DailyBrief,
  EntryCreateResponse,
  HistoryResponse,
  JobResponse,
  ShareCardResponse,
  SharedBrief,
  UploadCreateResponse,
  WeeklySuggestion,
  WeeklySummary,
} from "../types/api";

export async function createUpload(params: {
  token: string;
  fileName: string;
  fileSize?: number;
  mimeType: string;
  durationMs: number;
}): Promise<UploadCreateResponse> {
  return request<UploadCreateResponse, Omit<typeof params, "token">>("/miniapp/uploads/create", {
    method: "POST",
    token: params.token,
    data: {
      fileName: params.fileName,
      fileSize: params.fileSize,
      mimeType: params.mimeType,
      durationMs: params.durationMs,
    },
  });
}

export async function submitRecordedEntry(params: {
  token: string;
  filePath: string;
  durationMs: number;
  localDate: string;
  recorderOptions?: {
    format: "mp3" | "aac";
    sampleRate: number;
    encodeBitRate: number;
    label: string;
  };
}): Promise<EntryCreateResponse> {
  if (USE_CLOUDBASE_UPLOAD) {
    const upload = await uploadAudioFileToCloudBase({
      filePath: params.filePath,
      localDate: params.localDate,
      suffix: params.recorderOptions ? `.${params.recorderOptions.format}` : undefined,
    });

    return request<EntryCreateResponse, {
      cloud_file_id: string;
      cloud_temp_url: string;
      duration_ms: number;
      local_date: string;
      client_meta: object;
    }>("/miniapp/entries", {
      method: "POST",
      token: params.token,
      data: {
        cloud_file_id: upload.cloud_file_id,
        cloud_temp_url: upload.cloud_temp_url,
        duration_ms: Math.max(1, Math.round(params.durationMs)),
        local_date: params.localDate,
        client_meta: {
          source: "wechat-miniapp",
          recorder: "wx.getRecorderManager",
          storage: "cloudbase",
          cloud_path: upload.cloud_path,
          recorder_options: params.recorderOptions || null,
        },
      },
    });
  }

  const upload = await createUpload({
    token: params.token,
    fileName: `recording-${Date.now()}.mp3`,
    mimeType: "audio/mpeg",
    durationMs: params.durationMs,
  });

  await uploadAudioFile({
    uploadUrl: upload.upload_api_url,
    filePath: params.filePath,
    token: params.token,
  });

  return request<EntryCreateResponse, { object_key: string; duration_ms: number; local_date: string; client_meta: object }>(
    "/miniapp/entries",
    {
      method: "POST",
      token: params.token,
      data: {
        object_key: upload.object_key,
        duration_ms: Math.max(1, Math.round(params.durationMs)),
        local_date: params.localDate,
        client_meta: {
          source: "wechat-miniapp",
          recorder: "wx.getRecorderManager",
          recorder_options: params.recorderOptions || null,
        },
      },
    },
  );
}

export function getJob(token: string, jobId: string): Promise<JobResponse> {
  return request<JobResponse>(`/miniapp/jobs/${jobId}`, { token });
}

export function getDailyBrief(token: string, date: string): Promise<DailyBrief> {
  return request<DailyBrief>(`/miniapp/daily/${date}`, { token });
}

export function getEntryResult(token: string, entryId: string): Promise<DailyBrief> {
  return request<DailyBrief>(`/miniapp/entries/${entryId}/result`, { token });
}

export function deleteEntry(token: string, entryId: string): Promise<void> {
  return request<void>(`/miniapp/entries/${entryId}`, { method: "DELETE", token });
}

export { deleteCloudFile };

export function updateItemText(token: string, itemId: string, text: string): Promise<void> {
  return request<void, { edited_text: string }>(`/miniapp/items/${itemId}`, {
    method: "POST",
    token,
    data: { edited_text: text },
  });
}

export function deleteItem(token: string, itemId: string): Promise<void> {
  return request<void>(`/miniapp/items/${itemId}`, { method: "DELETE", token });
}

export function regenerateEntry(token: string, entryId: string): Promise<EntryCreateResponse> {
  return request<EntryCreateResponse>(`/miniapp/entries/${entryId}/regenerate`, { method: "POST", token });
}

export function createShareCard(token: string, params: { entryId?: string; date?: string }): Promise<ShareCardResponse> {
  return request<ShareCardResponse, { entry_id?: string; date?: string }>("/miniapp/share/cards", {
    method: "POST",
    token,
    data: {
      entry_id: params.entryId,
      date: params.date,
    },
  });
}

export function getSharedBrief(shareId: string): Promise<SharedBrief> {
  return request<SharedBrief>(`/miniapp/share/cards/${shareId}`);
}

export function getHistory(token: string, skip = 0, limit = 20): Promise<HistoryResponse> {
  return request<HistoryResponse>(`/miniapp/history?skip=${skip}&limit=${limit}`, { token });
}

export function getWeeklySuggestion(token: string, weekStart: string): Promise<WeeklySuggestion> {
  return request<WeeklySuggestion>(`/miniapp/weekly/suggestion?week_start=${weekStart}`, { token });
}

export function getWeeklySummary(token: string, weekStart: string): Promise<WeeklySummary> {
  return request<WeeklySummary>(`/miniapp/weekly/${weekStart}`, { token });
}

export function createWeeklySummary(token: string, weekStart: string): Promise<WeeklySummary> {
  return request<WeeklySummary, { week_start: string }>("/miniapp/weekly", {
    method: "POST",
    token,
    data: { week_start: weekStart },
  });
}

export function reclassifyDay(token: string, date: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/miniapp/daily/${date}/reclassify`, {
    method: "POST",
    token,
    timeoutMs: RECLASSIFY_TIMEOUT_MS,
  });
}

export function regenWeeklySummary(token: string, weekStart: string): Promise<WeeklySummary> {
  return request<WeeklySummary, { week_start: string; force: boolean }>("/miniapp/weekly", {
    method: "POST",
    token,
    data: { week_start: weekStart, force: true },
  });
}
