#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_proxy.py: 自动从环境变量 NODE_LINK 解析节点并生成 sing-box config.json 配置文件
监听 127.0.0.1:7890 (HTTP + SOCKS5 混合代理)
支持协议: trojan://, vless://, vmess://, hysteria2://, tuic://, socks5://
"""
import os
import sys
import json
import base64
import urllib.parse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def parse_node(link):
    link = (link or "").strip()
    if not link:
        raise ValueError("NODE_LINK 变量为空，未提供节点链接")
    proto = link.split("://")[0].lower()

    if proto == "trojan":
        raw = link[9:].split("#")[0]
        password, rest = raw.split("@", 1)
        if "?" in rest:
            host_port, query_str = rest.split("?", 1)
        else:
            host_port, query_str = rest, ""
        server, port_str = host_port.split(":", 1)
        params = urllib.parse.parse_qs(query_str)
        get_p = lambda k, d="": params.get(k, [d])[0]

        tls_cfg = {
            "enabled": True,
            "server_name": get_p("sni") or get_p("host") or server,
            "insecure": get_p("allowInsecure") == "1" or get_p("insecure") == "1",
        }
        if get_p("fp"):
            tls_cfg["utls"] = {"enabled": True, "fingerprint": get_p("fp")}

        outbound = {
            "type": "trojan",
            "tag": "proxy-out",
            "server": server,
            "server_port": int(port_str),
            "password": password,
            "tls": tls_cfg,
        }
        if get_p("type") == "ws":
            outbound["transport"] = {
                "type": "ws",
                "path": urllib.parse.unquote(get_p("path", "/")),
                "headers": {"Host": get_p("host") or get_p("sni") or server}
            }
        return outbound

    if proto == "vless":
        raw = link[8:]
        user_host = raw.split("#")[0]
        uuid, rest = user_host.split("@", 1)
        if "?" in rest:
            host_port, query_str = rest.split("?", 1)
        else:
            host_port, query_str = rest, ""
        server, port_str = host_port.split(":", 1)
        params = urllib.parse.parse_qs(query_str)
        get_p = lambda k, d="": params.get(k, [d])[0]

        outbound = {
            "type": "vless",
            "tag": "proxy-out",
            "server": server,
            "server_port": int(port_str),
            "uuid": uuid,
        }
        if get_p("flow"):
            outbound["flow"] = get_p("flow")
        sec = get_p("security")
        if sec == "tls":
            tls_cfg = {
                "enabled": True,
                "server_name": get_p("sni") or get_p("host") or server,
                "insecure": get_p("insecure") == "1" or get_p("allowInsecure") == "1",
            }
            if get_p("fp"):
                tls_cfg["utls"] = {"enabled": True, "fingerprint": get_p("fp")}
            outbound["tls"] = tls_cfg
        elif sec == "reality":
            outbound["tls"] = {
                "enabled": True,
                "server_name": get_p("sni") or server,
                "reality": {
                    "enabled": True,
                    "public_key": get_p("pbk"),
                    "short_id": get_p("sid"),
                },
                "utls": {"enabled": True, "fingerprint": get_p("fp", "chrome")},
            }
        if get_p("type") == "ws":
            outbound["transport"] = {
                "type": "ws",
                "path": urllib.parse.unquote(get_p("path", "/")),
                "headers": {
                    "Host": get_p("host") or get_p("sni") or server
                }
            }
        return outbound

    if proto == "vmess":
        raw_b64 = link[8:].split("#")[0]
        mod = len(raw_b64) % 4
        if mod == 2:
            raw_b64 += "=="
        elif mod == 3:
            raw_b64 += "="
        data = json.loads(base64.b64decode(raw_b64).decode("utf-8", "ignore"))
        outbound = {
            "type": "vmess",
            "tag": "proxy-out",
            "server": data.get("add", ""),
            "server_port": int(data.get("port", 443)),
            "uuid": data.get("id", ""),
            "security": data.get("scy", "auto"),
            "alter_id": int(data.get("aid", 0)),
        }
        if data.get("tls") == "tls":
            tls_cfg = {
                "enabled": True,
                "server_name": data.get("sni") or data.get("host") or data.get("add", ""),
                "insecure": False,
            }
            if data.get("ufp"):
                tls_cfg["utls"] = {"enabled": True, "fingerprint": data["ufp"]}
            outbound["tls"] = tls_cfg
        if data.get("net") == "ws":
            outbound["transport"] = {
                "type": "ws",
                "path": urllib.parse.unquote(data.get("path", "/")),
                "headers": {
                    "Host": data.get("host") or data.get("sni") or data.get("add", "")
                }
            }
        return outbound

    if proto in ("hysteria2", "hy2"):
        raw = link.split("://", 1)[1].split("#")[0]
        auth, rest = raw.split("@", 1)
        if "?" in rest:
            host_port, query_str = rest.split("?", 1)
        else:
            host_port, query_str = rest, ""
        server, port_str = host_port.split(":", 1)
        params = urllib.parse.parse_qs(query_str)
        get_p = lambda k, d="": params.get(k, [d])[0]

        outbound = {
            "type": "hysteria2",
            "tag": "proxy-out",
            "server": server,
            "server_port": int(port_str),
            "password": auth,
            "tls": {
                "enabled": True,
                "server_name": get_p("sni") or server,
                "insecure": get_p("insecure") == "1",
            }
        }
        if get_p("obfs"):
            outbound["obfs"] = {
                "type": get_p("obfs"),
                "password": get_p("obfs-password")
            }
        return outbound

    if proto == "tuic":
        raw = link[7:]
        user_host = raw.split("#")[0]
        auth, rest = user_host.split("@", 1)
        if ":" in auth:
            uuid, password = auth.split(":", 1)
        else:
            uuid, password = auth, auth
        if "?" in rest:
            host_port, query_str = rest.split("?", 1)
        else:
            host_port, query_str = rest, ""
        server, port_str = host_port.split(":", 1)
        params = urllib.parse.parse_qs(query_str)
        get_p = lambda k, d="": params.get(k, [d])[0]

        return {
            "type": "tuic",
            "tag": "proxy-out",
            "server": server,
            "server_port": int(port_str),
            "uuid": uuid,
            "password": password,
            "congestion_control": get_p("congestion_control", "bbr"),
            "udp_relay_mode": get_p("udp_relay_mode", "native"),
            "tls": {
                "enabled": True,
                "server_name": get_p("sni") or server,
                "alpn": [get_p("alpn", "h3")],
                "insecure": get_p("allow_insecure") == "1" or get_p("insecure") == "1",
            }
        }

    raise ValueError(f"不支持的节点协议: {proto}")

def generate_config(node_link=None, output_path="config.json"):
    if not node_link:
        node_link = os.environ.get("NODE_LINK", "").strip()

    if not node_link:
        print("[WARN] 未检测到环境变量 NODE_LINK，跳过 sing-box 节点配置生成")
        return None

    print("[INFO] 正在从环境变量 NODE_LINK 解析节点配置...")
    try:
        outbound = parse_node(node_link)
        print(f"[INFO] 节点解析成功: 协议={outbound['type']}, 服务器={outbound['server']}:{outbound['server_port']}")
    except Exception as e:
        print(f"[ERROR] 节点解析失败: {e}")
        sys.exit(1)

    config = {
        "log": {
            "level": "warn"
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 7890
            }
        ],
        "outbounds": [
            outbound,
            {
                "type": "direct",
                "tag": "direct"
            }
        ]
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"[INFO] sing-box 配置文件已生成: {output_path} (本地端口 127.0.0.1:7890)")
    return output_path

if __name__ == "__main__":
    generate_config()
