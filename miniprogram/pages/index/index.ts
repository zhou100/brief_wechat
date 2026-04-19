Page({
  redirected: false,

  onLoad() {
    this.goToday();
  },

  onShow() {
    this.goToday();
  },

  goToday() {
    if (this.redirected) return;
    this.redirected = true;
    wx.redirectTo({ url: "/pages/day/day" });
  },
});
