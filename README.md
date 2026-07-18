# caigamer-checkin

This project automates daily sign-in on caigamer.cn using Playwright.
这个项目使用 Playwright 自动完成 caigamer.cn 的每日签到。

## What this project does / 这个项目做什么

- It opens the website in a headless browser.
- It logs into the site using your account credentials.
- It checks whether you already signed in today.
- If not, it tries to click the sign-in button.
- It saves screenshots during the flow for debugging.

- 它会在无头浏览器中打开网站。
- 它会使用你的账号信息登录。
- 它会检查今天是否已经签到。
- 如果尚未签到，它会尝试点击签到按钮。
- 它会保存执行过程中的截图，方便排查问题。

## Before you start / 在开始前

You need:
- a GitHub account
- the repository pushed to GitHub
- your caigamer.cn username and password

你需要：
- 一个 GitHub 账号
- 这个仓库已推送到 GitHub
- 你的 caigamer.cn 用户名和密码

## Where to put your account password / 账号密码放在哪里

### Option A: GitHub Actions automatic daily run / 方案 A：GitHub Actions 自动每天运行

Go to your GitHub repository, then open:
- Settings
- Secrets and variables
- Actions

Then add these secrets:
- `CAIGAMER_USERNAME`
- `CAIGAMER_PASSWORD`
- `CAIGAMER_USERNAME_2`
- `CAIGAMER_PASSWORD_2`

If you only use one account, you only need the first two secrets.
If you want two accounts, fill all four.

进入你的 GitHub 仓库后，依次打开：
- Settings
- Secrets and variables
- Actions

然后添加这些 Secret：
- `CAIGAMER_USERNAME`
- `CAIGAMER_PASSWORD`
- `CAIGAMER_USERNAME_2`
- `CAIGAMER_PASSWORD_2`

如果你只用一个账号，只需要前两个即可。
如果你要跑两个账号，就把四个都填写好。

### Option B: Local manual run / 方案 B：本地手动运行

You can also run the script locally on your computer.
In PowerShell or terminal, set the environment variables before running:

你也可以在本地电脑直接运行这个脚本。
在 PowerShell 或终端里先设置环境变量，再执行脚本：

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

## How to run it / 怎么运行

### 1. Install Python dependencies / 安装 Python 依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Run locally / 本地运行

```bash
python checkin.py
```

### 3. If you use GitHub Actions / 如果你使用 GitHub Actions

After you push the repository to GitHub:
1. make sure Actions are enabled
2. make sure the secrets above are created
3. the workflow will run every day at 01:00 UTC automatically
4. you can also click Run workflow manually

仓库推到 GitHub 后：
1. 确认 Actions 已启用
2. 确认上面的 Secrets 已填写
3. 工作流会每天在 UTC 01:00 自动运行
4. 也可以在 GitHub 页面手动点击 Run workflow 立即执行

## What time does it run each day / 每天几点运行

The schedule is:
- every day at 01:00 UTC

定时配置是：
- 每天 UTC 01:00 运行一次

If you want a different time, you can change the cron expression in [.github/workflows/checkin.yml](.github/workflows/checkin.yml).

如果你想改成别的时间，可以在 [.github/workflows/checkin.yml](.github/workflows/checkin.yml) 里修改 cron 表达式。

## What happens after it runs / 运行后会发生什么

- the script opens the website
- logs into the site
- checks status
- clicks sign-in if needed
- saves screenshots
- exits with a result code

- 脚本会打开网站
- 登录网站
- 检查当前签到状态
- 如果未签到会尝试签到
- 保存截图
- 最终退出并返回结果代码

## If something goes wrong / 如果出现问题

Common reasons:
- username or password is missing
- the website changed its page layout
- login or sign-in selectors are no longer correct
- browser dependencies were not installed

常见原因：
- 用户名或密码没有填写
- 网站页面结构发生了变化
- 登录或签到的选择器失效
- 浏览器依赖没有安装成功

If that happens:
- check the logs in the GitHub Actions run or terminal output
- open the screenshot files to see the page state
- update the selectors in [checkin.py](checkin.py)

如果出现问题：
- 查看 GitHub Actions 的日志或本地终端输出
- 打开截图文件查看页面状态
- 在 [checkin.py](checkin.py) 中更新对应选择器

## Recommended first-time usage / 新手推荐的首次使用方式

For a first-time setup:
1. create the GitHub secrets
2. push the repository to GitHub
3. open Actions and run the workflow manually once
4. check the screenshots and logs
5. if it works, leave the schedule enabled

新手第一次建议这样做：
1. 先创建 GitHub Secrets
2. 把仓库推送到 GitHub
3. 打开 Actions，先手动执行一次
4. 查看日志和截图
5. 如果正常，再保持自动定时运行

## License / 许可证

This project is provided for personal use and automation of your own account access.

本项目仅供个人使用，用于自动化自己的账号签到流程。
