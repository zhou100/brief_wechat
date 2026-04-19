import type { BriefApp } from "../../app";
import { JOB_POLL_INTERVAL_MS } from "../../env";
import { getJob } from "../../services/entries";
import { todayLocalDate } from "../../utils/date";
import { jobErrorText } from "../../utils/errors";

const app = getApp<BriefApp>();

Page({
  data: {
    jobId: "",
    progress: 12,
    stepText: "正在准备",
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
        stepText: statusText(job.status, job.step, job.progress),
        preview: job.result_preview?.summary || "",
        failed: job.status === "failed",
        errorMessage: job.status === "failed" ? jobErrorText(job.error_code, job.error_message) : "",
      });

      if (job.status === "done" && job.entry_id) {
        clearInterval(this.pollTimer);
        wx.removeStorageSync("brief_active_job_id");
        wx.redirectTo({ url: `/pages/day/day?date=${job.local_date || todayLocalDate()}&entry_id=${job.entry_id}` });
      }

      if (job.status === "failed") {
        clearInterval(this.pollTimer);
        wx.showToast({ title: "这段没听清", icon: "none" });
      }
    } catch (error) {
      this.setData({ stepText: "网络有点慢，正在继续整理。" });
    }
  },

  goRecord() {
    wx.redirectTo({ url: "/pages/day/day" });
  },

  goHome() {
    if (this.data.jobId && !this.data.failed) {
      wx.setStorageSync("brief_active_job_id", this.data.jobId);
    }
    wx.redirectTo({ url: "/pages/day/day" });
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

function statusText(status: string, step?: string, progress = 0): string {
  if (status === "done") return "整理好了";
  if (status === "failed") return "回到今天再处理";
  if (status === "processing") {
    if (step?.includes("summar")) return "正在帮你理清爽";
    if (progress >= 75) return "快好了";
    return "正在听懂你讲的话";
  }
  return "正在准备";
}
