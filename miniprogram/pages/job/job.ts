import type { BriefApp } from "../../app";
import { JOB_POLL_INTERVAL_MS } from "../../env";
import { getJob } from "../../services/entries";

const app = getApp<BriefApp>();

Page({
  data: {
    jobId: "",
    progress: 12,
    stepText: "排队中",
    preview: "",
    failed: false,
    errorMessage: "",
  },

  pollTimer: 0 as number,

  onLoad(query: Record<string, string | undefined>) {
    const jobId = query.job_id || "";
    this.setData({ jobId });
    if (jobId) {
      wx.setStorageSync("brief_active_job_id", jobId);
    }
    this.poll();
    this.pollTimer = Number(setInterval(() => this.poll(), JOB_POLL_INTERVAL_MS));
  },

  async poll() {
    if (!this.data.jobId) return;
    try {
      const token = await app.ensureLogin();
      const job = await getJob(token, this.data.jobId);
      this.setData({
        progress: job.progress || (job.status === "done" ? 100 : 45),
        stepText: job.step || statusText(job.status),
        preview: job.result_preview?.summary || "",
        failed: job.status === "failed",
        errorMessage: job.error_message || errorCodeText(job.error_code),
      });

      if (job.status === "done" && job.entry_id) {
        clearInterval(this.pollTimer);
        wx.removeStorageSync("brief_active_job_id");
        wx.redirectTo({ url: `/pages/day/day?entry_id=${job.entry_id}` });
      }

      if (job.status === "failed") {
        clearInterval(this.pollTimer);
        wx.showToast({ title: "处理失败", icon: "none" });
      }
    } catch (error) {
      this.setData({ stepText: "网络不稳定，正在重试" });
    }
  },

  goRecord() {
    wx.redirectTo({ url: "/pages/record/record" });
  },

  goHome() {
    if (this.data.jobId && !this.data.failed) {
      wx.setStorageSync("brief_active_job_id", this.data.jobId);
    }
    wx.reLaunch({ url: "/pages/index/index" });
  },

  onHide() {
    if (this.data.jobId && !this.data.failed && this.data.progress < 100) {
      wx.setStorageSync("brief_active_job_id", this.data.jobId);
    }
  },

  onUnload() {
    clearInterval(this.pollTimer);
  },
});

function statusText(status: string): string {
  if (status === "processing") return "转写和总结中";
  if (status === "done") return "已完成";
  if (status === "failed") return "处理失败";
  return "排队中";
}

function errorCodeText(code?: string): string {
  if (code === "audio_download_failed") return "音频下载失败，请重新录音再试。";
  if (code === "transcription_failed") return "语音转写失败，请用真机录音再试，或检查后端 OpenAI 配置。";
  if (code === "job_failed") return "处理失败，请查看 CloudBase 服务日志。";
  return code ? `处理失败：${code}` : "";
}
