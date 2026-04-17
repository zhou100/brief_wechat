Page({
  data: {
    weekKey: "",
  },

  onLoad(query: Record<string, string | undefined>) {
    this.setData({ weekKey: query.week_key || "" });
  },
});
