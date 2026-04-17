import { API_BASE_URL, REQUEST_TIMEOUT_MS, USE_MOCK_API } from "../env";
import { mockCloudUploadAudioFile, mockRequest, mockUploadAudioFile } from "./mock";
import type { CloudUploadResponse } from "../types/api";

type RequestOptions<TBody> = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  data?: TBody;
  token?: string;
};

export function request<TResponse, TBody = unknown>(
  path: string,
  options: RequestOptions<TBody> = {},
): Promise<TResponse> {
  console.info("[brief-api]", USE_MOCK_API ? "mock" : "real", API_BASE_URL, path);

  if (USE_MOCK_API) {
    return mockRequest<TResponse, TBody>(path, options);
  }

  const headers: Record<string, string> = {
    "content-type": "application/json",
  };

  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE_URL}${path}`,
      method: options.method || "GET",
      data: options.data as WechatMiniprogram.IAnyObject | string | ArrayBuffer | undefined,
      header: headers,
      timeout: REQUEST_TIMEOUT_MS,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data as TResponse);
          return;
        }
        reject(new Error(`Request failed: ${res.statusCode}`));
      },
      fail: reject,
    });
  });
}

export function uploadAudioFile(params: {
  uploadUrl: string;
  filePath: string;
  token: string;
  formData?: Record<string, string>;
}): Promise<void> {
  if (USE_MOCK_API) {
    return mockUploadAudioFile();
  }

  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: params.uploadUrl,
      filePath: params.filePath,
      name: "file",
      header: {
        Authorization: `Bearer ${params.token}`,
      },
      formData: params.formData,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve();
          return;
        }
        reject(new Error(`Upload failed: ${res.statusCode}`));
      },
      fail: reject,
    });
  });
}

export function uploadAudioFileToCloudBase(params: {
  filePath: string;
  localDate: string;
}): Promise<CloudUploadResponse> {
  if (USE_MOCK_API) {
    return mockCloudUploadAudioFile();
  }

  const suffix = fileSuffix(params.filePath);
  const cloudPath = `raw_audio/${params.localDate}/${Date.now()}-${randomString()}${suffix}`;

  return new Promise((resolve, reject) => {
    if (!wx.cloud) {
      reject(new Error("CloudBase SDK is unavailable. Check project AppID and base library."));
      return;
    }

    console.info("[brief-cloud] upload", { cloudPath, filePath: params.filePath });
    wx.cloud.uploadFile({
      cloudPath,
      filePath: params.filePath,
      success: async (uploadRes) => {
        try {
          console.info("[brief-cloud] uploaded", { fileID: uploadRes.fileID });
          const tempUrlRes = await wx.cloud.getTempFileURL({
            fileList: [uploadRes.fileID],
          });
          console.info("[brief-cloud] temp url result", tempUrlRes.fileList);
          const item = tempUrlRes.fileList[0];
          if (!item || item.status !== 0 || !item.tempFileURL) {
            reject(new Error(item?.errMsg || "CloudBase temp file URL failed"));
            return;
          }
          resolve({
            cloud_file_id: uploadRes.fileID,
            cloud_temp_url: item.tempFileURL,
            cloud_path: cloudPath,
          });
        } catch (error) {
          console.error("[brief-cloud] temp url failed", error);
          reject(error);
        }
      },
      fail: (error) => {
        console.error("[brief-cloud] upload failed", error);
        reject(error);
      },
    });
  });
}

export function deleteCloudFile(fileID: string): Promise<void> {
  if (!fileID || USE_MOCK_API) {
    return Promise.resolve();
  }

  return wx.cloud.deleteFile({ fileList: [fileID] }).then(() => undefined);
}

function fileSuffix(filePath: string): string {
  const cleanPath = filePath.split("?")[0];
  const dotIndex = cleanPath.lastIndexOf(".");
  return dotIndex >= 0 ? cleanPath.slice(dotIndex) : ".mp3";
}

function randomString(): string {
  return Math.random().toString(36).slice(2, 10);
}
