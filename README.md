# Kerit Cloud 自动登录与续期系统

基于 **Playwright** + **NopeCHA 验证码插件 (自动识别 Turnstile / hCaptcha)** + **sing-box 节点代理 (Trojan)** 的 Kerit Cloud (`billing.kerit.cloud`) 每日心跳自动续期方案。

---

## 🌟 核心特性
1. **真实浏览器自动化**: 基于 Playwright 驱动 Chromium，配合虚拟显示器 (Xvfb) 无头模式，规避常见 Cloudflare 脚本封锁。
2. **NopeCHA 验证码自动破解**: 自动下载 NopeCHA Chromium 扩展并注入 API Key，自动勾选和破解 Cloudflare Turnstile 与 hCaptcha。
3. **内置 sing-box 节点代理**:
   - 原生支持 `trojan://`, `vless://`, `vmess://`, `hysteria2://`, `tuic://`。
   - 动态解析并将流量桥接至本地 `127.0.0.1:7890`，使用海外纯净住宅/机房节点直连目标，降低风控拦截。
4. **Discord Bot 免费续期专精**:
   - 登录后直达 `/services/free` 页面。
   - 自动读取剩余天数与心跳状态，精准点击 `Send a heartbeat - +1 day`。
5. **Telegram 推送**: 成功、冷却中、异常均支持 TG 详细通知，并附带现场截图。

---

## 🔐 环境变量 / GitHub Secrets 配置

| 变量名 | 默认值 / 示例 | 说明 |
| :--- | :--- | :--- |
| `KERIT_EMAIL` | `yuxiaojie0322@gmail.com` | Kerit Cloud 登录邮箱 |
| `KERIT_PASSWORD` | `YxJ223512@` | Kerit Cloud 登录密码 |
| `NOPECHA_KEY` | `qifr6gi669wcvuj8iy30rq2j410wfjwm` | NopeCHA 打码 API Key |
| `NODE_LINK` | `trojan://...` | sing-box 节点链接 (默认为你的 Trojan 节点) |
| `TG_BOT_TOKEN` | *(可选)* | Telegram Bot Token |
| `TG_CHAT_ID` | *(可选)* | Telegram Chat ID |

---

## 💻 本地运行方法

1. 安装依赖:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
2. (可选) 下载 NopeCHA 插件到 `scripts/extensions/nopecha/unpacked`:
   ```bash
   mkdir -p scripts/extensions/nopecha/unpacked
   # 下载 chromium.zip 并解压到该目录
   ```
3. 运行续期:
   ```bash
   python renew_kerit.py
   ```
