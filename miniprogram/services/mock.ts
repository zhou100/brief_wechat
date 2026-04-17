import type {
  DailyBrief,
  EntryCreateResponse,
  HistoryResponse,
  JobResponse,
  LoginResponse,
  ShareCardResponse,
  SharedBrief,
  UploadCreateResponse,
} from "../types/api";

let pollCount = 0;
let lastEntryId = "mock-entry-1";

export function mockRequest<TResponse, TBody = unknown>(
  path: string,
  options: { method?: string; data?: TBody } = {},
): Promise<TResponse> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(route<TResponse, TBody>(path, options)), 400);
  });
}

export function mockUploadAudioFile(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 500));
}

function route<TResponse, TBody>(
  path: string,
  options: { method?: string; data?: TBody },
): TResponse {
  if (path === "/miniapp/auth/login") {
    return {
      token: "mock-token",
      user: { id: "mock-user", display_name: "Brief Tester" },
    } satisfies LoginResponse as TResponse;
  }

  if (path === "/miniapp/uploads/create") {
    return {
      upload_api_url: "mock://upload/audio",
      object_key: `raw_audio/mock-user/${Date.now()}.mp3`,
    } satisfies UploadCreateResponse as TResponse;
  }

  if (path === "/miniapp/entries" && options.method === "POST") {
    pollCount = 0;
    lastEntryId = `mock-entry-${Date.now()}`;
    return {
      entry_id: lastEntryId,
      job_id: "mock-job-1",
    } satisfies EntryCreateResponse as TResponse;
  }

  if (path.startsWith("/miniapp/jobs/")) {
    pollCount += 1;
    return {
      job_id: "mock-job-1",
      entry_id: lastEntryId,
      status: pollCount >= 8 ? "done" : "processing",
      progress: pollCount >= 8 ? 100 : Math.min(90, 20 + pollCount * 9),
      step: pollCount >= 8 ? "整理完成" : "正在整理你的内容",
      result_preview: {
        summary: "今天的重点已经整理成一张 Brief。",
      },
    } satisfies JobResponse as TResponse;
  }

  if (path.endsWith("/result") || path.startsWith("/miniapp/daily/")) {
    return mockBrief() as TResponse;
  }

  if (path.endsWith("/regenerate")) {
    pollCount = 0;
    return {
      entry_id: lastEntryId,
      job_id: "mock-job-regenerate",
    } satisfies EntryCreateResponse as TResponse;
  }

  if (path === "/miniapp/share/cards") {
    return {
      card: {
        share_id: "mock-share-1",
        title: "我的 Brief 摘要",
        summary: "今天的重点已经整理成一张 Brief。",
        open_loop_count: 2,
      },
    } satisfies ShareCardResponse as TResponse;
  }

  if (path.startsWith("/miniapp/share/cards/")) {
    return {
      share_id: "mock-share-1",
      summary: "今天的重点已经整理成一张 Brief。",
      open_loop_count: 2,
      created_at: new Date().toISOString(),
    } satisfies SharedBrief as TResponse;
  }

  if (path.startsWith("/miniapp/history")) {
    return {
      items: [],
      total: 0,
      skip: 0,
      limit: 20,
    } satisfies HistoryResponse as TResponse;
  }

  return undefined as TResponse;
}

function mockBrief(): DailyBrief {
  return {
    entry_id: lastEntryId,
    result_id: "mock-result-1",
    created_at: new Date().toISOString(),
    summary: "今天的重点是把微信小程序的最小录音闭环跑起来。",
    key_points: [
      "小程序已经可以进入录音、上传、处理和结果页面。",
      "后端需要补齐 /miniapp/* BFF 接口。",
      "分享只暴露摘要卡片，不暴露完整内容。",
    ],
    open_loops: [
      "接入真实微信登录 code 换 token。",
      "把上传入口接到后端存储。",
    ],
  };
}
