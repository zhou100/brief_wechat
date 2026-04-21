import type { BriefApp } from "../../app";
import { RECORDING_PRESETS, startRecording, stopRecording } from "../../services/recorder";
import { submitRecordedEntry } from "../../services/entries";
import { formatDuration, todayLocalDate } from "../../utils/date";
import { userFacingError } from "../../utils/errors";

const app = getApp<BriefApp>();

Page({
  data: {
    recording: false,
    uploading: false,
    elapsedMs: 0,
    elapsedLabel: "0:00",
    statusText: "点一下开始讲",
    lastFilePath: "",
    lastDurationMs: 0,
    errorText: "",
    presetLabels: RECORDING_PRESETS.map((preset) => preset.label),
    selectedPresetIndex: 0,
    selectedPresetLabel: RECORDING_PRESETS[0].label,
    lastRecorderOptions: RECORDING_PRESETS[0],
    showPresetPicker: false,
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
      vibrate();
      this.setData({
        recording: true,
        uploading: false,
        elapsedMs: 0,
        elapsedLabel: "0:00",
        statusText: "正在听你讲",
        lastFilePath: "",
        errorText: "",
        lastRecorderOptions: options,
      });
      this.timer = Number(setInterval(() => {
        const elapsedMs = this.data.elapsedMs + 1000;
        this.setData({ elapsedMs, elapsedLabel: formatDuration(elapsedMs) });
      }, 1000));
    } catch (error) {
      this.setData({ statusText: "录音没打开，请再试一次" });
      wx.showToast({ title: "录音没打开", icon: "none" });
    }
  },

  async stop() {
    clearInterval(this.timer);
    try {
      const result = await stopRecording();
      vibrate();
      this.setData({
        recording: false,
        lastFilePath: result.tempFilePath,
        lastDurationMs: Math.max(1, Math.round(result.durationMs)),
        lastRecorderOptions: result.options,
      });
      await this.upload(result.tempFilePath, result.durationMs, result.options);
    } catch (error) {
      this.setData({ recording: false, uploading: false, statusText: "这段没录上，请再讲一遍" });
      wx.showToast({ title: "这段没录上", icon: "none" });
    }
  },

  async retryUpload() {
    if (!this.data.lastFilePath) return;
    await this.upload(this.data.lastFilePath, this.data.lastDurationMs, this.data.lastRecorderOptions);
  },

  async upload(filePath: string, durationMs: number, recorderOptions?: (typeof RECORDING_PRESETS)[number]) {
    const uploadOptions = recorderOptions || this.data.lastRecorderOptions;
    this.setData({ uploading: true, statusText: "正在先记下来" });
    wx.showLoading({ title: "正在记下来" });

    try {
      const token = await app.ensureLogin();
      const localDate = todayLocalDate();
      const entry = await submitRecordedEntry({
        token,
        filePath,
        durationMs,
        localDate,
        recorderOptions: uploadOptions,
      });
      wx.setStorageSync("brief_active_job_id", entry.job_id);
      wx.hideLoading();
      wx.redirectTo({ url: `/pages/day/day?date=${localDate}&entry_id=${entry.entry_id}` });
    } catch (error) {
      wx.hideLoading();
      const message = userFacingError(error, "这段没传上去，请再试一次。");
      console.error("[brief-record] upload failed", error);
      this.setData({
        uploading: false,
        statusText: "这段没传上去，可重试",
        errorText: message,
      });
      wx.showToast({ title: "没传上去", icon: "none" });
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

function vibrate() {
  try {
    wx.vibrateShort({ type: "light" });
  } catch (error) {
    console.warn("[brief-record] vibrate unavailable", error);
  }
}
