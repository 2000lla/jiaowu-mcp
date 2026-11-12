"""WebVPN 扫码登录 -> 教务系统登录 -> 保存会话(含资源前缀)。

凭证来源优先级:
    1. 环境变量 JWC_USER / JWC_PASS
    2. 本地 config.local.json 的 user / password 字段
    3. 交互式输入(仅在本机终端运行时)

学校地址等环境信息全部来自 config.local.json, 代码不含任何硬编码标识。

用法:
    .venv/bin/python login_once.py           # 有会话先复用, 失效再扫码
    .venv/bin/python login_once.py --force   # 强制重新扫码
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import sys
import time

from selenium.webdriver.common.by import By

import jwcore as base

SESSION = base.SESSION
CONFIG = base.HERE / "config.local.json"
PROFILE = str(base.HERE / ".chrome-profile")
DBG = base.OUT / "debug"


def load_config() -> dict:
    if not CONFIG.exists():
        sys.exit(f"缺少配置文件 {CONFIG.name}\n"
                 '内容示例: {"vpn_base": "https://...", "resource_name": "教务系统",'
                 ' "jwxt_host": "jwxt.example.edu.cn"}')
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    for key in ("vpn_base", "resource_name"):
        if not cfg.get(key):
            sys.exit(f"{CONFIG.name} 缺少字段: {key}")
    cfg["vpn_base"] = cfg["vpn_base"].rstrip("/")
    return cfg


def load_credentials(cfg: dict) -> tuple[str, str]:
    user = os.environ.get("JWC_USER") or cfg.get("user")
    pwd = os.environ.get("JWC_PASS") or cfg.get("password")
    if user and pwd:
        return user, pwd
    if sys.stdin.isatty():
        if not user:
            user = input("教务系统账号: ").strip()
        if not pwd:
            pwd = getpass.getpass("教务系统密码: ")
        return user, pwd
    raise SystemExit("需要账号密码: 设置环境变量 JWC_USER / JWC_PASS, "
                     "或在 config.local.json 填 user / password")


def _driver_path() -> str | None:
    """跨平台定位 chromedriver: 环境变量 > 本地目录 > 交给 Selenium Manager。"""
    env = os.environ.get("CHROMEDRIVER")
    if env and os.path.exists(env):
        return env
    for p in (base.HERE / "chromedriver-mac-arm64" / "chromedriver",
              base.HERE / "chromedriver-mac-x64" / "chromedriver",
              base.HERE / "chromedriver-win64" / "chromedriver.exe",
              base.HERE / "chromedriver" / "chromedriver"):
        if p.exists():
            return str(p)
    return None


def build_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    o = Options()
    o.add_argument(f"--user-data-dir={PROFILE}")
    o.add_argument("--window-size=1280,1000")
    o.add_argument("--lang=zh-CN")
    o.add_argument("--no-first-run")
    o.add_argument("--no-default-browser-check")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    path = _driver_path()
    service = Service(executable_path=path) if path else Service()
    d = webdriver.Chrome(service=service, options=o)
    d.set_page_load_timeout(60)
    return d


def save_session(d, cfg: dict, prefix: str) -> dict:
    jar = {
        "saved_at": dt.datetime.now().isoformat(timespec="seconds"),
        "vpn_base": cfg["vpn_base"],
        "prefix": prefix,
        "cookies": d.get_cookies(),
    }
    SESSION.write_text(json.dumps(jar, ensure_ascii=False, indent=2), encoding="utf-8")
    SESSION.chmod(0o600)
    return jar


def load_cookies(d, cfg: dict) -> bool:
    if not SESSION.exists():
        return False
    try:
        jar = json.loads(SESSION.read_text(encoding="utf-8"))
    except Exception:
        return False
    cookies = jar.get("cookies") or []
    if not cookies:
        return False

    d.get(cfg["vpn_base"] + "/")
    time.sleep(1)
    now = time.time()
    added = 0
    for c in cookies:
        ck = {k: v for k, v in c.items()
              if k in ("name", "value", "domain", "path", "secure", "httpOnly")}
        if c.get("expiry") and c["expiry"] < now:
            continue
        try:
            d.add_cookie(ck)
            added += 1
        except Exception:
            pass
    print(f"  注入 {added}/{len(cookies)} 条 cookie")
    d.get(cfg["vpn_base"] + "/")
    time.sleep(3)
    return "/login" not in d.current_url


def qr_login(d, cfg: dict) -> None:
    d.get(cfg["vpn_base"] + "/login")
    time.sleep(2)
    if "/login" not in d.current_url:
        print("✓ 已有 VPN 登录态")
        return
    print("=" * 62)
    print("请用【手机企业微信】扫描浏览器窗口里的二维码")
    print("=" * 62, flush=True)
    for _ in range(150):
        if "/login" not in d.current_url:
            print("✓ 扫码成功", flush=True)
            time.sleep(2)
            return
        time.sleep(2)
    raise SystemExit("✗ 等待扫码超时")


def click_resource(d, cfg: dict) -> None:
    d.get(cfg["vpn_base"] + "/")
    time.sleep(3)
    before = set(d.window_handles)
    name = cfg["resource_name"]
    r = d.execute_script(r"""
        var name = arguments[0];
        var els = Array.from(document.querySelectorAll('a,div,li')).filter(function(e){
            var t = (e.innerText || '').trim();
            var r = e.getBoundingClientRect();
            return t && t.length < 40 && t.indexOf(name) >= 0 && r.width > 0;
        });
        if (!els.length) return 'no_match';
        els.sort(function(a,b){ return a.innerText.length - b.innerText.length; });
        els[0].click();
        return 'clicked';
    """, name)
    print(f"  点击「{name}」: {r}", flush=True)
    time.sleep(5)
    for h in d.window_handles:
        if h not in before:
            d.switch_to.window(h)
            break
    else:
        if len(d.window_handles) > 1:
            d.switch_to.window(d.window_handles[-1])
    time.sleep(1)


def jwxt_login(d, cfg: dict) -> bool:
    if not d.find_elements(By.ID, "yhm"):
        print(f"  ✓ 教务已处于登录态: {d.title.strip()}", flush=True)
        return True

    user, pwd = load_credentials(cfg)
    print("  输入账号密码登录教务系统...", flush=True)
    el = d.find_element(By.ID, "yhm")
    el.clear()
    el.send_keys(user)
    el = d.find_element(By.ID, "mm")
    el.clear()
    el.send_keys(pwd)

    fixed = d.execute_script(r"""
        var f = document.querySelector('form');
        var p = location.pathname, i = p.indexOf('/jwglxt/');
        if (i < 0 || !f) return 'skip';
        f.action = location.origin + p.substring(0, i) +
                   '/jwglxt/xtgl/login_slogin.html' + (location.search || '');
        return f.action;
    """)
    print(f"  提交地址: {fixed}", flush=True)
    try:
        d.find_element(By.ID, "dl").click()
    except Exception:
        d.execute_script("document.querySelector('form').submit();")
    time.sleep(6)

    if d.find_elements(By.ID, "yhm"):
        tip = d.execute_script(
            "var e=document.querySelector('#tips');return e?e.innerText.trim():'';")
        print(f"  ✗ 登录失败: {tip or '仍在登录页'}", flush=True)
        return False
    print(f"  ✓ 教务登录成功: {d.title.strip()}", flush=True)
    return True


def current_prefix(d) -> str:
    """从当前 jwglxt 页地址截出 WebVPN 资源前缀。"""
    url = d.current_url
    i = url.find("/jwglxt/")
    if i < 0:
        return ""
    return url[:i]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="强制重新扫码")
    args = ap.parse_args()

    cfg = load_config()
    d = build_driver()
    try:
        ok = False
        if not args.force:
            print("尝试复用已有会话...")
            ok = load_cookies(d, cfg)

        if not ok:
            qr_login(d, cfg)

        click_resource(d, cfg)
        print(f"  当前页: {d.title.strip()}", flush=True)

        # 先落盘一次: 即使后面教务登录失败(如缺账号密码), 扫码拿到的票据也不白费
        prefix = current_prefix(d)
        save_session(d, cfg, prefix)

        if not jwxt_login(d, cfg):
            DBG.mkdir(parents=True, exist_ok=True)
            (DBG / "login_failed.html").write_text(d.page_source, encoding="utf-8")
            raise SystemExit(1)

        prefix = current_prefix(d) or prefix
        if not prefix:
            print("  ! 未能识别资源前缀, 会话文件将缺少 prefix 字段", flush=True)
        jar = save_session(d, cfg, prefix)
        DBG.mkdir(parents=True, exist_ok=True)
        d.save_screenshot(str(DBG / "login_ok.png"))

        print("\n" + "=" * 62)
        print("✓ 登录成功, 会话已保存")
        print(f"  文件: {SESSION}")
        print(f"  cookie 数: {len(jar['cookies'])}")
        print(f"  资源前缀: {prefix[:80]}{'...' if len(prefix) > 80 else ''}")
        print("=" * 62)
    finally:
        time.sleep(1)
        d.quit()


if __name__ == "__main__":
    main()
