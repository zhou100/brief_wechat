# 讲过就清爽

一个练习项目。帮助说方言的中老年人用语音记录日常，AI 自动整理成可读的文字摘要。

开源，随意使用。

---

## 背景

很多中老年人不擅长打字，但愿意说话。这个小程序让用户对着手机讲一段话，后端自动转录、分类、整理，结果以简洁的中文呈现。界面设计以吴语区中老年用户为主要对象，文字大、操作少、语言口语化。

产品名"讲过就清爽"——讲出来，记下来，脑子就轻松了。

## 功能

- 语音录制，上传到 CloudBase 存储
- 后端转录（讯飞）、AI 分类整理（DeepSeek）
- 按天查看整理结果，支持手动再整理
- 按周生成回顾摘要
- 历史记录浏览

## 技术栈

```text
miniprogram/     微信小程序（TypeScript + WXML）
backend/         FastAPI 后端（Python，部署于腾讯云托管）
```

后端依赖：
- 讯飞 WebSocket 流式转录
- 腾讯云 TokenHub → DeepSeek v3 / Hunyuan（LLM）
- CloudBase MySQL + CloudBase 存储
- JWT 认证

## 本地运行

**小程序端：**

```bash
npm install
npm run build
cp miniprogram/env.example.ts miniprogram/env.ts
# 修改 env.ts 填入你的 API 地址
```

用微信开发者工具打开项目根目录（`project.config.json` 所在位置）。

**后端：**

```bash
cp deployment/tencent-cloudbase-env.example backend/.env
# 填入各服务的密钥
cd backend
pip install -r requirements.txt
python scripts/init_db.py
uvicorn app.main:app --reload
```

所需外部服务：MySQL、讯飞账号、腾讯云 TokenHub 账号。

## 部署

腾讯云托管（CloudBase Run）部署说明见：

- `docs/tencent-cloudbase.md`
- `docs/cloudbase-checklist.md`
- `deployment/tencent-cloudbase-env.example`

## 注意

`backend/.env` 包含密钥，不要提交到版本库。项目内有 `.env.example` 模板。

## License

MIT

---

# 讲过就清爽 (Talk It Out, Clear Your Head)

A practice project. A WeChat Mini Program that helps older adults who speak Chinese dialects record their daily lives by voice — the backend transcribes and organises everything into a readable summary.

Open source. Use it however you like.

## Background

Many older adults find typing difficult but are happy to talk. This app lets users speak into their phone; the backend transcribes, categorises, and tidies the result into plain Chinese. The UI is designed for Wu-dialect speakers: large text, minimal steps, conversational language.

The name means roughly "once you've said it, your head feels lighter."

## Features

- Voice recording, uploaded to Tencent CloudBase storage
- Transcription via iFlytek, AI organisation via DeepSeek
- Day view with manual re-tidy option
- Weekly recap summary
- History browsing

## Stack

```text
miniprogram/     WeChat Mini Program (TypeScript + WXML)
backend/         FastAPI backend (Python, deployed on Tencent CloudBase Run)
```

Backend dependencies:
- iFlytek WebSocket streaming ASR
- Tencent TokenHub → DeepSeek v3 / Hunyuan (LLM)
- CloudBase MySQL + CloudBase storage
- JWT auth

## Local Setup

**Mini Program:**

```bash
npm install
npm run build
cp miniprogram/env.example.ts miniprogram/env.ts
# Fill in your API base URL in env.ts
```

Open the project root in WeChat DevTools (where `project.config.json` lives).

**Backend:**

```bash
cp deployment/tencent-cloudbase-env.example backend/.env
# Fill in your service credentials
cd backend
pip install -r requirements.txt
python scripts/init_db.py
uvicorn app.main:app --reload
```

External services required: MySQL, iFlytek account, Tencent TokenHub account.

## Deployment

CloudBase Run deployment is documented in:

- `docs/tencent-cloudbase.md`
- `docs/cloudbase-checklist.md`
- `deployment/tencent-cloudbase-env.example`

## Note

`backend/.env` contains secrets — do not commit it. A template is provided at `deployment/tencent-cloudbase-env.example`.

## License

MIT
