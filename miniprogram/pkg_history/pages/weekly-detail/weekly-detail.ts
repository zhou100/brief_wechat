import type { BriefApp } from "../../../app";
import { createWeeklySummary, getWeeklySummary, regenWeeklySummary } from "../../../services/entries";
import type { WeeklySummary } from "../../../types/api";

const app = getApp<BriefApp>();

Page({
  data: {
    weekStart: "",
    loading: true,
    errorText: "",
    regenLoading: false,
    regenDisabled: false,
    summary: null as WeeklySummary | null,
  },

  onLoad(query: Record<string, string | undefined>) {
    const weekStart = query.week_start || "";
    this.setData({ weekStart });
    this.load(weekStart);
  },

  async load(weekStart: string) {
    if (!weekStart) {
      this.setData({ loading: false, errorText: "这张小结暂时打不开。" });
      return;
    }
    this.setData({ loading: true, errorText: "" });
    try {
      const token = await app.ensureLogin();
      let summary: WeeklySummary;
      try {
        summary = await getWeeklySummary(token, weekStart);
      } catch (getError: unknown) {
        const msg = getError instanceof Error ? getError.message : String(getError);
        if (msg.includes("404")) {
          summary = await createWeeklySummary(token, weekStart);
        } else {
          throw getError;
        }
      }
      this.setData({
        summary,
        loading: false,
        regenDisabled: (summary.regen_count ?? 0) >= 5,
      });
    } catch (error) {
      console.error("[brief-weekly] load failed", error);
      const msg = error instanceof Error ? error.message : String(error);
      if (msg.includes("400")) {
        this.setData({ loading: false, errorText: "这个礼拜讲的还不够，再讲几段再来理。" });
      } else {
        this.setData({ loading: false, errorText: "不急，等会儿再理。" });
      }
    }
  },

  async regen() {
    const summary = this.data.summary;
    if (!summary || this.data.regenLoading || this.data.regenDisabled) return;
    this.setData({ regenLoading: true });
    try {
      const token = await app.ensureLogin();
      const fresh = await regenWeeklySummary(token, this.data.weekStart);
      this.setData({
        summary: fresh,
        regenLoading: false,
        regenDisabled: (fresh.regen_count ?? 0) >= 5,
      });
    } catch (error) {
      this.setData({ regenLoading: false });
      const msg = error instanceof Error ? error.message : String(error);
      if (msg.includes("429")) {
        this.setData({ regenDisabled: true });
        wx.showToast({ title: "这个礼拜已经理了好几次了", icon: "none" });
      } else {
        wx.showToast({ title: "重新理的时候出了问题", icon: "none" });
      }
    }
  },

  goRecord() {
    wx.navigateTo({ url: "/pages/day/day" });
  },

  onShareAppMessage() {
    const summary = this.data.summary;
    return {
      title: summary?.family_share_text || "上个礼拜的事体已经理好了",
      path: "/pages/day/day",
    };
  },
});
