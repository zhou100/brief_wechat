import type { BriefApp } from "../../app";
import {
  createShareCard,
  deleteCloudFile,
  deleteEntry,
  getDailyBrief,
  getEntryResult,
  regenerateEntry,
} from "../../services/entries";
import type { CategoryGroup, HistoryItem, ShareCard } from "../../types/api";
import { todayLocalDate } from "../../utils/date";
import { userFacingError } from "../../utils/errors";

const app = getApp<BriefApp>();

Page({
  data: {
    entryId: "",
    date: "",
    createdAt: "",
    summary: "",
    keyPoints: [] as string[],
    openLoops: [] as string[],
    categoryGroups: [] as ViewCategoryGroup[],
    entries: [] as HistoryItem[],
    entryCount: 0,
    contentCount: 0,
    cloudFileId: "",
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
      const result = await loadResult(token, entryId, date);
      this.setData({
        entryId: result.entry_id,
        createdAt: result.created_at,
        summary: result.summary,
        keyPoints: result.key_points || [],
        openLoops: result.open_loops || [],
        categoryGroups: viewCategoryGroups(result.category_groups || [], result.key_points || [], result.open_loops || []),
        entries: result.entries || [],
        entryCount: result.entries?.length || (result.entry_id ? 1 : 0),
        contentCount: countContent(result.category_groups || [], result.key_points || []),
        cloudFileId: result.cloud_file_id || "",
        shareCard: result.share_card || null,
      });
      const hasShareableContent = Boolean(result.entry_id) || Boolean(result.entries?.length);
      if (!result.share_card && hasShareableContent) {
        this.prepareShare(false);
      }
    } catch (error) {
      wx.showToast({ title: "结果暂时打不开", icon: "none" });
    }
  },

  async prepareShare(showError = true) {
    if (!this.data.date && !this.data.entryId) return;
    try {
      const token = await app.ensureLogin();
      const response = await createShareCard(token, {
        date: this.data.date,
        entryId: this.data.date ? undefined : this.data.entryId,
      });
      this.setData({ shareCard: response.card });
    } catch (error) {
      if (showError) {
        wx.showToast({ title: "暂时发不出去", icon: "none" });
      }
    }
  },

  async regenerate() {
    if (!this.data.entryId) return;
    wx.showLoading({ title: "重新整理" });
    try {
      const token = await app.ensureLogin();
      const response = await regenerateEntry(token, this.data.entryId);
      wx.setStorageSync("brief_active_job_id", response.job_id);
      wx.hideLoading();
      wx.redirectTo({ url: `/pages/job/job?job_id=${response.job_id}` });
    } catch (error) {
      wx.hideLoading();
      wx.showToast({ title: userFacingError(error, "重新整理没成功"), icon: "none" });
    }
  },

  deleteCurrent() {
    if (!this.data.entryId) return;
    wx.showModal({
      title: "删除刚才这段？",
      content: "删除后，这段录音和整理结果都会移除。今天其它记录会保留。",
      confirmText: "删除",
      success: async (res) => {
        if (!res.confirm) return;
        try {
          const token = await app.ensureLogin();
          await deleteEntry(token, this.data.entryId);
          if (this.data.cloudFileId) {
            deleteCloudFile(this.data.cloudFileId).catch((error) => {
              console.warn("[brief-cloud] delete file failed", error);
            });
          }
          wx.showToast({ title: "已删除", icon: "success" });
          wx.reLaunch({ url: "/pages/index/index" });
        } catch (error) {
          wx.showToast({ title: "删除没成功", icon: "none" });
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
      title: card?.title || "今天已经整理清爽了",
      path: shareId
        ? `/pkg_history/pages/share/share?share_id=${shareId}`
        : "/pages/index/index",
      imageUrl: card?.image_url,
    };
  },
});

async function loadResult(token: string, entryId: string, date: string) {
  if (date) {
    try {
      return await getDailyBrief(token, date);
    } catch (error) {
      if (!entryId) throw error;
      console.warn("[brief-day] daily result unavailable, falling back to entry result", error);
    }
  }
  if (!entryId) {
    return getDailyBrief(token, date || todayLocalDate());
  }
  return getEntryResult(token, entryId);
}

type ViewCategoryGroup = CategoryGroup & {
  helper: string;
  accentClass: string;
};

function viewCategoryGroups(
  groups: CategoryGroup[],
  keyPoints: string[],
  openLoops: string[],
): ViewCategoryGroup[] {
  if (groups.length > 0) {
    return groups.map((group) => ({
      ...group,
      helper: categoryHelper(group.category),
      accentClass: `category-${group.category.toLowerCase()}`,
    }));
  }

  const fallback: ViewCategoryGroup[] = [];
  if (openLoops.length > 0) {
    fallback.push({
      category: "TODO",
      label: "要办的事",
      helper: categoryHelper("TODO"),
      accentClass: "category-todo",
      items: openLoops.map((text) => ({ text, category: "TODO" })),
    });
  }
  if (keyPoints.length > 0) {
    fallback.push({
      category: "REFLECTION",
      label: "刚才讲到",
      helper: "先把原话理出来，后面多讲几段会更清楚。",
      accentClass: "category-reflection",
      items: keyPoints.map((text) => ({ text, category: "REFLECTION" })),
    });
  }
  return fallback;
}

function categoryHelper(category: CategoryGroup["category"]): string {
  const helpers: Record<CategoryGroup["category"], string> = {
    TODO: "明确要做的事，适合发给家人帮忙记一下。",
    MAITAISHAO: "买菜、汰菜、烧菜这些日常事，单独放一栏。",
    EXPERIMENT: "可以试试的办法，不一定今天就要办。",
    REFLECTION: "想法、感受、提醒，先留着以后看。",
    EARNING: "今天已经做过、办过、处理过的事。",
    LEARNING: "今天听到、看到、琢磨明白的东西。",
    FAMILY: "家人、家务、照顾人的事情。",
    RELAXING: "休息、锻炼、娱乐、出门走走。",
    TIME_RECORD: "时间记录。",
  };
  return helpers[category] || "";
}

function countContent(groups: CategoryGroup[], keyPoints: string[]): number {
  const total = groups.reduce((sum, group) => sum + group.items.length, 0);
  return total || keyPoints.length;
}
