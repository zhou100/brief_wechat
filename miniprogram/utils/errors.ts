export function userFacingError(error: unknown, fallback = "出了点小问题，请再试一次。"): string {
  const raw = errorText(error);
  if (!raw) return fallback;

  if (raw.includes("401") || raw.includes("credentials") || raw.includes("Unauthorized")) {
    return "登录过期了，请再试一次。";
  }
  if (raw.includes("503") || raw.includes("Service Temporarily Unavailable")) {
    return "服务正在启动，请稍后再试。";
  }
  if (raw.includes("timeout") || raw.includes("timed out")) {
    return "网络有点慢，请重试一次。";
  }
  if (raw.includes("upload") || raw.includes("INVALID_HOST")) {
    return "这段没传上去，请再试一次。";
  }
  if (raw.includes("xfyun") || raw.includes("transcription") || raw.includes("audioCoding")) {
    return "这段没听清，请再讲一遍。";
  }
  if (raw.includes("audio_convert") || raw.includes("format")) {
    return "这段录音格式不太对，请重新录一段。";
  }

  return fallback;
}

export function jobErrorText(code?: string, message?: string): string {
  const combined = [code, message].filter(Boolean).join(" ");

  if (!combined) return "";
  if (combined.includes("audio_download")) return "这段没传完整，请重新讲一段。";
  if (combined.includes("transcription") || combined.includes("xfyun")) return "这段没听清，请再讲一遍。";
  if (combined.includes("audio_convert")) return "这段录音格式不太对，请重新录一段。";
  if (combined.includes("stale_job")) return "整理中断了，请重新讲一段。";
  if (combined.includes("entry_not_found")) return "没有找到这条记录，请重新讲一段。";

  return "这段没有整理好，请再讲一遍。";
}

function errorText(error: unknown): string {
  if (!error) return "";
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;

  const maybe = error as { errMsg?: string; message?: string; data?: unknown };
  if (maybe.errMsg) return maybe.errMsg;
  if (maybe.message) return maybe.message;

  try {
    return JSON.stringify(error);
  } catch {
    return "";
  }
}
