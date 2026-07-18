# caigamer-checkin

A simple Playwright-based automation script for daily sign-in on caigamer.cn.
一个基于 Playwright 的自动签到脚本，用于每天自动签到 caigamer.cn。

## Overview / 项目概览

This repository contains:
- `checkin.py`: the browser automation workflow
- `.github/workflows/checkin.yml`: GitHub Actions schedule/dispatch automation
- `requirements.txt`: Python dependency list

本仓库包含：
- `checkin.py`：浏览器自动化签到流程
- `.github/workflows/checkin.yml`：GitHub Actions 定时/手动运行配置
- `requirements.txt`：Python 依赖清单

## Local Run / 本地运行

### 1. Install dependencies / 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Set environment variables / 设置环境变量

On Windows PowerShell:

```powershell
$env:CAIGAMER_USERNAME="your_username"
$env:CAIGAMER_PASSWORD="your_password"
python checkin.py
```

On Linux/macOS:

```bash
export CAIGAMER_USERNAME="your_username"
export CAIGAMER_PASSWORD="your_password"
python checkin.py
```

### 3. Notes / 备注

- The script uses headless Chromium and saves screenshots for each step.
- The script captures network responses that look like sign-in APIs for debugging.
- If the site UI changes, you may need to update the selectors in `checkin.py`.

- 脚本使用无头 Chromium，并会为每一步保存截图。
- 脚本会监听与签到相关的 API 请求与响应，便于排查问题。
- 如果网站页面结构变更，可能需要更新 `checkin.py` 中的选择器。

## GitHub Actions Deployment / GitHub Actions 部署

### 1. Add repository secrets / 添加仓库 Secrets

Create the following secrets in your GitHub repository:
- `CAIGAMER_USERNAME`
- `CAIGAMER_PASSWORD`
- `CAIGAMER_USERNAME_2`
- `CAIGAMER_PASSWORD_2`

在 GitHub 仓库中添加以下 Secrets：
- `CAIGAMER_USERNAME`
- `CAIGAMER_PASSWORD`
- `CAIGAMER_USERNAME_2`
- `CAIGAMER_PASSWORD_2`

### 2. Enable Actions / 启用 Actions

Push this repository to GitHub, then enable GitHub Actions.

推送到 GitHub 后，确认 GitHub Actions 已启用。

### 3. Workflow behavior / 工作流行为

- Scheduled run: every day at 01:00 UTC
- Manual run: via `workflow_dispatch`
- Screenshots are uploaded as GitHub Actions artifacts

- 定时运行：每天 UTC 01:00
- 手动运行：通过 `workflow_dispatch`
- 截图会作为 Actions artifact 上传，便于排查

## Troubleshooting / 故障排查

Typical causes:
- missing environment variables
- website structure changed
- login popup selector no longer matches
- sign-in button selector changed

常见原因：
- 环境变量缺失
- 网站页面结构发生变化
- 登录弹窗选择器失效
- 签到按钮选择器失效

## License / 许可证

This project is provided for personal use and automation of your own account access.

本项目仅供个人使用，用于自动化自己的账号签到流程。
