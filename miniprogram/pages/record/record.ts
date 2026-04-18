import type { BriefApp } from "../../app";
import { RECORDING_PRESETS, startRecording, stopRecording } from "../../services/recorder";
import { submitRecordedEntry } from "../../services/entries";
import { formatDuration, todayLocalDate } from "../../utils/date";

const app = getApp<BriefApp>();

Page({
  data: {
    recording: false,
    uploading: false,
    elapsedMs: 0,
    elapsedLabel: "0:00",
    statusText: "准备开始",
    lastFilePath: "",
    lastDurationMs: 0,
    errorText: "",
    presetLabels: RECORDING_PRESETS.map((preset) => preset.label),
    selectedPresetIndex: 0,
    selectedPresetLabel: RECORDING_PRESETS[0].label,
    lastRecorderOptions: RECORDING_PRESETS[0],
  },

  timer: 0 as number,

  onLoad() {
    const storedIndex = Number(wx.getStorageSync("brief_record_preset_index") || 0);
    const selectedPresetIndex = RECORDING_PRESETS[storedIndex] ? storedIndex : 0;
    this.setPreset(selectedPresetIndex);
  },

  changePreset(event: WechatMiniprogram.PickerChange) {
    this.setPreset(Number(event.detail.value || 0));
  },

  async start() {
    try {
      await app.ensureLogin();
      const options = RECORDING_PRESETS[this.data.selectedPresetIndex] || RECORDING_PRESETS[0];
      await startRecording(options);
      this.setData({
        recording: true,
        uploading: false,
        elapsedMs: 0,
        elapsedLabel: "0:00",
        statusText: "正在录音",
        lastFilePath: "",
        errorText: "",
        lastRecorderOptions: options,
      });
      this.timer = Number(setInterval(() => {
        const elapsedMs = this.data.elapsedMs + 1000;
        this.setData({ elapsedMs, elapsedLabel: formatDuration(elapsedMs) });
      }, 1000));
    } catch (error) {
      this.setData({ statusText: "录音不可用" });
      wx.showToast({ title: "无法使用录音", icon: "none" });
    }
  },

  async stop() {
    clearInterval(this.timer);
    try {
      const result = await stopRecording();
      this.setData({
        recording: false,
        lastFilePath: result.tempFilePath,
        lastDurationMs: Math.max(1, Math.round(result.durationMs)),
        lastRecorderOptions: result.options,
      });
      await this.upload(result.tempFilePath, result.durationMs, result.options);
    } catch (error) {
      this.setData({ recording: false, uploading: false, statusText: "录音中断，请重试" });
      wx.showToast({ title: "录音中断", icon: "none" });
    }
  },

  async retryUpload() {
    if (!this.data.lastFilePath) return;
    await this.upload(this.data.lastFilePath, this.data.lastDurationMs, this.data.lastRecorderOptions);
  },

  async upload(filePath: string, durationMs: number, recorderOptions?: (typeof RECORDING_PRESETS)[number]) {
    const uploadOptions = recorderOptions || this.data.lastRecorderOptions;
    this.setData({ uploading: true, statusText: "正在上传" });
    wx.showLoading({ title: "上传中" });

    try {
      const token = await app.ensureLogin();
      const entry = await submitRecordedEntry({
        token,
        filePath,
        durationMs,
        localDate: todayLocalDate(),
        recorderOptions: uploadOptions,
      });
      wx.setStorageSync("brief_active_job_id", entry.job_id);
      wx.hideLoading();
      wx.redirectTo({ url: `/pages/job/job?job_id=${entry.job_id}` });
    } catch (error) {
      wx.hideLoading();
      const message = readableError(error);
      console.error("[brief-record] upload failed", error);
      this.setData({
        uploading: false,
        statusText: "上传失败，可重试",
        errorText: message,
      });
      wx.showToast({ title: "上传失败", icon: "none" });
    }
  },

  onUnload() {
    clearInterval(this.timer);
  },

  setPreset(index: number) {
    const preset = RECORDING_PRESETS[index] || RECORDING_PRESETS[0];
    wx.setStorageSync("brief_record_preset_index", index);
    this.setData({
      selectedPresetIndex: index,
      selectedPresetLabel: preset.label,
      lastRecorderOptions: preset,
    });
  },
});

function readableError(error: unknown): string {
  if (!error) return "未知错误，请查看真机调试 Console。";
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string") return error;
  const maybe = error as { errMsg?: string; message?: string };
  if (maybe.errMsg) return maybe.errMsg;
  if (maybe.message) return maybe.message;
  try {
    return JSON.stringify(error);
  } catch {
    return "未知错误，请查看真机调试 Console。";
  }
}
