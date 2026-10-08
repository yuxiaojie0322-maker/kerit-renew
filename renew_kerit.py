# -*- coding: utf-8 -*-
"""
Kerit Cloud 自动每日续期脚本
- 支持 Cookie 免登录直通续期 (避开 KGuard 与人机验证)
- 配合 sing-box 本地代理 (127.0.0.1:7890) 绕过 Cloudflare 区域拦截
- 支持 Cookie 过期时自动降级回账号密码登录流程
- 进入 /services/free 页面并点击 "⚡ Send a heartbeat - +1 day" 续期按钮
- 支持 Telegram Bot 截图与状态通知
"""

import os
import sys
import time
import re
import requests
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# 设置标准输出编码为 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==================== 配置读取 ====================
KERIT_COOKIES = os.getenv("KERIT_COOKIES", "")
EMAIL = os.getenv("KERIT_EMAIL", "")
PASSWORD = os.getenv("KERIT_PASSWORD", "")
NOPECHA_KEY = os.getenv("NOPECHA_KEY", "")
PROXY_SERVER = os.getenv("PROXY_SERVER", "127.0.0.1:7890")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
SERVER_NAME = os.getenv("SERVER_NAME", "Kerit-Free-Bot")

LOGIN_URL = "https://billing.kerit.cloud/login"
FREE_HOSTING_URL = "https://billing.kerit.cloud/services/free"

# ==================== 日志与通知函数 ====================
def log(msg, level="INFO"):
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    prefix = f"[{now}] [{level}]"
    print(f"{prefix} {msg}", flush=True)

def mask_email(email_str):
    if not email_str or "@" not in email_str:
        return email_str
    user, domain = email_str.split("@", 1)
    if len(user) <= 2:
        return f"{user[:1]}***@{domain}"
    return f"{user[:2]}***{user[-1:]}@{domain}"

def send_telegram(status, old_time=None, new_time=None, note=None, photo_path=None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return

    t_now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "<b>Kerit Cloud 自动续期任务</b>",
        f"<b>状态</b>: {status}",
        f"<b>账号</b>: <code>{mask_email(EMAIL)}</code>",
        f"<b>服务</b>: {SERVER_NAME}"
    ]
    if old_time:
        lines.append(f"<b>续期前剩余</b>: {old_time}")
    if new_time:
        lines.append(f"<b>续期后剩余</b>: {new_time}")
    if note:
        lines.append(f"<b>说明</b>: {note}")
    lines.append(f"<b>时间</b>: {t_now} (UTC+8)")
    caption = "\n".join(lines)

    if photo_path and os.path.exists(photo_path):
        try:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
            with open(photo_path, "rb") as f:
                r = requests.post(url, files={"photo": f}, data={
                    "chat_id": TG_CHAT_ID,
                    "caption": caption,
                    "parse_mode": "HTML"
                }, timeout=25)
            if r.json().get("ok"):
                log("Telegram 截图通知发送成功")
                return
        except Exception as e:
            log(f"TG 发送图片异常: {e}，降级发送纯文本", "WARN")

    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TG_CHAT_ID,
            "text": caption,
            "parse_mode": "HTML"
        }, timeout=15)
        log("Telegram 文本通知发送成功")
    except Exception as e:
        log(f"TG 发送通知异常: {e}", "WARN")

# ==================== Cookie 注入函数 ====================
def inject_cookies(context, cookie_raw):
    if not cookie_raw:
        return False
    cookies = []
    for item in cookie_raw.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        k, v = item.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"')

        domain = "billing.kerit.cloud"
        if "cf_clearance" in k or "__cf" in k or "CF_" in k:
            domain = ".kerit.cloud"

        cookies.append({
            "name": k,
            "value": v,
            "domain": domain,
            "path": "/"
        })
    if cookies:
        try:
            context.add_cookies(cookies)
            log(f"成功注入 {len(cookies)} 个 Cookie 登录/免盾凭证！")
            return True
        except Exception as e:
            log(f"注入 Cookie 异常: {e}", "WARN")
    return False

# ==================== 补丁注入 NopeCHA 扩展 ====================
def patch_nopecha(nopecha_path, api_key):
    if not api_key:
        log("未提供 NOPECHA_KEY，使用试用模式", "WARN")
        return False

    bg_files = [
        os.path.join(nopecha_path, "assets", "qrmm9f.js"),
        os.path.join(nopecha_path, "background.js")
    ]
    target_bg = None
    for bg in bg_files:
        if os.path.exists(bg):
            target_bg = bg
            break

    if not target_bg:
        log(f"未找到 NopeCHA 后台入口脚本: {nopecha_path}", "WARN")
        return False

    try:
        with open(target_bg, "r", encoding="utf-8") as f:
            content = f.read()

        if "// NopeCHA-Inject-Kerit" in content:
            log("NopeCHA 插件已注入 Key，跳过重复写入", "INFO")
            return True

        inject_code = (
            "// NopeCHA-Inject-Kerit\n"
            "(function(){\n"
            "    const s = {\n"
            "        enabled: true,\n"
            f'        key: "{api_key}",\n'
            "        turnstile_auto_solve: true,\n"
            "        hcaptcha_auto_solve: true,\n"
            "        recaptcha_auto_solve: true,\n"
            "        settings: {\n"
            "            turnstile_auto_solve: true,\n"
            "            hcaptcha_auto_solve: true,\n"
            "            recaptcha_auto_solve: true\n"
            "        }\n"
            "    };\n"
            "    if(typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local){\n"
            "        chrome.storage.local.set(s, function(){});\n"
            "        chrome.storage.sync.set(s, function(){});\n"
            "    }\n"
            "})();\n"
        )
        with open(target_bg, "w", encoding="utf-8") as f:
            f.write(inject_code + "\n" + content)
        log("已成功向 NopeCHA 插件注入 API Key 与自动打码配置")
        return True
    except Exception as e:
        log(f"注入 NopeCHA Key 失败: {e}", "WARN")
        return False

# ==================== 辅助解析剩余时间 ====================
def extract_remaining_time(page):
    try:
        patterns = [
            r"(\d+\s*(?:days?|hours?|d|h|天|小时|分))",
            r"(Expires\s+in\s+[^<\n]+)",
            r"(Remaining\s+time\s*:\s*[^<\n]+)",
            r"(\d+\s*d\s*\d+\s*h)"
        ]
        text = page.locator("body").inner_text()
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    except Exception:
        pass
    return "未知"

# ==================== 核心执行流程 ====================
def run_renewal():
    log("==================================================")
    log("         Kerit Cloud 自动续期任务启动              ")
    log("==================================================")

    if not KERIT_COOKIES and (not EMAIL or not PASSWORD):
        log("缺少 KERIT_COOKIES 或 账号密码环境变量！", "ERROR")
        send_telegram("失败", note="环境变量未配置 Cookie 或账号密码")
        return False

    if EMAIL:
        log(f"账号: {mask_email(EMAIL)}")

    # 1. 检查代理连接
    proxy_config = None
    if PROXY_SERVER:
        log(f"正在测试 sing-box 代理: {PROXY_SERVER} ...")
        try:
            test_proxies = {
                "http": f"http://{PROXY_SERVER}",
                "https": f"http://{PROXY_SERVER}"
            }
            r = requests.get("https://api.ipify.org?format=json", proxies=test_proxies, timeout=12)
            exit_ip = r.json().get("ip", "未知")
            log(f"sing-box 代理连接成功！出口 IP: {exit_ip}")
            proxy_config = {"server": f"http://{PROXY_SERVER}"}
        except Exception as e:
            log(f"sing-box 代理测试异常: {e}，尝试直接连接", "WARN")

    # 2. 准备 NopeCHA 插件
    nopecha_ext_dir = os.path.join(os.getcwd(), "nopecha_ext")
    load_extension = False
    if os.path.isdir(nopecha_ext_dir):
        patch_nopecha(nopecha_ext_dir, NOPECHA_KEY)
        load_extension = True
        log(f"检测到已解压的 NopeCHA 插件目录: {nopecha_ext_dir}")

    # 3. 启动 Chromium
    with sync_playwright() as p:
        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1366,768"
        ]
        if load_extension:
            launch_args.extend([
                f"--disable-extensions-except={nopecha_ext_dir}",
                f"--load-extension={nopecha_ext_dir}"
            ])

        user_data_dir = os.path.join(os.getcwd(), ".chromium_user_data")
        log("启动 Chromium 浏览器上下文...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=launch_args,
            proxy=proxy_config,
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )

        page = context.new_page()

        # 监听关键网络请求便于排查
        def log_response(res):
            try:
                url_low = res.url.lower()
                if any(k in url_low for k in ["login", "kguard", "challenge", "submit", "heartbeat"]):
                    body_preview = ""
                    try:
                        body_preview = " -> " + res.text()[:200].replace("\n", " ")
                    except Exception:
                        pass
                    log(f"网络响应 [{res.status}] {res.url}{body_preview}")
            except Exception:
                pass
        page.on("response", log_response)

        try:
            # ---------------- 步骤 1: 登录 / 恢复 Session ----------------
            is_logged_in = False

            # 优先方式: 使用 Cookie 免登录直通
            if KERIT_COOKIES:
                log("检测到 KERIT_COOKIES，正在注入并直接访问 Free Hosting 续期页面...")
                inject_cookies(context, KERIT_COOKIES)
                page.goto(FREE_HOSTING_URL, wait_until="networkidle", timeout=45000)
                time.sleep(3)
                page.screenshot(path="01_cookie_check.png")

                if "/login" not in page.url.lower():
                    log(f"🎉 成功使用 Cookie 免登录进入页面！当前 URL: {page.url}")
                    is_logged_in = True
                else:
                    log("Cookie 已过期或未能通过，降级使用账号密码登录流程", "WARN")

            # 备用方式: 账号密码表单登录
            if not is_logged_in:
                log(f"正在访问登录页面: {LOGIN_URL}")
                page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
                time.sleep(3)
                page.screenshot(path="01_login_page.png")

                if "/login" not in page.url.lower():
                    log("检测到当前已处于登录状态，直接进入续期流程")
                else:
                    log("正在填写账号密码...")
                    page.wait_for_selector("#login-email, input[type='email'], input[name='email']", timeout=15000)
                    email_input = page.locator("#login-email, input[type='email'], input[name='email']").first
                    email_input.fill(EMAIL)
                    time.sleep(0.5)

                    pwd_input = page.locator("#p-login, input[type='password'], input[name='password']").first
                    pwd_input.fill(PASSWORD)
                    time.sleep(0.5)

                    if page.locator("#login-trust, input[type='checkbox']").count() > 0:
                        try:
                            trust_box = page.locator("#login-trust, input[type='checkbox']").first
                            if not trust_box.is_checked():
                                trust_box.check()
                                log("已勾选 'Keep me signed in'")
                        except Exception:
                            pass

                    page.screenshot(path="02_login_filled.png")

                    # 触发并等待 KGuard 人机验证
                    def is_kguard_verified():
                        try:
                            body_txt = page.locator("body").inner_text().lower()
                            return "you are verified" in body_txt or "confirmed human" in body_txt
                        except Exception:
                            return False

                    log("正在检查并触发 KGuard 人机验证...")
                    for sel in [
                        "text='Click to start the security check'",
                        "text='Verify you are human'",
                        "div:has-text('Verify you are human')",
                        "[class*='kguard']",
                        "#kguard"
                    ]:
                        try:
                            loc = page.locator(sel)
                            if loc.count() > 0 and loc.first.is_visible():
                                loc.first.click()
                                log(f"已点击 KGuard 目标: {sel}")
                                break
                        except Exception:
                            pass

                    for i in range(6):
                        time.sleep(1)
                        if is_kguard_verified():
                            log(f"🎉 KGuard 已成功验证！(耗时 {i+1} 秒)")
                            break

                    if not is_kguard_verified():
                        log("KGuard 尚未激活，点击一次 Sign In 激活后端挑战计算...", "INFO")
                        sign_in_btn = page.locator("button:visible:not(#login-2fa-btn)").filter(has_text="Sign In").first
                        if sign_in_btn.is_visible():
                            sign_in_btn.click()

                        for i in range(20):
                            time.sleep(1)
                            if is_kguard_verified():
                                log(f"🎉 KGuard 挑战计算完毕，已成功验证！(耗时 {i+1} 秒)")
                                break

                    time.sleep(2)
                    page.screenshot(path="02_before_submit.png")

                    log("正在定位并点击可见的 Sign In 登录按钮...")
                    sign_in_btn = page.locator("button:visible:not(#login-2fa-btn)").filter(has_text="Sign In").first
                    if not sign_in_btn.is_visible():
                        sign_in_btn = page.locator(".auth-btn:visible:not(#login-2fa-btn)").first

                    if sign_in_btn.is_visible():
                        sign_in_btn.click()
                    else:
                        pwd_input.press("Enter")

                    # 等待登录跳转
                    log("等待登录跳转中...")
                    for step_i in range(35):
                        time.sleep(1)
                        if any(p in page.url.lower() for p in ["/services", "/dashboard", "/account", "/client"]):
                            is_logged_in = True
                            log(f"🎉 登录成功！当前 URL: {page.url}")
                            break

                        if page.locator("#login-2fa-btn:visible, input[name*='2fa']:visible").count() > 0:
                            log("账号需要 2FA 双重身份验证！请在平台设置中关闭 2FA", "ERROR")
                            page.screenshot(path="login_2fa_required.png")
                            send_telegram("登录失败 (需要 2FA)", note="检测到 2FA 验证，请在平台关闭 2FA", photo_path="login_2fa_required.png")
                            return False

                        page_txt = page.locator("body").inner_text().lower()
                        if "human verification failed" in page_txt and is_kguard_verified():
                            log("检测到验证码已就绪 (绿色对勾)，重新点击 Sign In 提交 Token！", "INFO")
                            btn = page.locator("button:visible:not(#login-2fa-btn)").filter(has_text="Sign In").first
                            if btn.is_visible():
                                btn.click()
                                time.sleep(4)
                                continue

                        if page.locator("#login-error, .alert-danger, .error-message").count() > 0:
                            err_el = page.locator("#login-error, .alert-danger, .error-message").first
                            if err_el.is_visible():
                                err_msg = err_el.inner_text().strip()
                                if "human verification failed" not in err_msg.lower():
                                    log(f"登录页面报错提示: {err_msg}", "ERROR")
                                    page.screenshot(path="login_error.png")
                                    send_telegram("登录失败", note=f"平台报错: {err_msg}", photo_path="login_error.png")
                                    return False

                    if not is_logged_in:
                        log("登录超时，未能跳转入后台", "ERROR")
                        page.screenshot(path="login_failed.png")
                        send_telegram("登录超时", note="未能成功跳转出登录页", photo_path="login_failed.png")
                        return False

            time.sleep(2)
            page.screenshot(path="03_after_login.png")

            # ---------------- 步骤 2: 访问 Free Hosting 续期页面 ----------------
            if "/services/free" not in page.url.lower():
                log(f"正在进入 Free Hosting 页面: {FREE_HOSTING_URL}")
                page.goto(FREE_HOSTING_URL, wait_until="networkidle", timeout=45000)
                time.sleep(4)

            page.screenshot(path="04_free_hosting_page.png")
            old_remaining = extract_remaining_time(page)
            log(f"当前剩余有效时间: {old_remaining}")

            # ---------------- 步骤 3: 查找并点击 Heartbeat 按钮 ----------------
            log("正在定位 'Send a heartbeat - +1 day' 续期按钮...")
            heartbeat_btn = None
            btn_selectors = [
                "button:visible:has-text('Send a heartbeat')",
                "button:visible:has-text('heartbeat')",
                "//button[contains(., 'heartbeat')]"
            ]
            for sel in btn_selectors:
                loc = page.locator(sel)
                if loc.count() > 0 and loc.first.is_visible():
                    heartbeat_btn = loc.first
                    break

            if not heartbeat_btn:
                log("未直接发现 Heartbeat 按钮，滚动页面后查找...", "WARN")
                page.mouse.wheel(0, 300)
                time.sleep(1)
                loc = page.locator("button:visible:has-text('heartbeat')")
                if loc.count() > 0 and loc.first.is_visible():
                    heartbeat_btn = loc.first

            if not heartbeat_btn:
                log("未能定位到 Heartbeat 按钮", "ERROR")
                page.screenshot(path="heartbeat_btn_missing.png")
                send_telegram("续期按钮未找到", old_time=old_remaining, note="页面未渲染出 Send a heartbeat 按钮", photo_path="heartbeat_btn_missing.png")
                return False

            btn_text = heartbeat_btn.inner_text().strip()
            btn_disabled = heartbeat_btn.is_disabled() or "wait" in btn_text.lower() or "cooldown" in btn_text.lower()

            if btn_disabled:
                log(f"续期按钮当前不可点击 / 正在冷却中 ({btn_text})", "INFO")
                page.screenshot(path="heartbeat_cooldown.png")
                send_telegram("今日已心跳/冷却中", old_time=old_remaining, new_time=old_remaining, note=f"按钮状态: {btn_text}", photo_path="heartbeat_cooldown.png")
                return True

            log(f"正在点击续期按钮: '{btn_text}'...")
            heartbeat_btn.click()
            time.sleep(6)

            # 确认弹窗处理
            for _ in range(5):
                time.sleep(1)
                if page.locator("button:visible:has-text('Confirm'), button:visible:has-text('OK'), button:visible:has-text('Yes')").count() > 0:
                    try:
                        page.locator("button:visible:has-text('Confirm'), button:visible:has-text('OK'), button:visible:has-text('Yes')").first.click()
                        log("点击了确认弹窗按钮")
                        time.sleep(2)
                    except Exception:
                        pass

            page.screenshot(path="05_heartbeat_success.png")
            log("Heartbeat 续期按钮点击完成！")

            time.sleep(3)
            page.reload(wait_until="networkidle")
            time.sleep(3)
            new_remaining = extract_remaining_time(page)
            log(f"续期后最新剩余时间: {new_remaining}")

            send_telegram("续期成功", old_time=old_remaining, new_time=new_remaining, note="Heartbeat 心跳包已成功发送", photo_path="05_heartbeat_success.png")
            return True

        except Exception as e:
            log(f"运行异常: {e}", "ERROR")
            try:
                page.screenshot(path="error.png")
                send_telegram("运行异常", note=f"异常详情: {e}", photo_path="error.png")
            except Exception:
                pass
            return False
        finally:
            try:
                context.close()
            except Exception:
                pass

if __name__ == "__main__":
    success = run_renewal()
    sys.exit(0 if success else 1)
