import { API_BASE_URL, REQUEST_TIMEOUT_MS, USE_MOCK_API } from "../env";
import { mockRequest, mockUploadAudioFile } from "./mock";

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
