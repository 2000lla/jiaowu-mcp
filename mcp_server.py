"""教务系统课表 MCP 服务 (stdio)。

设计原则:
    - 只用 cookie 走纯 HTTP, 不启动浏览器, 不依赖 Selenium/WebDriver
    - 仅依赖 Python 标准库 + mcp, 全平台可用
    - 不含任何硬编码账号、令牌、学校地址

凭证文件: jiaowu/.session.json
    {"prefix": "https://<vpn>/https/<token>", "cookies": [{"name": ..., "value": ...}]}

首次使用或票据过期时, 用 import_session 工具导入从浏览器拿到的 cookie,
或在任意平台跑一次 login_once.py 生成该文件。

启动: .venv/bin/python mcp_server.py
"""
from __future__ import annotations

import datetime as dt
import json

from mcp.server.mcpserver import MCPServer

import fetch_schedule as fs

server = MCPServer(
    name="jiaowu",
    instructions=(
        "教务系统课表服务(纯 HTTP, 无浏览器)。"
        "先用 session_status 检查会话是否有效; 失效时提示用户通过 import_session 导入 cookie。"
    ),
)


def _err(exc: Exception) -> dict:
    return {
        "ok": False,
        "error": str(exc),
        "hint": "会话不可用: 请调用 import_session 导入浏览器 cookie",
        "need_session": True,
    }


@server.tool(
    name="get_schedule",
    description=(
        "获取本人课表(纯 HTTP, 无浏览器)。term 形如 '2026-1' 表示 2026-2027 学年第1学期, "
        "省略则按当前日期推断。返回课程列表: 课程/教师/地点/星期/节次/周次。"
    ),
)
def get_schedule(term: str | None = None) -> dict:
    try:
        return {"ok": True, **fs.get_schedule(term)}
    except fs.SessionExpired as exc:
        return _err(exc)


@server.tool(
    name="session_status",
    description="检查本地保存的 cookie 是否仍可用, 并返回学生信息、当前学期和课程条数。",
)
def session_status() -> dict:
    if not fs.SESSION.exists():
        return {"ok": False, "valid": False, "error": "本地没有会话文件",
                "hint": "调用 import_session 导入 cookie"}
    try:
        data = fs.get_schedule(None)
    except fs.SessionExpired as exc:
        return {"ok": False, "valid": False, "error": str(exc),
                "hint": "调用 import_session 重新导入 cookie"}
    return {
        "ok": True,
        "valid": True,
        "学生": data["学生"],
        "学期": data["学期名称"],
        "课程数": data["课程数"],
        "会话文件": str(fs.SESSION),
    }


def _parse_cookie(raw: str) -> list[dict]:
    """支持: 裸票据值 / 'name=value; name2=value2' / JSON 数组。"""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("cookie 为空")
    if raw.startswith("["):
        jar = json.loads(raw)
        if not isinstance(jar, list):
            raise ValueError("JSON 需是 cookie 数组")
        return jar

    if "=" not in raw:
        try:
            old = json.loads(fs.SESSION.read_text(encoding="utf-8"))
            for c in old.get("cookies", []):
                if c.get("name", "").startswith(fs.TICKET_PREFIX):
                    return [{"name": c["name"], "value": raw}]
        except Exception:
            pass
        raise ValueError("只给票据值时无法确定 cookie 名, 请传 name=value 形式")

    out = []
    for part in raw.replace("\n", ";").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out.append({"name": k.strip(), "value": v.strip()})
    return out


@server.tool(
    name="import_session",
    description=(
        "导入会话 cookie(纯 HTTP, 无浏览器)。cookie 可传 'name=value' 形式、"
        "浏览器复制的整条 cookie 字符串, 或只传票据值。prefix 传浏览器地址栏中 "
        "'/jwglxt/' 之前的完整地址; 省略则沿用已有会话里的前缀。导入后会立即校验。"
    ),
)
def import_session(cookie: str, prefix: str | None = None) -> dict:
    try:
        cookies = _parse_cookie(cookie)
    except Exception as exc:
        return {"ok": False, "error": f"cookie 解析失败: {exc}"}

    prefix = (prefix or "").strip().rstrip("/")
    if not prefix:
        try:
            prefix = json.loads(fs.SESSION.read_text(encoding="utf-8")).get("prefix", "")
        except Exception:
            prefix = ""
    if not prefix:
        return {"ok": False,
                "error": "缺少 prefix",
                "hint": "请传浏览器地址栏里 /jwglxt/ 之前的完整地址"}

    jar = {
        "saved_at": dt.datetime.now().isoformat(timespec="seconds"),
        "prefix": prefix,
        "cookies": cookies,
    }

    # 先校验再落盘: 坏 cookie 不得覆盖掉原本可用的会话
    import jwcore as core
    xnm, xqm = core.current_term()
    try:
        raw = fs.fetch_raw(xnm, xqm, sess=jar)
    except fs.SessionExpired as exc:
        return {"ok": False, "saved": False,
                "error": f"凭证校验失败, 未写入: {exc}",
                "hint": "请确认 cookie 未过期, 且 prefix 与浏览器地址栏一致"}

    fs.SESSION.write_text(json.dumps(jar, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        fs.SESSION.chmod(0o600)
    except OSError:
        pass  # Windows 等平台可能不支持, 忽略

    xs = raw.get("xsxx") or {}
    courses = [c for c in (core.normalize(x) for x in (raw.get("kbList") or []))
               if c["课程"]]
    return {
        "ok": True,
        "saved": True,
        "学生": {"姓名": xs.get("XM", ""), "学号": xs.get("XH", ""),
                 "班级": xs.get("BJMC", ""), "专业": xs.get("ZYMC", "")},
        "学期": core.term_label(xnm, xqm)[0],
        "课程数": len(courses),
    }


@server.tool(
    name="query_info",
    description=(
        "「信息查询」下的各项功能(纯 HTTP, 无浏览器)。feature 取值见 list_features; "
        "term 形如 '2026-1', 省略则用当前学期; date 仅「查询空闲教室」需要, 形如 2026-11-13。"
    ),
)
def query_info(feature: str, term: str | None = None,
               date: str | None = None) -> dict:
    import modules as M
    if feature not in M.REGISTRY:
        return {"ok": False, "error": f"不支持的功能: {feature}",
                "available": list(M.REGISTRY)}
    kwargs: dict = {}
    if term:
        kwargs["term"] = term
    if date and feature == "查询空闲教室":
        kwargs["date"] = date
    try:
        res = M.run(feature, **kwargs)
    except fs.SessionExpired as exc:
        return _err(exc)
    if not res.get("ok") and res.get("need_session"):
        return _err(RuntimeError(res.get("error", "")))
    return res


@server.tool(
    name="list_features",
    description="列出「信息查询」下已支持的功能名称, 供 query_info 使用。",
)
def list_features() -> dict:
    import modules as M
    return {"ok": True, "功能": list(M.REGISTRY)}


if __name__ == "__main__":
    server.run(transport="stdio")
