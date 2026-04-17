import type { BriefApp } from "../../app";
import { startRecording, stopRecording } from "../../services/recorder";
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
  },

  timer: 0 as number,

  async start() {
    try {
      await app.ensureLogin();
      await startRecording();
      this.setData({
        recording: true,
        uploading: false,
        elapsedMs: 0,
        elapsedLabel: "0:00",
        statusText: "正在录音",
        lastFilePath: "",
        errorText: "",
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
      });
      await this.upload(result.tempFilePath, result.durationMs);
    } catch (error) {
      this.setData({ recording: false, uploading: false, statusText: "录音中断，请重试" });
      wx.showToast({ title: "录音中断", icon: "none" });
    }
  },

  async retryUpload() {
    if (!this.data.lastFilePath) return;
    await this.upload(this.data.lastFilePath, this.data.lastDurationMs);
  },

  async upload(filePath: string, durationMs: number) {
    this.setData({ uploading: true, statusText: "正在上传" });
    wx.showLoading({ title: "上传中" });

    try {
      const token = await app.ensureLogin();
      const entry = await submitRecordedEntry({
        token,
        filePath,
        durationMs,
        localDate: todayLocalDate(),
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
