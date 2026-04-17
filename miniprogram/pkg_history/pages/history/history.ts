import type { BriefApp } from "../../../app";
import { getHistory } from "../../../services/entries";
import type { HistoryItem } from "../../../types/api";

const app = getApp<BriefApp>();

Page({
  data: {
    items: [] as HistoryItem[],
  },

  onShow() {
    this.load();
  },

  async load() {
    try {
      const token = await app.ensureLogin();
      const history = await getHistory(token);
      this.setData({ items: history.items });
    } catch (error) {
      wx.showToast({ title: "历史暂不可用", icon: "none" });
    }
  },

  openEntry(event: WechatMiniprogram.TouchEvent) {
    const id = event.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pkg_history/pages/entry/entry?id=${id}` });
  },
});
