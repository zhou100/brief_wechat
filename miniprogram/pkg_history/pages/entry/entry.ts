Page({
  data: {
    id: "",
  },

  onLoad(query: Record<string, string | undefined>) {
    this.setData({ id: query.id || "" });
  },
});
