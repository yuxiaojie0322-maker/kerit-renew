# -*- coding: utf-8 -*-
"""
Kerit Cloud (billing.kerit.cloud) 自动续期脚本
支持 GitHub Actions、sing-box 节点代理与 Telegram 消息推送
"""

import os
import re
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from seleniumbase import SB

# ==================== 环境变量与配置 ====================
EMAIL = os.environ.get("KERIT_EMAIL") or os.environ.get("EMAIL") or "yuxiaojie0322@gmail.com"
PASSWORD = os.environ.get("KERIT_PASSWORD") or os.environ.get("PASSWORD") or "YxJ223512@"

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""
SERVER_NAME = os.environ.get("SERVER_NAME") or "Kerit Free Hosting"

# 代理配置（sing-box 生成）
IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER") or "socks5://127.0.0.1:1080"

BASE_URL = "https://billing.kerit.cloud"
LOGIN_URL = f"{BASE_URL}/login"
FREE_HOSTING_URL = f"{BASE_URL}/services/free"

# ==================== 日志与工具函数 ====================
def log(msg: str):
    now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}", flush=True)

def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return email or "未配置"
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        return f"{name}***@{domain}"
    return f"{name[:2]}***{name[-2:]}@{domain}"

def get_current_ip():
    proxies = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None
    try:
        resp = requests.get("https://api.ip.sb/ip", proxies=proxies, timeout=10)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass
    try:
        resp = requests.get("https://ipinfo.io/ip", proxies=proxies, timeout=10)
        if resp.status_code == 200:
            return resp.text.strip()
    except Exception:
        pass
    return "获取失败"

def send_telegram_notification(status: str, old_due: str, new_due: str, count_info: str = "", note: str = ""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("⚠️ Telegram 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过通知")
        return
    
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    msg_lines = [
        "📡 <b>Kerit Cloud 自动续期通知</b>",
        "",
        f"<b>状态</b>: {status}",
        f"<b>账号</b>: <code>{mask_email(EMAIL)}</code>",
        f"<b>服务</b>: {SERVER_NAME}",
    ]
    if old_due:
        msg_lines.append(f"<b>续期前剩余</b>: {old_due}")
    if new_due:
        msg_lines.append(f"<b>续期后剩余</b>: {new_due}")
    if count_info:
        msg_lines.append(f"<b>今日心跳</b>: {count_info}")
    if note:
        msg_lines.append(f"<b>详细说明</b>: {note}")
    msg_lines.append(f"<b>执行时间</b>: {now_str} (UTC+8)")

    text = "\n".join(msg_lines)
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    proxies = {"http": PROXY_SERVER, "https": PROXY_SERVER} if IS_PROXY else None
    try:
        r = requests.post(url, json=payload, proxies=proxies, timeout=15)
        if r.status_code == 200:
            log("✅ Telegram 通知推送成功")
        else:
            log(f"⚠️ Telegram 推送失败: HTTP {r.status_code} - {r.text}")
    except Exception as e:
        log(f"❌ Telegram 推送异常: {e}")

# ==================== 页面解析与操作 ====================
def extract_remaining_time(sb) -> str:
    """提取剩余有效时间（例如：6天23小时43分钟）"""
    try:
        page_text = sb.get_text("body")
        # 匹配 X天X小时X分钟
        m = re.search(r"(\d+\s*天\s*\d+\s*小时(?:\s*\d+\s*分钟)?)", page_text)
        if m:
            return m.group(1).replace(" ", "")
        # 英文备用匹配
        m_en = re.search(r"(\d+\s*days?\s*\d+\s*hours?(?:\s*\d+\s*mins?)?)", page_text, re.IGNORECASE)
        if m_en:
            return m_en.group(1)
    except Exception as e:
        log(f"提取剩余时间异常: {e}")
    return "未知"

def extract_heartbeat_count(sb) -> str:
    """提取今日心跳次数（例如：今天的第0/5次）"""
    try:
        page_text = sb.get_text("body")
        m = re.search(r"(今天的第\s*\d+/\d+\s*次|\d+/\d+\s*次)", page_text)
        if m:
            return m.group(1).replace(" ", "")
    except Exception as e:
        log(f"提取心跳次数异常: {e}")
    return ""

def handle_captcha_checkbox(sb) -> bool:
    """处理 hCaptcha 或 Turnstile 复选框"""
    log("🔒 正在检测并尝试处理人机验证 (hCaptcha / Turnstile)...")
    
    # 1. 尝试 SeleniumBase UC 模式内置人机验证智能处理
    try:
        sb.uc_gui_handle_captcha()
        log("🤖 已调用 uc_gui_handle_captcha 处理人机验证")
        time.sleep(3)
    except Exception as e:
        log(f"uc_gui_handle_captcha 提示: {e}")

    # 2. 检查是否有 hCaptcha iframe 并尝试切换点击复选框
    try:
        hcaptcha_iframes = sb.find_elements('iframe[src*="hcaptcha.com"]')
        if hcaptcha_iframes:
            log(f"检测到 {len(hcaptcha_iframes)} 个 hCaptcha iframe，尝试检查并点击...")
            for idx, frame in enumerate(hcaptcha_iframes):
                try:
                    sb.switch_to_frame(frame)
                    time.sleep(1)
                    # 查找 checkbox
                    checkbox = sb.find_elements('#checkbox, .check, [role="checkbox"]')
                    if checkbox:
                        log(f"在 iframe #{idx} 中找到复选框，进行点击...")
                        sb.click(checkbox[0])
                        time.sleep(2)
                    sb.switch_to_default_content()
                except Exception as fe:
                    sb.switch_to_default_content()
                    log(f"处理 iframe #{idx} 出现轻微异常: {fe}")
    except Exception as e:
        log(f"检查 hCaptcha iframe 异常: {e}")
    
    time.sleep(2)
    return True

def find_and_click_heartbeat_button(sb) -> bool:
    """定位并点击 发送心跳 按钮"""
    log("🔍 正在定位 '发送心跳 · +1天' 按钮...")
    
    # 多种选择器查找
    btn_selectors = [
        'button:contains("发送心跳")',
        'button:contains("心跳")',
        'button:contains("heartbeat")',
        '//button[contains(., "发送心跳") or contains(., "心跳") or contains(., "heartbeat")]',
        'button.btn:contains("心跳")',
    ]
    
    for sel in btn_selectors:
        try:
            if sb.is_element_visible(sel):
                log(f"🎯 找到心跳按钮 (选择器: {sel})，准备点击...")
                sb.scroll_to(sel)
                time.sleep(1)
                sb.click(sel)
                log("✅ 心跳按钮已点击")
                return True
        except Exception:
            continue
            
    # JavaScript 强力兜底点击
    log("⚠️ 尝试使用 JavaScript 兜底查找并点击心跳按钮...")
    js_click_script = """
    (() => {
        const buttons = Array.from(document.querySelectorAll('button, a, div[role="button"]'));
        for (const b of buttons) {
            const txt = (b.innerText || b.textContent || '').trim();
            if (txt.includes('心跳') || txt.toLowerCase().includes('heartbeat') || txt.includes('+1天') || txt.includes('+1 day')) {
                b.scrollIntoView({ behavior: 'smooth', block: 'center' });
                b.click();
                return txt;
            }
        }
        return null;
    })();
    """
    try:
        res = sb.execute_script(js_click_script)
        if res:
            log(f"✅ 已通过 JS 触发心跳按钮点击: '{res}'")
            return True
    except Exception as e:
        log(f"JS 点击心跳按钮出错: {e}")

    return False

# ==================== 主续期流程 ====================
def run_renew():
    log("==========================================")
    log("🚀 Kerit Cloud 自动续期任务启动")
    log("==========================================")
    
    # 代理状态与出口 IP
    if IS_PROXY:
        log(f"🌐 代理已开启: {PROXY_SERVER}")
    else:
        log("🌐 代理未开启（直连访问）")
    current_ip = get_current_ip()
    log(f"📍 当前出口 IP: {current_ip}")
    log(f"👤 当前账号: {mask_email(EMAIL)}")

    if not EMAIL or not PASSWORD:
        log("❌ 错误: 未设置 KERIT_EMAIL 或 KERIT_PASSWORD，终止执行！")
        sys.exit(1)

    # 启动浏览器 (SeleniumBase UC 模式)
    proxy_arg = PROXY_SERVER if IS_PROXY else None
    
    with SB(uc=True, proxy=proxy_arg, incognito=True, test=False) as sb:
        # 设置窗口分辨率
        sb.set_window_size(1920, 1080)
        
        # -------------------- 第 1 步：访问登录页面 --------------------
        log(f"🔗 正在访问登录页: {LOGIN_URL}")
        try:
            sb.uc_open_with_reconnect(LOGIN_URL, reconnect_time=4)
        except Exception as e:
            log(f"⚠️ 打开登录页发生异常，尝试常规打开: {e}")
            sb.open(LOGIN_URL)
        
        sb.sleep(4)
        sb.save_screenshot("01_login_page.png")
        log(f"📄 当前页面标题: {sb.get_title()} | URL: {sb.get_current_url()}")

        # 检查是否已经是登录状态（如被记住登录）
        current_url = sb.get_current_url()
        is_already_logged_in = "/dashboard" in current_url or "/services" in current_url
        
        if not is_already_logged_in:
            log("📝 正在输入账号密码...")
            try:
                # 等待输入框加载
                sb.wait_for_element_visible("#login-email", timeout=15)
                sb.type("#login-email", EMAIL)
                time.sleep(0.5)
                
                sb.wait_for_element_visible("#p-login", timeout=15)
                sb.type("#p-login", PASSWORD)
                time.sleep(0.5)

                # 勾选信任此设备（延长会话）
                if sb.is_element_present("#login-trust"):
                    try:
                        if not sb.is_checked("#login-trust"):
                            sb.click("#login-trust")
                            log("🔒 已勾选 '信任此设备'")
                    except Exception:
                        pass
                
                # 尝试处理页面可能存在的 Cloudflare Turnstile
                try:
                    sb.uc_gui_handle_captcha()
                except Exception:
                    pass

                time.sleep(1)
                log("🖱️ 点击登录按钮...")
                sb.click("#login-btn")
                
            except Exception as e:
                log(f"❌ 输入账号密码或点击登录失败: {e}")
                sb.save_screenshot("01_login_failed.png")
                send_telegram_notification("❌ 登录异常", "", "", note=f"输入账号密码出错: {e}")
                sys.exit(1)

            # 等待登录结果与跳转
            log("⏳ 正在等待登录跳转验证...")
            login_success = False
            for i in range(25):
                sb.sleep(1)
                cur_url = sb.get_current_url()
                if "/dashboard" in cur_url or "/services" in cur_url:
                    login_success = True
                    log(f"🎉 登录成功！已跳转至: {cur_url}")
                    break
                # 检查错误提示
                if sb.is_element_visible("#login-error"):
                    err_txt = sb.get_text("#login-error")
                    if err_txt:
                        log(f"❌ 登录返回错误: {err_txt}")
                        sb.save_screenshot("01_login_error_banner.png")
                        send_telegram_notification("❌ 登录失败", "", "", note=f"平台提示: {err_txt}")
                        sys.exit(1)

            if not login_success:
                log("⚠️ 未能完成登录跳转，保存当前页面截图...")
                sb.save_screenshot("02_login_stuck.png")
                page_txt = sb.get_text("body")
                if "2FA" in page_txt or "双重认证" in page_txt:
                    log("❌ 账号开启了 2FA 双重认证，无法全自动登录，请先关闭 2FA 或使用会话 Token")
                    send_telegram_notification("❌ 登录失败", "", "", note="检测到 2FA 双重认证，请关闭 2FA")
                    sys.exit(1)
                send_telegram_notification("❌ 登录超时", "", "", note="未能成功登录并跳转至仪表板")
                sys.exit(1)

        sb.save_screenshot("02_after_login.png")

        # -------------------- 第 2 步：进入免费工坊 (Free Hosting) 页面 --------------------
        log(f"🔗 正在导航至免费工坊页面: {FREE_HOSTING_URL}")
        try:
            sb.uc_open_with_reconnect(FREE_HOSTING_URL, reconnect_time=3)
        except Exception:
            sb.open(FREE_HOSTING_URL)

        sb.sleep(6)
        sb.save_screenshot("03_free_hosting_page.png")
        log(f"📄 当前页面: {sb.get_title()} | URL: {sb.get_current_url()}")

        # 提取当前服务器状态和剩余时间
        old_due = extract_remaining_time(sb)
        count_info = extract_heartbeat_count(sb)
        log(f"📊 续期前剩余有效时间: {old_due}")
        if count_info:
            log(f"📈 今日已发送心跳: {count_info}")

        # 检查是否冷却中或不可续期
        body_text = sb.get_text("body")
        if "心跳间隔需大于" in body_text and ("请稍后" in body_text or "冷却中" in body_text):
            log("⏳ 当前处于心跳冷却期，暂无需重复发送心跳。")
            send_telegram_notification("⏳ 心跳冷却中", old_due, old_due, count_info, "当前时间未满1小时间隔，无需重复续期")
            return

        # -------------------- 第 3 步：处理 hCaptcha 人机验证 --------------------
        handle_captcha_checkbox(sb)
        sb.sleep(3)
        sb.save_screenshot("04_before_heartbeat.png")

        # -------------------- 第 4 步：点击 发送心跳 按钮 --------------------
        clicked = find_and_click_heartbeat_button(sb)
        if not clicked:
            log("❌ 未能成功点击心跳按钮")
            sb.save_screenshot("04_heartbeat_click_failed.png")
            send_telegram_notification("❌ 续期失败", old_due, old_due, count_info, "未能找到或点击'发送心跳'按钮")
            sys.exit(1)

        log("⏳ 已点击心跳按钮，等待服务端确认与页面数据刷新 (8秒)...")
        sb.sleep(8)
        sb.save_screenshot("05_after_heartbeat.png")

        # -------------------- 第 5 步：确认续期结果 --------------------
        new_due = extract_remaining_time(sb)
        new_count_info = extract_heartbeat_count(sb)
        after_body = sb.get_text("body")
        log(f"📊 续期后剩余有效时间: {new_due}")
        if new_count_info:
            log(f"📈 续期后今日心跳: {new_count_info}")

        # 判断依据：时间变长，或者心跳计数增加，或者页面提示成功
        has_time_increased = (old_due != "未知" and new_due != "未知" and old_due != new_due)
        has_count_increased = (count_info and new_count_info and count_info != new_count_info)
        has_success_toast = ("成功" in after_body or "success" in after_body.lower() or "+1" in after_body)

        if has_time_increased or has_count_increased or has_success_toast:
            log("🎉🎉🎉 恭喜！心跳发送成功，托管有效期已延长 +1 天！")
            send_telegram_notification(
                "✅ 续期成功 (+1天)",
                old_due,
                new_due if new_due != "未知" else "已延长+1天",
                new_count_info or count_info,
                "心跳信号已成功送达，Discord 机器人托管维持运行中"
            )
        else:
            log("⚠️ 剩余时间未发生明显变化，可能处于1小时冷却期或今日次数已达上限")
            send_telegram_notification(
                "⏳ 续期完毕 (待观察)",
                old_due,
                new_due,
                new_count_info or count_info,
                "心跳按钮已成功点击，但剩余时间未即时刷新，请查看 GitHub 运行截图"
            )

        log("==========================================")
        log("🏁 任务完成，正常退出")
        log("==========================================")

if __name__ == "__main__":
    try:
        run_renew()
    except Exception as e:
        log(f"❌ 运行发生未捕获异常: {e}")
        send_telegram_notification("❌ 任务异常终止", "", "", note=str(e))
        sys.exit(1)
