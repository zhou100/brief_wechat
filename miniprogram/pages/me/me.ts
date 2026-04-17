import type { BriefApp } from "../../app";

const app = getApp<BriefApp>();

Page({
  data: {
    userLabel: "未登录",
  },

  onShow() {
    const user = app.globalData.user;
    this.setData({ userLabel: user?.display_name || user?.id || "未登录" });
  },

  openSettings() {
    wx.navigateTo({ url: "/pkg_settings/pages/settings/settings" });
  },

  openPrivacy() {
    wx.navigateTo({ url: "/pkg_settings/pages/privacy/privacy" });
  },

  logout() {
    app.clearSession();
    this.setData({ userLabel: "未登录" });
  },
});
