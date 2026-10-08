#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kerit Cloud (billing.kerit.cloud) 自动登录与续期脚本
架构参考: vpsfree (Playwright + NopeCHA 验证码扩展 + sing-box 节点代理)
所有敏感配置严格通过环境变量 / Secrets 注入
"""

import os
import sys
import re
import time
import requests
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==================== 环境变量配置 ====================
EMAIL = (os.environ.get("KERIT_EMAIL") or os.environ.get("EMAIL") or "").strip()
PASSWORD = (os.environ.get("KERIT_PASSWORD") or os.environ.get("PASSWORD") or "").strip()
NOPECHA_KEY = os.environ.get("NOPECHA_KEY", "").strip()

# 代理配置 (由 setup_proxy.py 启动 sing-box 提供，默认 127.0.0.1:7890)
PROXY_URL = os.environ.get("PROXY_URL", "http://127.0.0.1:7890").strip()
IS_PROXY = os.environ.get("IS_PROXY", "true").lower() == "true"

BASE_URL = "https://billing.kerit.cloud"
LOGIN_URL = f"{BASE_URL}/login"
FREE_HOSTING_URL = f"{BASE_URL}/services/free"

# NopeCHA 扩展本地解压路径
EXT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "scripts", "extensions", "nopecha", "unpacked")

# Telegram 消息推送 (可选)
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
SERVER_NAME = os.environ.get("SERVER_NAME", "Kerit Free Discord Bot").strip()

def log(msg, level="INFO"):
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{t}] [{level}] {msg}", flush=True)

def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email or "未配置"
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        return f"{name}***@{domain}"
    return f"{name[:2]}***{name[-2:]}@{domain}"

# ==================== Telegram 推送 ====================
def send_telegram(status: str, old_time: str = "", new_time: str = "", note: str = "", photo_path: str = ""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    
    t_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    caption = (
        f"⚡ <b>Kerit Cloud 自动续期通知</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>状态</b>: {status}\n"
        f"<b>账号</b>: <code>{mask_email(EMAIL)}</code>\n"
        f"<b>服务</b>: {SERVER_NAME}\n"
    )
    if old_time:
        caption += f"<b>续期前剩余</b>: {old_time}\n"
    if new_time:
        caption += f"<b>续期后剩余</b>: {new_time}\n"
    if note:
        caption += f"<b>说明</b>: {note}\n"
    caption += f"<b>时间</b>: {t_now} (UTC+8)"

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

        inject = f"""// NopeCHA-Inject-Kerit
(function(){{
    const s = {{
        enabled: true,
        key: "{api_key}",
        auto_solve_hcaptcha: true,
        auto_solve_recaptcha: true,
        auto_solve_turnstile: true,
        recaptcha_solve_method: "image"
    }};
    function applySettings() {{
        if (typeof chrome !== 'undefined' && chrome.storage) {{
            if (chrome.storage.local) chrome.storage.local.set({{settings: s, key: "{api_key}"}});
            if (chrome.storage.sync) chrome.storage.sync.set({{settings: s, key: "{api_key}"}});
        }}
    }}
    applySettings();
    setTimeout(applySettings, 1000);
    setTimeout(applySettings, 3000);
}})();
"""
        with open(target_bg, "w", encoding="utf-8") as f:
            f.write(inject + content)

        log("NopeCHA API Key 成功注入插件！已启用 Turnstile/hCaptcha 自动打码")
        return True
    except Exception as e:
        log(f"NopeCHA 注入异常: {e}", "ERROR")
        return False

# ==================== 页面解析辅助 ====================
def extract_remaining_time(page) -> str:
    try:
        text = page.locator("body").inner_text()
        m = re.search(r"(\d+\s*d\s*\d+\s*h\s*\d+\s*m)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m2 = re.search(r"(\d+\s*days?\s*\d+\s*hours?(?:\s*\d+\s*mins?)?)", text, re.IGNORECASE)
        if m2:
            return m2.group(1).strip()
    except Exception as e:
        log(f"提取剩余时间异常: {e}", "WARN")
    return "未知"

# ==================== 主流程 ====================
def run_renewal():
    log("=" * 50)
    log("Kerit Cloud 自动续期任务启动")
    log("=" * 50)

    if not EMAIL or not PASSWORD:
        log("缺少必须的环境变量 KERIT_EMAIL 或 KERIT_PASSWORD！请在 Secrets 中配置", "ERROR")
        sys.exit(1)

    log(f"目标账号: {mask_email(EMAIL)}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("未安装 Playwright！请执行: pip install playwright && playwright install chromium", "ERROR")
        sys.exit(1)

    has_ext = os.path.exists(EXT_PATH) and os.path.exists(os.path.join(EXT_PATH, "manifest.json"))
    if has_ext:
        log(f"检测到 NopeCHA 插件: {EXT_PATH}")
        patch_nopecha(EXT_PATH, NOPECHA_KEY)
    else:
        log(f"未检测到 NopeCHA 插件目录 ({EXT_PATH})，将以原生浏览器运行", "WARN")

    proxy_config = None
    if IS_PROXY and PROXY_URL:
        try:
            r = requests.get("https://api.ip.sb/ip", proxies={"http": PROXY_URL, "https": PROXY_URL}, timeout=6)
            if r.status_code == 200:
                ip = r.text.strip()
                log(f"sing-box 节点代理连通成功！出口 IP: {ip}")
                proxy_config = {"server": PROXY_URL}
        except Exception as e:
            log(f"本地代理 {PROXY_URL} 无法连接 ({e})，将回退直连模式访问", "WARN")

    with sync_playwright() as p:
        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ]
        if has_ext:
            launch_args.extend([
                f"--disable-extensions-except={EXT_PATH}",
                f"--load-extension={EXT_PATH}",
            ])

        user_data_dir = os.path.join(os.getcwd(), "tmp_pw_profile")
        os.makedirs(user_data_dir, exist_ok=True)

        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            proxy=proxy_config,
            args=launch_args,
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="en-US",
            bypass_csp=True,
            ignore_https_errors=True,
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        old_remaining = ""
        new_remaining = ""

        try:
            # ---------------- 步骤 1: 访问登录页 ----------------
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

                # 勾选信任设备 (Keep me signed in / Trust)
                if page.locator("#login-trust, input[type='checkbox']").count() > 0:
                    try:
                        trust_box = page.locator("#login-trust, input[type='checkbox']").first
                        if not trust_box.is_checked():
                            trust_box.check()
                            log("已勾选 'Keep me signed in'")
                    except Exception:
                        pass

                page.screenshot(path="02_login_filled.png")

                # 处理人机验证：主动点击 KGuard 验证框触发验证
                log("检测并点击 KGuard 人机验证框...")
                try:
                    kguard_candidates = [
                        "text='Verify you are human'",
                        "text='Click to start'",
                        "[class*='kguard']",
                        "[id*='kguard']",
                        ".kguard-checkbox",
                        "[role='checkbox']"
                    ]
                    for sel in kguard_candidates:
                        loc = page.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            log(f"点击 KGuard 元素: {sel}")
                            loc.first.click(force=True)
                            time.sleep(2)
                            break
                except Exception as e:
                    log(f"触发 KGuard 提示: {e}", "WARN")

                # 检测验证码 iframe (Turnstile / Cloudflare / hCaptcha) 并点击
                for _ in range(6):
                    try:
                        for f in page.frames:
                            if any(x in f.url.lower() for x in ["challenges.cloudflare.com", "turnstile", "kguard", "hcaptcha"]):
                                cb = f.locator("input[type='checkbox'], #cf-stage, .cb-i, svg, [role='checkbox']").first
                                if cb.is_visible():
                                    cb.click(force=True)
                                    log("已主动协助点击验证码内部复选框")
                                    break
                    except Exception:
                        pass
                    time.sleep(1)

                log("等待 NopeCHA 打码插件识别与生效 (6秒)...")
                time.sleep(6)
                page.screenshot(path="02_before_submit.png")

                # 定位并点击可见的 'Sign In' 登录按钮 (排除隐藏的 #login-2fa-btn)
                log("正在定位可见的 Sign In 登录按钮...")
                clicked = False

                # 优先方式: 使用纯 JS 在页面上寻找当前可见且包含 Sign In 文本的按钮
                try:
                    res = page.evaluate("""() => {
                        const btns = Array.from(document.querySelectorAll('button, a.auth-btn, div.auth-btn, input[type="submit"]'));
                        for (const b of btns) {
                            if (b.id === 'login-2fa-btn') continue;
                            const isVisible = !!(b.offsetWidth || b.offsetHeight || b.getClientRects().length);
                            const txt = (b.innerText || b.textContent || b.value || '').trim();
                            if (isVisible && (txt.toLowerCase().includes('sign in') || txt.toLowerCase().includes('login'))) {
                                b.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                b.click();
                                return txt;
                            }
                        }
                        return null;
                    }""")
                    if res:
                        log(f"通过 JS 成功触发登录按钮点击: '{res}'")
                        clicked = True
                except Exception as e:
                    log(f"JS 触发登录按钮异常: {e}", "WARN")

                if not clicked:
                    # 备用选择器列表
                    btn_selectors = [
                        "button:visible:not(#login-2fa-btn):has-text('Sign In')",
                        "button.auth-btn:visible:not(#login-2fa-btn)",
                        "button[type='submit']:visible:not(#login-2fa-btn)",
                        "button:visible:has-text('Sign In')"
                    ]
                    for sel in btn_selectors:
                        try:
                            loc = page.locator(sel)
                            if loc.count() > 0 and loc.first.is_visible():
                                log(f"通过选择器定位到按钮: {sel}，执行点击...")
                                loc.first.click(force=True)
                                clicked = True
                                break
                        except Exception:
                            pass

                # 等待登录跳转
                log("等待登录跳转...")
                logged_in = False
                for _ in range(35):
                    time.sleep(1)
                    cur_url = page.url.lower()
                    if "/login" not in cur_url:
                        logged_in = True
                        log(f"登录成功，当前 URL: {page.url}")
                        break
                    
                    # 检查是否有 2FA 提示
                    if page.locator("#login-2fa-btn:visible, input[name*='2fa']:visible, input[id*='2fa']:visible").count() > 0:
                        log("账号需要 2FA 双重身份验证！无法全自动登录，请先关闭 2FA", "ERROR")
                        page.screenshot(path="login_2fa_required.png")
                        send_telegram("登录失败 (需要 2FA)", note="检测到 2FA 验证，请在平台关闭 2FA", photo_path="login_2fa_required.png")
                        return False

                    # 检查是否有错误提示
                    if page.locator("#login-error, .alert-danger, .error-message").count() > 0:
                        err_el = page.locator("#login-error, .alert-danger, .error-message").first
                        if err_el.is_visible():
                            err_msg = err_el.inner_text().strip()
                            if err_msg:
                                log(f"登录页面报错提示: {err_msg}", "ERROR")
                                page.screenshot(path="login_error.png")
                                send_telegram("登录失败", note=f"页面报错: {err_msg}", photo_path="login_error.png")
                                return False

                if not logged_in:
                    log("登录超时，仍停留在登录页面", "ERROR")
                    page.screenshot(path="login_failed.png")
                    send_telegram("登录超时", note="未能成功跳转出登录页", photo_path="login_failed.png")
                    return False

            time.sleep(2)
            page.screenshot(path="03_after_login.png")

            # ---------------- 步骤 2: 访问 Free Hosting 续期页面 ----------------
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
            heartbeat_btn.click(force=True)
            time.sleep(6)

            # 确认弹窗处理
            for _ in range(5):
                time.sleep(1)
                if page.locator("button:visible:has-text('Confirm'), button:visible:has-text('OK'), button:visible:has-text('Yes')").count() > 0:
                    try:
                        page.locator("button:visible:has-text('Confirm'), button:visible:has-text('OK'), button:visible:has-text('Yes')").first.click(force=True)
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
                browser.close()
            except Exception:
                pass

if __name__ == "__main__":
    success = run_renewal()
    sys.exit(0 if success else 1)
