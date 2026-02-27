#!/usr/bin/env python3
"""
小米账号扫码登录工具

绕过"登录保护"限制，通过米家 App 扫码完成登录，
获取 service token 后写入 .env 文件供 app.py 使用。

用法:
    python qr_login.py              # 在终端显示二维码
    python qr_login.py --country cn # 指定区域（默认 cn）
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

try:
    import qrcode
except ImportError:
    print("请先安装 qrcode: pip install qrcode")
    sys.exit(1)


COUNTRY_SERVERS = {
    "cn": "https://api.io.mi.com/app",
    "de": "https://de.api.io.mi.com/app",
    "us": "https://us.api.io.mi.com/app",
    "sg": "https://sg.api.io.mi.com/app",
    "in": "https://in.api.io.mi.com/app",
    "ru": "https://ru.api.io.mi.com/app",
}

LP_TIMEOUT = 60
MAX_RETRIES = 5


def get_qr_ticket(session: requests.Session) -> dict:
    r = session.get(
        "https://account.xiaomi.com/longPolling/loginUrl",
        params={"sid": "xiaomiio", "_qrsize": "240"},
        timeout=10,
    )
    return json.loads(r.text.replace("&&&START&&&", ""))


def print_qr(url: str):
    qr = qrcode.QRCode(version=1, box_size=1, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def poll_for_scan(session: requests.Session, lp_url: str) -> dict | None:
    """Long-poll until QR is scanned or timeout."""
    start = time.time()
    attempt = 0

    while attempt < MAX_RETRIES:
        attempt += 1
        elapsed = int(time.time() - start)
        print(f"\r  等待扫码中... ({elapsed}s)", end="", flush=True)

        try:
            r = session.get(lp_url, timeout=LP_TIMEOUT)
            body = r.text.strip()

            if not body:
                continue

            if body.startswith("&&&START&&&"):
                body = body[len("&&&START&&&"):]

            data = json.loads(body)
            return data

        except requests.exceptions.Timeout:
            continue
        except json.JSONDecodeError:
            continue
        except requests.exceptions.ConnectionError:
            time.sleep(2)
            continue

    return None


def complete_login(session: requests.Session, location: str) -> dict | None:
    """Follow location URL to get service token and cookies."""
    r = session.get(location, timeout=15, allow_redirects=True)
    service_token = session.cookies.get("serviceToken")
    user_id = session.cookies.get("userId")
    ssecurity = None

    if "&ssecurity=" in location:
        import re
        m = re.search(r"ssecurity=([^&]+)", location)
        if m:
            from urllib.parse import unquote
            ssecurity = unquote(m.group(1))

    if service_token and user_id:
        return {
            "userId": user_id,
            "serviceToken": service_token,
            "ssecurity": ssecurity,
        }
    return None


def fetch_devices(session: requests.Session, tokens: dict, country: str) -> list:
    """Fetch device list to verify login works."""
    api_base = COUNTRY_SERVERS.get(country, COUNTRY_SERVERS["cn"])
    url = f"{api_base}/home/device_list"

    session.cookies.update({
        "userId": str(tokens["userId"]),
        "serviceToken": tokens["serviceToken"],
    })
    session.headers.update({
        "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
    })

    payload = json.dumps(
        {"getVirtualModel": False, "getHuamiDevices": 0},
        separators=(",", ":"),
    )
    r = session.post(url, data={"data": payload}, timeout=15)
    result = r.json()

    if result.get("code") == 0:
        return result.get("result", {}).get("list", [])
    else:
        print(f"  设备列表获取失败: code={result.get('code')}, msg={result.get('message')}")
        return []


def save_tokens_to_env(tokens: dict, country: str):
    """Save tokens to .env file."""
    env_path = Path(__file__).parent / ".env"
    lines = []

    if env_path.exists():
        lines = env_path.read_text().splitlines()

    token_vars = {
        "MIIO_SERVICE_TOKEN": tokens["serviceToken"],
        "MIIO_USER_ID": tokens["userId"],
        "MIIO_SSECURITY": tokens.get("ssecurity", ""),
        "MIIO_COUNTRY": country,
    }

    for key, value in token_vars.items():
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n")
    print(f"  已保存到 {env_path}")


def main():
    parser = argparse.ArgumentParser(description="小米账号扫码登录")
    parser.add_argument("--country", default="cn", help="区域: cn/de/us/sg (默认 cn)")
    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════╗")
    print("║     小米账号扫码登录工具             ║")
    print("╚══════════════════════════════════════╝")
    print()

    session = requests.Session()

    # Step 1: Get QR ticket
    print("[1/4] 获取二维码...")
    ticket_data = get_qr_ticket(session)
    qr_url = ticket_data.get("qr", "")
    lp_url = ticket_data.get("lp", "")

    if not qr_url or not lp_url:
        print("  错误: 无法获取二维码")
        sys.exit(1)

    # Step 2: Show QR code
    print()
    print("[2/4] 请用米家 App 扫描下方二维码:")
    print("  (米家 App → 我的 → 右上角扫一扫)")
    print()
    print_qr(qr_url)
    print()

    # Step 3: Poll for scan
    print("[3/4] 等待扫码确认...")
    scan_result = poll_for_scan(session, lp_url)
    print()

    if not scan_result:
        print("  超时: 未检测到扫码，请重新运行")
        sys.exit(1)

    code = scan_result.get("code", -1)
    if code == 3:
        print("  二维码已过期，请重新运行")
        sys.exit(1)

    location = scan_result.get("location", "")
    if not location:
        print(f"  扫码结果异常: {json.dumps(scan_result, ensure_ascii=False)[:200]}")
        sys.exit(1)

    print("  扫码成功！正在获取凭据...")

    # Step 4: Complete login
    tokens = complete_login(session, location)
    if not tokens:
        print("  错误: 无法获取 service token")
        sys.exit(1)

    print()
    print("[4/4] 登录成功!")
    print(f"  userId: {tokens['userId']}")
    print(f"  serviceToken: {tokens['serviceToken'][:20]}...")
    print()

    # Save tokens
    save_tokens_to_env(tokens, args.country)

    # Verify by fetching devices
    print()
    print("验证登录: 获取设备列表...")
    devices = fetch_devices(session, tokens, args.country)
    print(f"  找到 {len(devices)} 个设备")
    for d in devices[:10]:
        model = d.get("model", "?")
        name = d.get("name", "?")
        did = d.get("did", "?")
        print(f"    [{did}] {name} ({model})")

    if len(devices) > 10:
        print(f"    ... 还有 {len(devices) - 10} 个设备")

    print()
    print("✓ 完成! 现在可以启动 app.py，温湿度计页面将使用保存的 token 访问设备数据。")


if __name__ == "__main__":
    main()
