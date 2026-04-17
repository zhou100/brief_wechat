Page({
  data: {
    message: "",
  },

  onInput(event: WechatMiniprogram.Input) {
    this.setData({ message: event.detail.value });
  },

  submit() {
    wx.showToast({ title: "已记录", icon: "success" });
  },
});
