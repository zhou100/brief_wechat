import type { BriefApp } from "../../app";
import { JOB_POLL_INTERVAL_MS } from "../../env";
import { RECORDING_PRESETS, startRecording, stopRecording } from "../../services/recorder";
import {
  deleteItem,
  getDailyBrief,
  getEntryResult,
  getJob,
  getWeeklySuggestion,
  submitRecordedEntry,
  tidyDay,
  updateItemText,
} from "../../services/entries";
import type { CategoryGroup, HistoryItem, WeeklySuggestion } from "../../types/api";
import { addLocalDays, formatDayLabel, formatDuration, previousWeekStart, sanitizeLocalDate, todayLocalDate } from "../../utils/date";
import { jobErrorText, userFacingError } from "../../utils/errors";

const app = getApp<BriefApp>();

Page({
  data: {
    entryId: "",
    date: "",
    today: "",
    dateLabel: "今天",
    isToday: true,
    createdAt: "",
    summary: "",
    keyPoints: [] as string[],
    openLoops: [] as string[],
    categoryGroups: [] as ViewCategoryGroup[],
    entries: [] as HistoryItem[],
    entryCount: 0,
    contentCount: 0,
    dayStatsText: "今天还没记内容。",
    starting: false,
    recording: false,
    stopping: false,
    uploading: false,
    processing: false,
    dateNavDisabled: false,
    elapsedMs: 0,
    elapsedLabel: "0:00",
    statusText: "",
    activeJobId: "",
    errorText: "",
    editingItemId: "",
    editDraft: "",
    tidying: false,
    hasUntidiedTranscripts: false,
    viewMode: "category" as "category" | "timeline",
    weeklySuggestion: null as WeeklySuggestion | null,
  },

  recordTimer: 0 as number,
  pollTimer: 0 as number,
  loadRequestId: 0 as number,
  recordingDate: "" as string,

  onLoad(query: Record<string, string | undefined>) {
    const entryId = query.entry_id || "";
    const today = todayLocalDate();
    const date = sanitizeLocalDate(query.date, today) || today;
    this.setData({
      entryId,
      ...dateViewState(date, today),
    });
    this.load(entryId, date);
  },

  onShow() {
    const activeJobId = wx.getStorageSync("brief_active_job_id") || "";
    if (activeJobId && activeJobId !== this.data.activeJobId) {
      this.startPolling(activeJobId);
    }
  },

  async load(entryId: string, date: string) {
    const requestId = ++this.loadRequestId;
    try {
      const token = await app.ensureLogin();
      const result = await loadResult(token, entryId, date);
      if (requestId !== this.loadRequestId) return;
      const categoryGroups = viewCategoryGroups(result.category_groups || [], result.key_points || [], result.open_loops || []);
      const entries = result.entries || [];
      const hasUntidiedTranscripts = entries.some((entry) => !!entry.transcript && (!entry.categories || entry.categories.length === 0));
      const contentCount = countContent(result.category_groups || [], result.key_points || []);
      this.setData({
        entryId: result.entry_id,
        createdAt: result.created_at,
        summary: result.summary,
        keyPoints: result.key_points || [],
        openLoops: result.open_loops || [],
        categoryGroups,
        entries,
        entryCount: entries.length || (result.entry_id ? 1 : 0),
        contentCount,
        dayStatsText: dayStatsText(this.data.dateLabel, entries.length || (result.entry_id ? 1 : 0), contentCount, hasUntidiedTranscripts),
        hasUntidiedTranscripts,
        viewMode: hasUntidiedTranscripts ? "timeline" : categoryGroups.length > 0 ? this.data.viewMode : entries.length > 0 ? "timeline" : "category",
      });
      this.loadWeeklySuggestion(token);
    } catch (error) {
      if (requestId !== this.loadRequestId) return;
      console.warn("[brief-day] load failed", error);
      if (shouldShowLoadFailureToast(error, entryId, date, this.data.entryCount, this.data.contentCount)) {
        wx.showToast({ title: `${this.data.dateLabel}内容暂时打不开`, icon: "none" });
      }
    }
  },

  switchDate(date: string) {
    if (this.data.dateNavDisabled) return;
    const today = todayLocalDate();
    const nextDate = sanitizeLocalDate(date, today);
    if (!nextDate) {
      wx.showToast({ title: "不能选未来的日期", icon: "none" });
      return;
    }
    this.setData({
      entryId: "",
      createdAt: "",
      summary: "",
      keyPoints: [],
      openLoops: [],
      categoryGroups: [],
      entries: [],
      entryCount: 0,
      contentCount: 0,
      dayStatsText: `${formatDayLabel(nextDate, today)}还没记内容。`,
      hasUntidiedTranscripts: false,
      errorText: "",
      editingItemId: "",
      editDraft: "",
      viewMode: "category",
      weeklySuggestion: null,
      ...dateViewState(nextDate, today),
    });
    this.load("", nextDate);
  },

  goPreviousDay() {
    this.switchDate(addLocalDays(this.data.date || todayLocalDate(), -1));
  },

  goNextDay() {
    if (this.data.isToday) return;
    this.switchDate(addLocalDays(this.data.date || todayLocalDate(), 1));
  },

  goToday() {
    this.switchDate(todayLocalDate());
  },

  selectDate(event: WechatMiniprogram.CustomEvent<{ value: string }>) {
    this.switchDate(event.detail.value);
  },

  async startRecord() {
    if (this.data.starting || this.data.recording || this.data.stopping || this.data.uploading || this.data.processing) return;
    this.recordingDate = this.data.date || todayLocalDate();
    this.setData({ starting: true, dateNavDisabled: true, errorText: "", statusText: "正在准备录音。" });
    try {
      await app.ensureLogin();
      const options = RECORDING_PRESETS[0];
      await startRecording(options);
      vibrate();
      this.setData({
        starting: false,
        recording: true,
        stopping: false,
        uploading: false,
        dateNavDisabled: true,
        errorText: "",
        elapsedMs: 0,
        elapsedLabel: "0:00",
        statusText: "正在听你讲",
      });
      this.recordTimer = Number(setInterval(() => {
        const elapsedMs = this.data.elapsedMs + 1000;
        this.setData({ elapsedMs, elapsedLabel: formatDuration(elapsedMs) });
      }, 1000));
    } catch (error) {
      this.recordingDate = "";
      wx.showToast({ title: "录音没打开", icon: "none" });
      this.setData({ starting: false, dateNavDisabled: false, statusText: "录音没打开，请再试一次" });
    }
  },

  async stopRecord() {
    if (!this.data.recording || this.data.stopping || this.data.uploading || this.data.processing) return;
    clearInterval(this.recordTimer);
    this.setData({
      recording: false,
      stopping: true,
      dateNavDisabled: true,
      errorText: "",
      statusText: "收到了，正在收尾。",
    });
    try {
      const result = await stopRecording();
      vibrate();
      await this.upload(result.tempFilePath, result.durationMs);
    } catch (error) {
      this.recordingDate = "";
      this.setData({
        recording: false,
        stopping: false,
        uploading: false,
        dateNavDisabled: false,
        statusText: "这段没录上，请再讲一遍",
      });
      wx.showToast({ title: "这段没录上", icon: "none" });
    }
  },

  async upload(filePath: string, durationMs: number) {
    this.setData({
      recording: false,
      stopping: false,
      uploading: true,
      processing: true,
      dateNavDisabled: true,
      errorText: "",
      statusText: "收到了，先帮你记下来。",
    });

    try {
      const token = await app.ensureLogin();
      const localDate = this.recordingDate || this.data.date || todayLocalDate();
      const entry = await submitRecordedEntry({
        token,
        filePath,
        durationMs,
        localDate,
        recorderOptions: RECORDING_PRESETS[0],
      });
      this.recordingDate = "";
      this.setData(dateViewState(localDate, todayLocalDate()));
      wx.setStorageSync("brief_active_job_id", entry.job_id);
      this.startPolling(entry.job_id);
      wx.showToast({ title: "正在记下来", icon: "none" });
    } catch (error) {
      this.recordingDate = "";
      const message = userFacingError(error, "这段没传上去，请再试一次。");
      console.error("[brief-day] upload failed", error);
      this.setData({
        uploading: false,
        processing: false,
        dateNavDisabled: false,
        statusText: "这段没传上去",
        errorText: message,
      });
      wx.showToast({ title: "没传上去", icon: "none" });
    }
  },

  startPolling(jobId: string) {
    clearInterval(this.pollTimer);
    this.setData({
      activeJobId: jobId,
      processing: true,
      uploading: false,
      dateNavDisabled: true,
      statusText: "正在帮你记下来。",
      errorText: "",
    });
    this.pollJob();
    this.pollTimer = Number(setInterval(() => this.pollJob(), JOB_POLL_INTERVAL_MS));
  },

  async pollJob() {
    if (!this.data.activeJobId) return;
    try {
      const token = await app.ensureLogin();
      const job = await getJob(token, this.data.activeJobId);
      if (job.status === "done") {
        clearInterval(this.pollTimer);
        wx.removeStorageSync("brief_active_job_id");
        const date = job.local_date || this.data.date || todayLocalDate();
        this.setData({
          activeJobId: "",
          processing: false,
          uploading: false,
          dateNavDisabled: false,
          statusText: `刚才这段已经记下来，放进${formatDayLabel(date, todayLocalDate())}了。`,
          ...dateViewState(date, todayLocalDate()),
        });
        await this.load(job.entry_id || this.data.entryId, date);
        return;
      }

      if (job.status === "failed") {
        clearInterval(this.pollTimer);
        wx.removeStorageSync("brief_active_job_id");
        this.setData({
          activeJobId: "",
          processing: false,
          uploading: false,
          dateNavDisabled: false,
          statusText: "这段没听清，请再讲一遍。",
          errorText: jobErrorText(job.error_code, job.error_message),
        });
        return;
      }

      this.setData({ statusText: "正在听写，先把原话记下来。" });
    } catch (error) {
      this.setData({ statusText: "网络有点慢，还在继续记下来。" });
    }
  },

  async loadWeeklySuggestion(token: string) {
    const today = todayLocalDate();
    if (this.data.date !== today || this.data.processing) {
      this.setData({ weeklySuggestion: null });
      return;
    }

    const weekStart = previousWeekStart(today);
    const userId = app.globalData.user?.id || "unknown";
    if (wx.getStorageSync(weeklyPromptKey(userId, weekStart, "seen")) || wx.getStorageSync(weeklyPromptKey(userId, weekStart, "dismissed"))) {
      this.setData({ weeklySuggestion: null });
      return;
    }

    try {
      const suggestion = await getWeeklySuggestion(token, weekStart);
      if (this.data.date !== today || this.data.processing) return;
      this.setData({ weeklySuggestion: suggestion.show ? suggestion : null });
    } catch (error) {
      console.warn("[brief-day] weekly suggestion skipped", error);
      this.setData({ weeklySuggestion: null });
    }
  },

  openWeeklyThings() {
    const suggestion = this.data.weeklySuggestion;
    if (!suggestion) return;
    const userId = app.globalData.user?.id || "unknown";
    wx.setStorageSync(weeklyPromptKey(userId, suggestion.week_start, "seen"), "1");
    this.setData({ weeklySuggestion: null });
    wx.navigateTo({
      url: `/pkg_history/pages/weekly-detail/weekly-detail?week_start=${suggestion.week_start}`,
    });
  },

  dismissWeeklyThings() {
    const suggestion = this.data.weeklySuggestion;
    if (!suggestion) return;
    const userId = app.globalData.user?.id || "unknown";
    wx.setStorageSync(weeklyPromptKey(userId, suggestion.week_start, "dismissed"), "1");
    this.setData({ weeklySuggestion: null });
  },

  async tidy() {
    if (this.data.tidying || this.data.processing) return;
    const date = this.data.date || todayLocalDate();
    this.setData({ tidying: true, statusText: "正在帮你理清爽。" });
    try {
      const token = await app.ensureLogin();
      await tidyDay(token, date);
      await this.load(this.data.entryId, date);
      wx.showToast({ title: "整理好了", icon: "success" });
    } catch (error) {
      wx.showToast({ title: "没整理成功，请再试", icon: "none" });
    } finally {
      this.setData({ tidying: false });
    }
  },

  startEdit(event: WechatMiniprogram.TouchEvent) {
    const { itemId, text } = event.currentTarget.dataset as { itemId?: string; text?: string };
    if (!itemId) return;
    this.setData({ editingItemId: itemId, editDraft: text || "" });
  },

  updateEditDraft(event: WechatMiniprogram.Input) {
    this.setData({ editDraft: event.detail.value });
  },

  cancelEdit() {
    this.setData({ editingItemId: "", editDraft: "" });
  },

  showCategoryView() {
    this.setData({ viewMode: "category" });
  },

  showTimelineView() {
    this.setData({ viewMode: "timeline" });
  },

  async saveEdit(event: WechatMiniprogram.TouchEvent) {
    const { itemId } = event.currentTarget.dataset as { itemId?: string };
    if (!itemId) return;
    try {
      const token = await app.ensureLogin();
      await updateItemText(token, itemId, this.data.editDraft);
      this.setData({ editingItemId: "", editDraft: "" });
      await this.load(this.data.entryId, this.data.date || todayLocalDate());
    } catch (error) {
      wx.showToast({ title: "没改成功", icon: "none" });
    }
  },

  deleteThing(event: WechatMiniprogram.TouchEvent) {
    const { itemId } = event.currentTarget.dataset as { itemId?: string };
    if (!itemId) return;
    wx.showModal({
      title: "删掉这条？",
      content: "只删这一条整理出来的内容，不会删整段录音。",
      confirmText: "删除",
      success: async (res) => {
        if (!res.confirm) return;
        try {
          const token = await app.ensureLogin();
          await deleteItem(token, itemId);
          await this.load(this.data.entryId, this.data.date || todayLocalDate());
        } catch (error) {
          wx.showToast({ title: "没删成功", icon: "none" });
        }
      },
    });
  },

  onShareAppMessage() {
    return {
      title: "今天已经整理清爽了",
      path: `/pages/day/day?date=${this.data.date || todayLocalDate()}`,
    };
  },

  onHide() {
    if (this.data.activeJobId) {
      wx.setStorageSync("brief_active_job_id", this.data.activeJobId);
    }
  },

  onUnload() {
    clearInterval(this.recordTimer);
    clearInterval(this.pollTimer);
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

function dateViewState(date: string, today = todayLocalDate()) {
  return {
    date,
    today,
    dateLabel: formatDayLabel(date, today),
    isToday: date === today,
  };
}

function shouldShowLoadFailureToast(error: unknown, entryId: string, date: string, entryCount: number, contentCount: number): boolean {
  if (entryId || entryCount > 0 || contentCount > 0) return true;
  return date !== todayLocalDate() || !isNotFoundError(error);
}

function isNotFoundError(error: unknown): boolean {
  return error instanceof Error && error.message.includes("Request failed: 404");
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
      label: "还要做",
      helper: categoryHelper("TODO"),
      accentClass: "category-todo",
      items: openLoops.map((text) => ({ text, category: "TODO" })),
    });
  }
  if (keyPoints.length > 0) {
    fallback.push({
      category: "REFLECTION",
      label: "刚才讲到",
      helper: categoryHelper("REFLECTION"),
      accentClass: "category-reflection",
      items: keyPoints.map((text) => ({ text, category: "REFLECTION" })),
    });
  }
  return fallback;
}

function categoryHelper(category: CategoryGroup["category"]): string {
  const helpers: Record<CategoryGroup["category"], string> = {
    TODO: "明确还没做、需要记住的事。",
    MAITAISHAO: "买菜、汰菜、烧菜这些日常事。",
    EXPERIMENT: "可以试试的办法。",
    REFLECTION: "想到的感受、判断和以后可回看的话。",
    EARNING: "今天已经办过、处理过的事。",
    LEARNING: "今天听到、看到、琢磨明白的东西。",
    FAMILY: "照顾家人、陪家人、为家里人跑的事。",
    RELAXING: "休息、锻炼、娱乐。",
    TIME_RECORD: "时间记录。",
  };
  return helpers[category] || "";
}

function countContent(groups: CategoryGroup[], keyPoints: string[]): number {
  const total = groups.reduce((sum, group) => sum + group.items.length, 0);
  return total || keyPoints.length;
}

function dayStatsText(dateLabel: string, entryCount: number, contentCount: number, hasUntidiedTranscripts: boolean): string {
  if (entryCount <= 0) return `${dateLabel}还没记内容。`;
  if (hasUntidiedTranscripts && contentCount <= 0) return `${dateLabel}已记下 ${entryCount} 段，点一下可以理清爽。`;
  if (hasUntidiedTranscripts) return `${dateLabel}已记下 ${entryCount} 段，还有原话可以继续理清爽。`;
  return `${dateLabel}讲了 ${entryCount} 段，整理出 ${contentCount} 条内容。`;
}

function vibrate() {
  try {
    wx.vibrateShort({ type: "light" });
  } catch (error) {
    console.warn("[brief-day] vibrate unavailable", error);
  }
}

function weeklyPromptKey(userId: string, weekStart: string, state: "seen" | "dismissed"): string {
  return `brief_weekly_prompt_${state}:${userId}:${weekStart}`;
}
