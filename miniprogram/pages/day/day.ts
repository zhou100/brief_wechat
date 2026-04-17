import type { BriefApp } from "../../app";
import {
  createShareCard,
  deleteEntry,
  getDailyBrief,
  getEntryResult,
  regenerateEntry,
} from "../../services/entries";
import type { ShareCard } from "../../types/api";
import { todayLocalDate } from "../../utils/date";

const app = getApp<BriefApp>();

Page({
  data: {
    entryId: "",
    date: "",
    createdAt: "",
    summary: "",
    keyPoints: [] as string[],
    openLoops: [] as string[],
    shareCard: null as ShareCard | null,
  },

  onLoad(query: Record<string, string | undefined>) {
    const entryId = query.entry_id || "";
    const date = query.date || todayLocalDate();
    this.setData({ entryId, date });
    this.load(entryId, date);
  },

  async load(entryId: string, date: string) {
    try {
      const token = await app.ensureLogin();
      const result = entryId ? await getEntryResult(token, entryId) : await getDailyBrief(token, date);
      this.setData({
        entryId: result.entry_id,
        createdAt: result.created_at,
        summary: result.summary,
        keyPoints: result.key_points || [],
        openLoops: result.open_loops || [],
        shareCard: result.share_card || null,
      });
      if (!result.share_card) {
        this.prepareShare(false);
      }
    } catch (error) {
      wx.showToast({ title: "结果暂不可用", icon: "none" });
    }
  },

  async prepareShare(showError = true) {
    if (!this.data.entryId) return;
    try {
      const token = await app.ensureLogin();
      const response = await createShareCard(token, this.data.entryId);
      this.setData({ shareCard: response.card });
    } catch (error) {
      if (showError) {
        wx.showToast({ title: "分享卡片生成失败", icon: "none" });
      }
    }
  },

  async regenerate() {
    if (!this.data.entryId) return;
    wx.showLoading({ title: "重新生成" });
    try {
      const token = await app.ensureLogin();
      const response = await regenerateEntry(token, this.data.entryId);
      wx.setStorageSync("brief_active_job_id", response.job_id);
      wx.hideLoading();
      wx.redirectTo({ url: `/pages/job/job?job_id=${response.job_id}` });
    } catch (error) {
      wx.hideLoading();
      wx.showToast({ title: "重新生成失败", icon: "none" });
    }
  },

  deleteCurrent() {
    if (!this.data.entryId) return;
    wx.showModal({
      title: "删除这条内容？",
      content: "删除后音频、文本和总结都会从你的记录中移除。",
      confirmText: "删除",
      success: async (res) => {
        if (!res.confirm) return;
        try {
          const token = await app.ensureLogin();
          await deleteEntry(token, this.data.entryId);
          wx.showToast({ title: "已删除", icon: "success" });
          wx.reLaunch({ url: "/pages/index/index" });
        } catch (error) {
          wx.showToast({ title: "删除失败", icon: "none" });
        }
      },
    });
  },

  recordMore() {
    wx.navigateTo({ url: "/pages/record/record" });
  },

  onShareAppMessage() {
    const card = this.data.shareCard;
    const shareId = card?.share_id || "";
    return {
      title: card?.title || "我的 Brief 摘要",
      path: shareId
        ? `/pkg_history/pages/share/share?share_id=${shareId}`
        : "/pages/index/index",
      imageUrl: card?.image_url,
    };
  },
});
