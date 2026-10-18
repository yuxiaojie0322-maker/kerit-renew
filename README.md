# Kerit Cloud 自动心跳续期项目

> 基于 VPS8 先进架构（SeleniumBase UC 反检测 + NopeCHA + hCaptcha-Challenger LLM 视觉识别 + sing-box 节点代理）。核心脚本托管于私有合集仓库 `my-private-scripts`，由当前公开仓库 GitHub Actions 每日自动触发。

## ⚙️ 环境变量配置 (Repository Secrets)

进入仓库 **Settings** ➔ **Secrets and variables** ➔ **Actions** ➔ **New repository secret** 配置：

| 变量名 | 必填 | 说明 |
| :--- | :---: | :--- |
| `REPO_TOKEN` *(或 `CORE_SCRIPT_TOKEN`)* | **是** | 您的 GitHub Personal Access Token (PAT)，用于拉取私有核心代码 |
| `KERIT` | 否 | 格式为 `邮箱-----密码`（若不填则默认使用内置账号 `yuxiaojie0322@gmail.com`） |
| `NOPECHA_KEY` | 推荐 | NopeCHA 自动打码 Token |
| `OPENAI_API_KEY` | 推荐 | 用于 hCaptcha 视觉识图大模型的 API Key |
| `OPENAI_BASE_URL` | 推荐 | 模型 API 基础路径，如 `https://ai.lezi-chat.bond/v1` |
| `OPENAI_MODEL` | 推荐 | 推荐视觉模型，如 `deepseek-v4.1-flash` |
| `NODE_LINK` | 否 | sing-box 代理节点链接 (支持 vless/vmess/ss，留空则直连) |
| `TG_BOT_TOKEN` | 否 | Telegram 机器人 Token |
| `TG_CHAT_ID` | 否 | Telegram 接收通知账号 ID |

## 🚀 运行机制
- **定时调度**：每天北京时间 10:00 与 22:00 自动触发心跳（+1 天）。
- **手动触发**：在 GitHub Actions 页面随时点击 **Run workflow** 即可手动执行一次续期并查看实时截图。