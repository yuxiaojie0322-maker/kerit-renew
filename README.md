# Kerit Cloud 免费托管自动续期脚本

适用于 [Kerit Cloud (克里特云)](https://billing.kerit.cloud) 的 Discord 机器人免费托管（Free Hosting）自动续期项目。

通过 GitHub Actions 每天定时自动登录、绕过 Cloudflare 盾及 KGuard 防护、识别人机验证（hCaptcha / Turnstile）、点击 **“发送心跳 · +1天”** 续期按钮，并通过 Telegram 推送每日续期结果。

---

## 🌟 核心特性

- **过盾方案**：采用 **SeleniumBase UC (Undetected-Chromedriver) 模式**，模拟真实人类输入与操作行为，支持智能处理 Cloudflare Turnstile 和 hCaptcha 人机验证。
- **纯净节点代理**：集成 **sing-box** 代理隧道，支持通过 `NODE_LINK` 节点订阅链接挂载纯净节点运行，有效解决 GitHub Actions 官方机房 IP 遭到 Cloudflare 403 拦截或盾验证无法通过的问题。
- **双重保底机制**：心跳按钮点击支持 CSS 选择器查找与原生 JavaScript 节点遍历双重机制，确保无论页面改版或微调均能稳健点击。
- **全流程截图**：执行过程自动生成各阶段诊断截图（登录页、登录后、免费工坊页、心跳前、心跳后），出错时可从 Actions Artifacts 快速排查。
- **Telegram 实时推送**：支持推送续期状态、当前剩余时长、今日已心跳次数等完整信息。

---

## ⚙️ GitHub Secrets 配置参数

在你的 GitHub 仓库中，进入 **Settings** -> **Secrets and variables** -> **Actions**，添加以下 Repository Secrets：

| Secret 名称 | 必须 | 说明 | 示例 |
| :--- | :---: | :--- | :--- |
| `KERIT_EMAIL` | 是 | Kerit Cloud 登录邮箱 | `yuxiaojie0322@gmail.com` |
| `KERIT_PASSWORD` | 是 | Kerit Cloud 登录密码 | `YxJ223512@` |
| `NODE_LINK` | **推荐** | 节点链接（vless / vmess / ss / trojan / 订阅链接），配合 sing-box 解决机房 IP 封锁与 CF 盾 | `vless://...` 或 `https://sub...` |
| `TG_BOT_TOKEN` | 否 | Telegram Bot Token，用于推送消息 | `123456789:ABCdef...` |
| `TG_CHAT_ID` | 否 | Telegram Chat ID，接收通知的个人或群聊 ID | `987654321` |
| `SERVER_NAME` | 否 | 自定义服务器备注名称，用于通知标识 | `【免费】yuxiaojie0322` |

> 💡 **提示**：如果未设置 `NODE_LINK`，脚本将自动尝试使用 GitHub Actions 直连网络访问。但鉴于 Kerit Cloud 部署了较严格的 Cloudflare 盾策略，配置一个纯净节点（`NODE_LINK`）可以极大提升通过率。

---

## 🚀 部署步骤

1. **新建 GitHub 仓库**（建议设为 **Private 私有仓库**）。
2. 将本项目所有文件上传至仓库：
   ```bash
   git init
   git add .
   git commit -m "feat: init kerit cloud auto renew"
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```
3. 在仓库的 **Settings** -> **Secrets and variables** -> **Actions** 中配置上述 Secrets。
4. 进入仓库的 **Actions** 标签页，在左侧选择 **Kerit Cloud Auto Renew** 工作流，点击 **Run workflow** 手动测试一次。
5. 测试完成后，查看工作流输出日志和生成的 Artifact 截图，若配置了 Telegram 还会收到状态推送。
6. 脚本默认配置在 **每天 UTC 02:00（北京时间 10:00）** 自动执行一次。

---

## 📂 项目文件结构

```
.
├── .github/
│   └── workflows/
│       └── renew.yml          # GitHub Actions 自动化工作流定义
├── app.py                     # 核心续期逻辑（SeleniumBase UC 自动化驱动）
├── requirements.txt           # Python 依赖清单
├── .gitignore                 # Git 忽略配置
└── README.md                  # 说明文档
```
