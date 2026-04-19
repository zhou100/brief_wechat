const recorder = wx.getRecorderManager();
type RecorderStopHandler = Parameters<typeof recorder.onStop>[0];
type RecorderErrorHandler = Parameters<typeof recorder.onError>[0];

type RecorderWithOff = WechatMiniprogram.RecorderManager & {
  offStop?: (callback?: RecorderStopHandler) => void;
  offError?: (callback?: RecorderErrorHandler) => void;
};

export type RecordingResult = {
  tempFilePath: string;
  durationMs: number;
  options: RecordingOptions;
};

export type RecordingFormat = "mp3" | "aac";

export type RecordingOptions = {
  format: RecordingFormat;
  sampleRate: 16000 | 44100;
  encodeBitRate: number;
  label: string;
};

export const RECORDING_PRESETS: RecordingOptions[] = [
  { label: "MP3 16k", format: "mp3", sampleRate: 16000, encodeBitRate: 48000 },
  { label: "MP3 44.1k", format: "mp3", sampleRate: 44100, encodeBitRate: 96000 },
  { label: "AAC 16k", format: "aac", sampleRate: 16000, encodeBitRate: 48000 },
  { label: "AAC 44.1k", format: "aac", sampleRate: 44100, encodeBitRate: 96000 },
];

let startedAt = 0;
let activeOptions = RECORDING_PRESETS[0];
let pendingStop:
  | {
      resolve: (result: RecordingResult) => void;
      reject: (error: WechatMiniprogram.GeneralCallbackResult) => void;
    }
  | null = null;

export function startRecording(options: RecordingOptions = RECORDING_PRESETS[0]): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.authorize({
      scope: "scope.record",
      success: () => {
        activeOptions = options;
        startedAt = Date.now();
        recorder.start({
          duration: 10 * 60 * 1000,
          sampleRate: options.sampleRate,
          numberOfChannels: 1,
          encodeBitRate: options.encodeBitRate,
          format: options.format,
        });
        resolve();
      },
      fail: reject,
    });
  });
}

export function stopRecording(): Promise<RecordingResult> {
  if (pendingStop) {
    return Promise.reject(new Error("Recording is already stopping"));
  }
  cleanupStopListeners();
  return new Promise((resolve, reject) => {
    const handleStop: RecorderStopHandler = (res) => {
      if (!pendingStop) return;
      const current = pendingStop;
      pendingStop = null;
      cleanupStopListeners(handleStop, handleError);
      current.resolve({
        tempFilePath: res.tempFilePath,
        durationMs: res.duration || Date.now() - startedAt,
        options: activeOptions,
      });
    };
    const handleError: RecorderErrorHandler = (err) => {
      if (!pendingStop) return;
      const current = pendingStop;
      pendingStop = null;
      cleanupStopListeners(handleStop, handleError);
      current.reject(err);
    };

    pendingStop = { resolve, reject };
    recorder.onStop(handleStop);
    recorder.onError(handleError);
    recorder.stop();
  });
}

function cleanupStopListeners(
  stopHandler?: RecorderStopHandler,
  errorHandler?: RecorderErrorHandler,
): void {
  const manager = recorder as RecorderWithOff;
  try {
    manager.offStop?.(stopHandler);
    manager.offError?.(errorHandler);
  } catch (error) {
    console.warn("[brief-recorder] listener cleanup skipped", error);
  }
}
