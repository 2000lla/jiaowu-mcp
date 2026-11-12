"""无窗口扫码登录: 企业微信二维码渲染成本地图片, 浏览器全程 headless。

流程:
    1. 后台启动无头 Chrome 打开 WebVPN 登录页
    2. 从页面里取出企业微信登录 iframe 的 URL, 用 segno 渲染成 PNG
    3. 由调用方把图片展示给用户扫码
    4. 轮询 cookie, 拿到 wengine_vpn_ticket 即登录成功
    5. 打开教务系统入口取资源前缀, 完成教务登录, 写入 .session.json
    6. 关闭浏览器, 后续全部走纯 HTTP

用法:
    .venv/bin/python qr_login.py           # 生成二维码并等待扫码
    .venv/bin/python qr_login.py --headful # 调试时显示窗口
"""
from __future__ import annotations

import argparse
import json
import time

from selenium.webdriver.common.by import By

import login_once as L
import jwcore as core

QR_PNG = core.OUT / "qr_login.png"
QR_URL_TXT = core.OUT / "qr_login_url.txt"


def build_driver(mode: str):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    o = Options()
    if mode == "headless":
        # 注意: 企业微信扫码的 OAuth 回跳在纯 headless 下无法完成
        o.add_argument("--headless=new")
        o.add_argument("--no-sandbox")
        o.add_argument("--disable-gpu")
        o.add_argument("--window-size=1280,900")
    elif mode == "hidden":
        # 有界面但移到屏幕外, 用户看不到窗口, 同时保留完整浏览器行为
        o.add_argument("--window-position=-3200,0")
        o.add_argument("--window-size=520,900")
    else:
        o.add_argument("--window-size=1280,900")
    o.add_argument("--lang=zh-CN")
    o.add_argument(f"--user-data-dir={L.PROFILE}")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    path = L._driver_path()
    service = Service(executable_path=path) if path else Service()
    d = webdriver.Chrome(service=service, options=o)
    d.set_page_load_timeout(60)
    return d


def grab_qr_url(d, timeout: float = 25) -> str:
    """等企业微信 iframe 出现, 取它的 src。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        src = d.execute_script(r"""
            var f = document.querySelector('iframe[src*="qrConnect"], iframe[src*="wwopen"]');
            return f ? f.src : '';
        """)
        if src:
            return src
        time.sleep(0.5)
    raise SystemExit("✗ 没等到企业微信二维码 iframe")


def capture_qr(d) -> None:
    """截取企业微信 iframe 区域, 拿到真正可扫的二维码。

    iframe 是 open.work.weixin.qq.com 的同源策略对象, 读不到它的 DOM,
    只能靠截图裁剪。"""
    from PIL import Image

    rect = d.execute_script(r"""
        var f = document.querySelector('iframe[src*="qrConnect"], iframe[src*="wwopen"]');
        if (!f) return null;
        var r = f.getBoundingClientRect();
        return {x: r.x, y: r.y, w: r.width, h: r.height,
                vw: window.innerWidth, vh: window.innerHeight};
    """)
    if not rect or not rect.get("w"):
        raise SystemExit("✗ 没找到企业微信二维码区域")

    core.OUT.mkdir(parents=True, exist_ok=True)
    tmp = core.OUT / "_qr_full.png"
    d.save_screenshot(str(tmp))
    im = Image.open(tmp)
    scale = im.width / rect["vw"]          # 处理 Retina 缩放
    pad = 6
    box = (max(0, int((rect["x"] - pad) * scale)),
           max(0, int((rect["y"] - pad) * scale)),
           min(im.width, int((rect["x"] + rect["w"] + pad) * scale)),
           min(im.height, int((rect["y"] + rect["h"] + pad) * scale)))
    im.crop(box).save(QR_PNG)
    tmp.unlink(missing_ok=True)
    QR_URL_TXT.write_text(d.current_url, encoding="utf-8")


def wait_authed(d, timeout: float = 75) -> bool:
    """扫码后页面会自己完成授权跳转, 必须等它跳完, 中途不要导航。"""
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        url = d.current_url or ""
        if url != last:
            last = url
            print(f"    · {url[:80]} | cookies={len(d.get_cookies())}", flush=True)
        if "/login" not in url:
            time.sleep(2)
            return True
        time.sleep(1)
    return False


def wait_ticket(d, timeout: float = 300) -> dict:
    """轮询 cookie, 等到 WebVPN 票据出现。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for c in d.get_cookies():
            if c.get("name", "").startswith("wengine_vpn_ticket") and c.get("value"):
                return c
        time.sleep(2)
    raise SystemExit("✗ 等待扫码超时")


def inject_saved(d, cfg: dict) -> bool:
    """把 .session.json 里的票据注入浏览器, 避免重复扫码。"""
    if not core.SESSION.exists():
        return False
    try:
        jar = json.loads(core.SESSION.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not any(c.get("name", "").startswith("wengine_vpn_ticket")
               for c in jar.get("cookies", [])):
        return False
    d.get(cfg["vpn_base"] + "/")
    time.sleep(1)
    for c in jar.get("cookies", []):
        ck = {k: v for k, v in c.items()
              if k in ("name", "value", "domain", "path", "secure", "httpOnly")}
        try:
            d.add_cookie(ck)
        except Exception:
            pass
    d.get(cfg["vpn_base"] + "/")
    time.sleep(2)
    return "/login" not in d.current_url


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="hidden",
                    choices=["hidden", "headless", "visible"],
                    help="hidden=窗口移到屏幕外(默认), headless=纯无头, visible=正常窗口")
    ap.add_argument("--from-session", action="store_true",
                    help="复用 .session.json 里的票据, 只补全前缀与教务登录")
    ap.add_argument("--timeout", type=float, default=300)
    args = ap.parse_args()

    cfg = L.load_config()
    d = build_driver(args.mode)
    try:
        if args.from_session and inject_saved(d, cfg):
            print("✓ 已复用本地票据, 跳过扫码", flush=True)
        else:
            d.get(cfg["vpn_base"] + "/login")
            time.sleep(2)
            grab_qr_url(d)                 # 等 iframe 出现
            time.sleep(2)                  # 等二维码渲染完
            capture_qr(d)
            print(f"QR_READY {QR_PNG}", flush=True)
            # 登录页在扫码前就种了 wengine_vpn_ticket(pre-auth), 不能拿它当成功信号;
            # 真正的成功标志是页面离开 /login
            if not wait_authed(d, args.timeout):
                raise SystemExit("✗ 等待扫码超时")
            cookies = d.get_cookies()
            ticket = next((c for c in cookies
                           if c["name"].startswith("wengine_vpn_ticket")), None)
            print(f"✓ 授权完成: {d.current_url[:60]} | cookies={len(cookies)}",
                  flush=True)
            if not ticket:
                raise SystemExit("✗ 授权后未找到票据 cookie")
        L.click_resource(d, cfg)
        prefix = L.current_prefix(d)
        if not prefix:
            raise SystemExit("✗ 未取得资源前缀")
        L.save_session(d, cfg, prefix)
        print(f"✓ 已进入教务系统, 前缀 {prefix[:60]}...", flush=True)

        if not L.jwxt_login(d, cfg):
            raise SystemExit("✗ 教务登录失败")
        L.save_session(d, cfg, L.current_prefix(d) or prefix)
        print("✓ 会话已保存", flush=True)
    finally:
        d.quit()


if __name__ == "__main__":
    main()
