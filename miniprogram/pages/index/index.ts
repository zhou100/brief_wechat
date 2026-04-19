import type { BriefApp } from "../../app";
import { userFacingError } from "../../utils/errors";

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
      wx.showToast({ title: userFacingError(error, "暂时进不去，请再试一次"), icon: "none" });
    }
  },

  resumeJob() {
    wx.navigateTo({ url: `/pages/job/job?job_id=${this.data.activeJobId}` });
  },
});
