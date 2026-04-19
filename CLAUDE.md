# Project Notes

## Runtime Path

This repo lives in WSL.

Use this Linux path for terminal commands:

```bash
/home/yujunz/llm_projects/brief_wechat
```

Do not run build/test commands from the Windows UNC path:

```text
\\wsl.localhost\Ubuntu\home\yujunz\llm_projects\brief_wechat
```

Windows `cmd.exe` does not support UNC working directories and may silently fall back to `C:\Windows`, which breaks commands like `npm run build`.

When the shell is PowerShell, run WSL commands through an explicit WSL path, for example:

```powershell
wsl.exe -d Ubuntu --cd /home/yujunz/llm_projects/brief_wechat -- bash -lc "npm run build"
```

If WSL Node is unavailable, run Node with absolute UNC paths instead of relying on the current working directory:

```powershell
node "\\wsl.localhost\Ubuntu\home\yujunz\llm_projects\brief_wechat\node_modules\typescript\bin\tsc" -p "\\wsl.localhost\Ubuntu\home\yujunz\llm_projects\brief_wechat\miniprogram\tsconfig.json"
```

## Ship Workflow

Never run `/ship` directly from `main`.

Before shipping, create or switch to a feature branch from the WSL repo path, for example:

```powershell
wsl.exe -d Ubuntu --cd /home/yujunz/llm_projects/brief_wechat -- git switch -c miniapp-daily-refresh
```

Then run `/ship`. This keeps CloudBase/GitHub deploy changes reviewable and avoids pushing a large working tree directly to `main`.

## Design System

Always read `DESIGN.md` before making visual or UI decisions.

Current product direction:

- Product name: `讲过就清爽`
- Tone: Wu/dialect-friendly, older-user-readable, warm red with Jiangnan qing accent
- Core flow: `开始讲 -> 录音 -> 上传 -> 整理 -> 结果 -> 发给家人`
