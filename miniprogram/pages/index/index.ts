import type { BriefApp } from "../../app";

const app = getApp<BriefApp>();

Page({
  data: {
    activeJobId: "",
  },

  onShow() {
    this.setData({ activeJobId: wx.getStorageSync("brief_active_job_id") || "" });
  },

  async startRecord() {
    try {
      await app.ensureLogin();
      wx.navigateTo({ url: "/pages/record/record" });
    } catch (error) {
      wx.showToast({ title: "登录失败", icon: "none" });
    }
  },

  resumeJob() {
    wx.navigateTo({ url: `/pages/job/job?job_id=${this.data.activeJobId}` });
  },
});
