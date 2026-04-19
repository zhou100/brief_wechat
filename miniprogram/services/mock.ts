import type {
  DailyBrief,
  EntryCreateResponse,
  HistoryResponse,
  JobResponse,
  LoginResponse,
  ShareCardResponse,
  SharedBrief,
  UploadCreateResponse,
  CloudUploadResponse,
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

export function mockCloudUploadAudioFile(): Promise<CloudUploadResponse> {
  return new Promise((resolve) => {
    setTimeout(() => resolve({
      cloud_file_id: `cloud://mock-env/mock-bucket/raw_audio/mock/${Date.now()}.mp3`,
      cloud_temp_url: "https://example.com/mock-audio.mp3",
      cloud_path: `raw_audio/mock/${Date.now()}.mp3`,
    }), 500);
  });
}

function route<TResponse, TBody>(
  path: string,
  options: { method?: string; data?: TBody },
): TResponse {
  if (path === "/miniapp/auth/login") {
    return {
      token: "mock-token",
      user: { id: "mock-user", display_name: "清爽测试用户" },
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
      local_date: new Date().toISOString().slice(0, 10),
      status: pollCount >= 8 ? "done" : "processing",
      progress: pollCount >= 8 ? 100 : Math.min(90, 20 + pollCount * 9),
      step: pollCount >= 8 ? "整理完成" : "正在整理你的内容",
      result_preview: {
        summary: "今天的重点已经整理清爽了。",
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
        title: "今天已经整理清爽了",
        summary: "今天的重点已经整理清爽了。",
        open_loop_count: 2,
      },
    } satisfies ShareCardResponse as TResponse;
  }

  if (path.startsWith("/miniapp/share/cards/")) {
    return {
      share_id: "mock-share-1",
      summary: "今天的重点已经整理清爽了。",
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
  const createdAt = new Date().toISOString();
  return {
    entry_id: lastEntryId,
    result_id: "mock-result-1",
    cloud_file_id: "cloud://mock-env/mock-bucket/raw_audio/mock/latest.mp3",
    date: new Date().toISOString().slice(0, 10),
    created_at: createdAt,
    summary: "今天主要讲了这些事。",
    key_points: [
      "微信小程序录音、上传、处理和结果页面已经跑通。",
      "默认录音格式固定为 MP3 16k。",
      "结果页应该按一天来整理，不只看单段录音。",
      "早上买菜、汰菜、烧了两个菜。",
    ],
    open_loops: [
      "把结果页改成今日清爽。",
      "把分类逻辑展示出来。",
    ],
    entries: [
      {
        id: lastEntryId,
        transcript: "今天小程序跑通了，但是结果页太像单条摘要。",
        local_date: new Date().toISOString().slice(0, 10),
        created_at: createdAt,
        duration_seconds: 18,
        categories: [
          { text: "微信小程序录音上传处理结果页面已经跑通", category: "EARNING" },
          { text: "结果页太像单条摘要，需要改成今日整理", category: "REFLECTION" },
          { text: "早上买菜、汰菜、烧了两个菜", category: "MAITAISHAO" },
        ],
      },
    ],
    category_groups: [
      {
        category: "EARNING",
        label: "办事体",
        items: [
          { text: "微信小程序录音、上传、处理和结果页面已经跑通", category: "EARNING" },
        ],
      },
      {
        category: "MAITAISHAO",
        label: "买汰烧",
        items: [
          { text: "早上买菜、汰菜、烧了两个菜", category: "MAITAISHAO" },
        ],
      },
      {
        category: "TODO",
        label: "还要做",
        items: [
          { text: "把结果页改成今日清爽", category: "TODO" },
          { text: "把分类逻辑展示出来", category: "TODO" },
        ],
      },
      {
        category: "REFLECTION",
        label: "感悟",
        items: [
          { text: "单条录音摘要太单薄，应该按每天累积", category: "REFLECTION" },
        ],
      },
    ],
  };
}
