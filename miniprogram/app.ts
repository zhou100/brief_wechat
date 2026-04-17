import { loginWithWechatCode } from "./services/auth";
import type { MiniappUser } from "./types/api";

type GlobalData = {
  token: string | null;
  user: MiniappUser | null;
};

App({
  globalData: {
    token: null,
    user: null,
  } as GlobalData,

  onLaunch() {
    const token = wx.getStorageSync("brief_token") as string | undefined;
    const user = wx.getStorageSync("brief_user") as MiniappUser | undefined;
    this.globalData.token = token || null;
    this.globalData.user = user || null;
  },

  async ensureLogin(): Promise<string> {
    if (this.globalData.token) {
      return this.globalData.token;
    }

    const { code } = await wx.login();
    const session = await loginWithWechatCode(code);
    this.globalData.token = session.token;
    this.globalData.user = session.user;
    wx.setStorageSync("brief_token", session.token);
    wx.setStorageSync("brief_user", session.user);
    return session.token;
  },

  clearSession() {
    this.globalData.token = null;
    this.globalData.user = null;
    wx.removeStorageSync("brief_token");
    wx.removeStorageSync("brief_user");
  },
});

export type BriefApp = WechatMiniprogram.App.Instance<{
  globalData: GlobalData;
  ensureLogin(): Promise<string>;
  clearSession(): void;
}>;
