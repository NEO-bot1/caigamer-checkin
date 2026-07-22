# Caigamer Check-in — Handoff Guide

简短说明（Summary）
- 目的：自动化在 caigamer.cn 的每日签到流程（登录、判断是否已签到、必要时点击签到并保存截图）。
- 语言：Python（异步 Playwright）。
- 主脚本：checkin.py。CI：.github/workflows/checkin.yml。

项目结构
- checkin.py — 主流程实现，包含浏览器启动、登录、签到检测、点击与截图保存。
- README.md — 使用、部署与故障排查说明（中英）。
- requirements.txt — 依赖（包含 playwright）。
- .github/workflows/checkin.yml — GitHub Actions 工作流，定时运行并上传截图 artifact。
- CLAUDE.md — 本文件，供 LLM 或新维护者快速接手。

运行前提与环境变量
- 必需环境变量：CAIGAMER_USERNAME, CAIGAMER_PASSWORD。
- 可选：CAIGAMER_USERNAME_2, CAIGAMER_PASSWORD_2（当前脚本未使用第二账号，但 README 推荐可配置）。
- 依赖安装：

```bash
pip install -r requirements.txt
playwright install chromium
```

本地运行（示例）

Windows PowerShell:

```powershell
$env:CAIGAMER_USERNAME="your_username"
$env:CAIGAMER_PASSWORD="your_password"
python checkin.py
```

Linux / macOS:

```bash
export CAIGAMER_USERNAME="your_username"
export CAIGAMER_PASSWORD="your_password"
python checkin.py
```

主要流程（High-level）
- 读取环境变量；若缺失则记录错误并返回非零退出码。
- 启动 headless Chromium，设置 viewport/locale/timezone（Asia/Shanghai）。
- 打开 https://caigamer.cn/，等待 DOM 加载并截图（page_01_homepage_*）。
- 处理登录弹窗：检查页面 input 元素，若未自动弹出则尝试点击登录链接。等待并定位用户名/密码输入框，填写并回车提交。
- 关闭可能的欢迎 modal（通过执行页面 JS 清理 .modal 与 backdrop）。
- 查找 #sign_title，读取其文本判断是否包含“今日已签到”。若未签到，尝试点击（优先点击可点击的父元素），等待并重新检查状态。
- 在关键步骤保存截图，文件格式 page_<step>_<timestamp>.png，CI 会将这些截图作为 artifact 上传以便排查。

故障排查点（Troubleshooting）
- 缺少环境变量：检查 Actions Secrets 或本地环境。
- 页面结构变化：查看最新截图定位新选择器，更新 checkin.py 中相应 query_selector 或 wait_for_selector。
- 网站引入验证码或二次验证：脚本无法自动应对，需要人工介入或引入更复杂的解决方案。
- 浏览器依赖或字体问题：确保执行 playwright install chromium，CI 中已包含中文字体安装步骤。

对 LLM/新维护者的快速交接要点
- 入口函数：run_checkin()（checkin.py）。
- 关键点：username/password 环境变量，签到判断点为页面元素 #sign_title。
- 修改选择器：搜索 query_selector, wait_for_selector, #sign_title 并调整定位逻辑或超时。
- 调试：在本地运行并查看生成的 page_*.png 文件，或在 Actions 的 run 中下载 artifact。

建议改进（可选）
- 支持多账号：将账号列表参数化并循环执行签到流程。
- 增加重试与退避策略：对关键点击和网络请求添加重试机制与更合理的超时。
- 更稳健的选择器：优先使用 data-* 或更稳定的 CSS 路径，而非仅依赖文本或层级结构。
- 引入 dry-run 模式（仅截图/验证选择器，不提交登录）便于 CI 前的验证。
- 日志与监控：把日志保存为 artifact 或上传到集中化日志系统；避免在日志中打印敏感信息。

输出与退出码
- 输出：page_*.png 截图文件。CI 上传为 artifact。
- 退出码：0 表示成功或无需操作，1 表示出现错误。

许可与使用条款
- 个人用途：仅用于自动化你自己的账户操作。请遵守目标站点的服务条款与法律法规。

---

若你希望，我可以：
- 直接把此文件提交到远程仓库（需要你在本地执行 git push），或
- 继续改进 checkin.py（例如增强选择器健壮性、多账号支持或重试逻辑）。

（结束）
