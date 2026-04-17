const recorder = wx.getRecorderManager();

export type RecordingResult = {
  tempFilePath: string;
  durationMs: number;
};

let startedAt = 0;

export function startRecording(): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.authorize({
      scope: "scope.record",
      success: () => {
        startedAt = Date.now();
        recorder.start({
          duration: 10 * 60 * 1000,
          sampleRate: 16000,
          numberOfChannels: 1,
          encodeBitRate: 48000,
          format: "mp3",
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
      });
    });
    recorder.onError((err) => reject(err));
    recorder.stop();
  });
}
