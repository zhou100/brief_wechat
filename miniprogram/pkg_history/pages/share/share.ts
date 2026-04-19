import { getSharedBrief } from "../../../services/entries";

Page({
  data: {
    shareId: "",
    summary: "",
    openLoopCount: 0,
  },

  onLoad(query: Record<string, string | undefined>) {
    const shareId = query.share_id || "";
    this.setData({ shareId });
    this.load(shareId);
  },

  async load(shareId: string) {
    if (!shareId) return;
    try {
      const result = await getSharedBrief(shareId);
      this.setData({
        summary: result.summary,
        openLoopCount: result.open_loop_count,
      });
    } catch (error) {
      wx.showToast({ title: "暂时打不开", icon: "none" });
    }
  },

  startRecord() {
    wx.reLaunch({ url: "/pages/index/index" });
  },
});
