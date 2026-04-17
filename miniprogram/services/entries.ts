import { deleteCloudFile, request, uploadAudioFile, uploadAudioFileToCloudBase } from "./api";
import { USE_CLOUDBASE_UPLOAD } from "../env";
import type {
  DailyBrief,
  EntryCreateResponse,
  HistoryResponse,
  JobResponse,
  ShareCardResponse,
  SharedBrief,
  UploadCreateResponse,
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
}): Promise<EntryCreateResponse> {
  if (USE_CLOUDBASE_UPLOAD) {
    const upload = await uploadAudioFileToCloudBase({
      filePath: params.filePath,
      localDate: params.localDate,
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

export function regenerateEntry(token: string, entryId: string): Promise<EntryCreateResponse> {
  return request<EntryCreateResponse>(`/miniapp/entries/${entryId}/regenerate`, { method: "POST", token });
}

export function createShareCard(token: string, entryId: string): Promise<ShareCardResponse> {
  return request<ShareCardResponse, { entry_id: string }>("/miniapp/share/cards", {
    method: "POST",
    token,
    data: { entry_id: entryId },
  });
}

export function getSharedBrief(shareId: string): Promise<SharedBrief> {
  return request<SharedBrief>(`/miniapp/share/cards/${shareId}`);
}

export function getHistory(token: string, skip = 0, limit = 20): Promise<HistoryResponse> {
  return request<HistoryResponse>(`/miniapp/history?skip=${skip}&limit=${limit}`, { token });
}
