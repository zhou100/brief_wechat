const recorder = wx.getRecorderManager();

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
  return new Promise((resolve, reject) => {
    recorder.onStop((res) => {
      resolve({
        tempFilePath: res.tempFilePath,
        durationMs: res.duration || Date.now() - startedAt,
        options: activeOptions,
      });
    });
    recorder.onError((err) => reject(err));
    recorder.stop();
  });
}
