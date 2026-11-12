"""纯 HTTP 方式获取课表 —— 不启动浏览器, 是 MCP 服务的核心实现。

所有环境相关信息(学校地址、资源前缀、票据)都来自本地 .session.json,
由 login_once.py 扫码登录时写入; 本文件不含任何硬编码标识。
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.parse
import urllib.request

import jwcore as base

SESSION = base.SESSION
TICKET_PREFIX = "wengine_vpn_ticket"
KB_PATH = "/jwglxt/kbcx/xskbcx_cxXsKb.html?gnmkdm=N2151"


class SessionExpired(RuntimeError):
    """凭证缺失或失效, 需要重新扫码。"""


def _load_session() -> dict:
    if not SESSION.exists():
        raise SessionExpired("本地没有会话文件")
    try:
        return json.loads(SESSION.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SessionExpired(f"会话文件读取失败: {exc}") from exc


def _ticket(sess: dict) -> str:
    for c in sess.get("cookies", []):
        if c.get("name", "").startswith(TICKET_PREFIX) and c.get("value"):
            return c["value"]
    raise SessionExpired("会话文件里没有 WebVPN 票据")


def _prefix(sess: dict) -> str:
    prefix = (sess.get("prefix") or "").rstrip("/")
    if not prefix:
        raise SessionExpired("会话文件缺少资源前缀")
    return prefix


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_raw(xnm: str, xqm: str, sess: dict | None = None) -> dict:
    """取课表原始 JSON。sess 可传入候选会话用于校验, 不读磁盘。"""
    sess = sess if sess is not None else _load_session()
    url = _prefix(sess) + KB_PATH
    data = urllib.parse.urlencode({"xnm": xnm, "xqm": xqm}).encode()
    req = urllib.request.Request(url, data=data)
    req.add_header("Cookie", f"{_ticket_name(sess)}={_ticket(sess)}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/157.0.0.0 Safari/537.36")
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx(), timeout=30) as r:
            body = r.read().decode("utf-8", "ignore").strip()
    except Exception as exc:
        raise SessionExpired(f"请求失败: {type(exc).__name__}") from exc

    if not body.startswith("{"):
        raise SessionExpired("接口未返回 JSON, 凭证可能已失效")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SessionExpired("JSON 解析失败") from exc

    # 会话失效时接口返回 {"success": false, "message": "...", "url": "/login"}
    # 正常响应一定带 kbList(即使为空数组), 以此判定凭证是否真的可用
    if not isinstance(data, dict) or "kbList" not in data:
        msg = data.get("message") if isinstance(data, dict) else ""
        raise SessionExpired(msg or "会话已失效, 请重新获取凭证")
    return data


def _ticket_name(sess: dict) -> str:
    for c in sess.get("cookies", []):
        if c.get("name", "").startswith(TICKET_PREFIX):
            return c["name"]
    raise SessionExpired("会话文件里没有 WebVPN 票据")


def get_schedule(term: str | None = None) -> dict:
    xnm, xqm = base.parse_term_arg(term) if term else base.current_term()
    raw = fetch_raw(xnm, xqm)

    xs = raw.get("xsxx") or {}
    courses = [c for c in (base.normalize(x) for x in (raw.get("kbList") or []))
               if c["课程"]]
    label, _ = base.term_label(xnm, xqm)
    return {
        "学年": xnm,
        "学期": 1 if xqm == "3" else 2,
        "学期名称": label,
        "学生": {
            "姓名": xs.get("XM", ""),
            "学号": xs.get("XH", ""),
            "班级": xs.get("BJMC", ""),
            "专业": xs.get("ZYMC", ""),
        },
        "课程数": len(courses),
        "课程": sorted(courses, key=lambda c: (c["星期"], c["起始节"], c["课程"])),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--term", help="学年-学期, 如 2026-1")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        data = get_schedule(args.term)
    except SessionExpired as exc:
        print(f"✗ {exc}", file=sys.stderr)
        print("  → 运行 .venv/bin/python login_once.py 重新扫码", file=sys.stderr)
        raise SystemExit(2)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    st = data["学生"]
    print(f"\n{st['姓名']}  {st['学号']}  {st['班级']}")
    base.print_console(data["课程"], data["学期名称"])
    slug = f"{data['学年']}-{data['学期']}"
    base.write_outputs(data["课程"], data["学期名称"], data["学年"],
                       "3" if data["学期"] == 1 else "12", st, slug)
    print(f"\n已保存: {base.OUT}/schedule_{slug}.json / .md")


if __name__ == "__main__":
    main()
