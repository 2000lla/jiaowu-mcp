"""「信息查询」各功能的纯 HTTP 实现。

每个函数返回 dict:
    {"ok": True,  "data": ...}
    {"ok": False, "error": "..."}

接口均通过 WebVPN cookie 访问, 不依赖浏览器。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

import fetch_schedule as fs

DEFAULT_XNM, DEFAULT_XQM = None, None


# ---------------------------------------------------------------- 基础请求
def _request(path: str, data: dict | None = None) -> tuple[int, str]:
    sess = fs._load_session()
    url = fs._prefix(sess) + "/jwglxt" + path
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body)
        req.add_header("Content-Type",
                       "application/x-www-form-urlencoded; charset=UTF-8")
    else:
        req = urllib.request.Request(url)
    req.add_header("Cookie", f"{fs._ticket_name(sess)}={fs._ticket(sess)}")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/157.0.0.0 Safari/537.36")
    try:
        with urllib.request.urlopen(req, context=fs._ssl_ctx(), timeout=30) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "ignore")


def _term(term: str | None) -> tuple[str, str]:
    import jwcore as core
    return core.parse_term_arg(term) if term else core.current_term()


def _grid(path: str, extra: dict | None = None, rows: int = 200) -> dict:
    """jqGrid 风格的分页查询, 自动翻页取全。"""
    xnm, xqm = _term(None)
    base_params = {"rows": str(rows), "sidx": "", "sord": "asc",
                   "xnm": xnm, "xqm": xqm}
    if extra:
        base_params.update({k: v for k, v in extra.items() if v is not None})

    merged: dict = {}
    page = 1
    while page <= 20:
        params = dict(base_params, page=str(page))
        code, body = _request(path, params)
        body = body.strip()
        if not body.startswith("{"):
            return {"error": f"HTTP {code}: {body[:120]}"}
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return {"error": "JSON 解析失败"}
        items = data.get("items") or []
        total = data.get("totalCount")
        if not merged:
            merged = data
        elif items:
            merged.setdefault("items", []).extend(items)
        if not items:
            break
        if isinstance(total, int) and len(merged.get("items") or []) >= total:
            break
        if len(items) < int(base_params["rows"]):
            break
        page += 1
    return merged


def _grid_for(path: str, term: str | None, extra: dict | None = None,
              rows: int = 300) -> dict:
    """带指定学期的分页查询。"""
    import jwcore as core
    xnm, xqm = core.parse_term_arg(term) if term else core.current_term()
    params = {"xnm": xnm, "xqm": xqm}
    if extra:
        params.update(extra)
    # 临时复用 _grid 的翻页逻辑
    merged: dict = {}
    page = 1
    while page <= 20:
        body_params = dict(params, page=str(page), rows=str(rows),
                           sidx="", sord="asc")
        code, body = _request(path, body_params)
        body = body.strip()
        if not body.startswith("{"):
            return {"error": f"HTTP {code}: {body[:120]}"}
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return {"error": "JSON 解析失败"}
        items = data.get("items") or []
        if not merged:
            merged = data
        elif items:
            merged.setdefault("items", []).extend(items)
        total = data.get("totalCount")
        if not items or (isinstance(total, int) and
                         len(merged.get("items") or []) >= total):
            break
        if len(items) < rows:
            break
        page += 1
    return merged


def _index_html(gnmkdm: str, path: str) -> str:
    sep = "&" if "?" in path else "?"
    code, html = _request(f"{path}{sep}gnmkdm={gnmkdm}")
    return html if code == 200 else ""


# ---------------------------------------------------------------- 各功能
def personal_info() -> dict:
    """查询个人信息: 解析页面上的静态文本。"""
    html = _index_html("N100801", "/xsxxxggl/xsgrxxwh_cxXsgrxx.html")
    if not html:
        return {"ok": False, "error": "页面加载失败"}
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    fields = {
        "姓名": r"姓名：\s*([^\s]+)",
        "学号": r"学号：\s*(\d+)",
        "性别": r"性别：\s*([^\s]+)",
        "出生日期": r"出生日期：\s*([\d-]+)",
        "民族": r"民族：\s*([^\s]+)",
        "政治面貌": r"政治面貌：\s*([^\s]+)",
        "年级": r"年级：\s*([^\s]+)",
        "学院": r"学院名称：\s*([^\s]+)",
        "专业": r"专业名称：\s*([^\s]+)",
        "班级": r"班级名称：\s*([^\s]+)",
        "入学日期": r"入学日期：\s*(\d+)",
        "学生类型": r"学生类型：\s*([^\s]+)",
    }
    out = {}
    for k, pat in fields.items():
        m = re.search(pat, text)
        if m:
            out[k] = m.group(1)
    return {"ok": True, "data": out}


def grades(term: str | None = None) -> dict:
    """学生成绩查询。"""
    data = _grid_for("/cjcx/cjcx_cxXsgrcj.html?doType=query", term, rows=300)
    if "error" in data:
        return {"ok": False, "error": data["error"]}
    items = data.get("items") or []
    clean = [{
        "课程": it.get("kcmc", ""),
        "学分": it.get("xf", ""),
        "成绩": it.get("cj", "") or it.get("bfzcj", ""),
        "绩点": it.get("jd", ""),
        "课程性质": it.get("kcxz", ""),
        "教师": it.get("jsxm", ""),
        "学年": it.get("xnmc", ""),
        "学期": it.get("xqmc", ""),
        "考试性质": it.get("ksxz", ""),
    } for it in items]
    return {"ok": True, "课程数": len(clean), "成绩": clean}


def exams(term: str | None = None) -> dict:
    """考试信息查询。"""
    data = _grid_for("/kwgl/kscx_cxXsksxxIndex.html?doType=query", term, rows=200)
    if "error" in data:
        return {"ok": False, "error": data["error"]}
    items = data.get("items") or []
    clean = [{
        "课程": it.get("kcmc", ""),
        "考试名称": it.get("ksmc", ""),
        "考试时间": it.get("kssj", ""),
        "考场": it.get("cdmc", "") or it.get("cdbh", ""),
        "座位号": it.get("zwh", ""),
        "考试方式": it.get("ksfs", ""),
    } for it in items]
    return {"ok": True, "场次": len(clean), "考试": clean}


def class_schedule(term: str | None = None) -> dict:
    """班级课表查询(返回各班级课表汇总)。"""
    data = _grid_for("/kbdy/bjkbdy_cxBjkbdyTjkbList.html", term, rows=200)
    if "error" in data:
        return {"ok": False, "error": data["error"]}
    items = data.get("items") or []
    return {"ok": True, "班级数": len(items),
            "班级": [{"班级": i.get("bjmc") or i.get("bj", "")} for i in items][:80]}


def week_schedule(term: str | None = None) -> dict:
    """学生课表查询(按周次)。"""
    data = _grid_for("/kbcx/xskbcxMobile_cxXsKb.html", term, rows=200)
    if "error" in data:
        return {"ok": False, "error": data["error"]}
    return {"ok": True, "课程数": len(data.get("kbList") or []),
            "课程": data.get("kbList") or []}


def grade_report() -> dict:
    """学生成绩总表打印(结构化总表)。"""
    data = _grid("/bysxxcx/xscjzbdy_cxXscjzbdyIndex.html?doType=query", rows=100)
    if "error" in data:
        return {"ok": False, "error": data["error"]}
    items = data.get("items") or []
    return {"ok": True, "记录数": len(items), "明细": items[:5]}


def certificate_exam() -> dict:
    """结业换证考试查询。"""
    data = _grid("/jyhzgl/ksxxcx_cxXsksxxIndex.html?doType=query", rows=100)
    if "error" in data:
        return {"ok": False, "error": data["error"]}
    items = data.get("items") or []
    return {"ok": True, "场次": len(items), "考试": items}


def free_rooms(date: str | None = None) -> dict:
    """查询空闲教室。"""
    extra = {}
    if date:
        extra["ssrq"] = date
    data = _grid("/cdjy/cdjy_cxAtyycdSchedule.html", extra or None, rows=200)
    if "error" in data:
        return {"ok": False, "error": data["error"]}
    return {"ok": True, "数据": data}



def _empty_ok(data: dict, label: str) -> dict:
    items = data.get("items") or []
    total = data.get("totalResult") or data.get("totalCount") or len(items)
    return {"ok": True, label: int(total) if isinstance(total, int) else len(items),
            "明细": items}


def student_alert(term: str | None = None) -> dict:
    """学籍预警查询。"""
    data = _grid_for("/xjyj/xjyj_cxXjyjList.html", term, rows=100)
    if "error" in data:
        return {"ok": False, "error": data["error"]}
    return _empty_ok(data, "预警数")


def academic_alert(term: str | None = None) -> dict:
    """学业预警处理查询。"""
    data = _grid_for("/xyyjjk/xyyjclcx_cxXyyjclcxxsList.html", term, rows=100)
    if "error" in data:
        return {"ok": False, "error": data["error"]}
    return _empty_ok(data, "预警数")


def academic_status(term: str | None = None) -> dict:
    """学生学业情况查询。"""
    import jwcore as core
    xnm, xqm = core.parse_term_arg(term) if term else core.current_term()
    code, body = _request("/xsxy/xsxyqk_cxJxzxjhxfyqKcxx.html?gnmkdm=N105515",
                          {"xnm": xnm, "xqm": xqm, "page": "1", "rows": "200"})
    body = body.strip()
    if code != 200:
        return {"ok": False, "error": f"HTTP {code}"}
    if body.startswith("["):
        data = json.loads(body)
        return {"ok": True, "课程数": len(data), "明细": data}
    if body.startswith("{"):
        data = json.loads(body)
        items = data.get("items") or []
        return {"ok": True, "课程数": len(items), "明细": items}
    return {"ok": False, "error": body[:100]}


def course_confirm(term: str | None = None) -> dict:
    """学生选课情况确认: 用课表里的教学班 id 去查。"""
    import jwcore as core
    xnm, xqm = core.parse_term_arg(term) if term else core.current_term()
    raw = fs.fetch_raw(xnm, xqm)
    ids = [x.get("jxb_id") for x in (raw.get("kbList") or []) if x.get("jxb_id")]
    ids = list(dict.fromkeys(ids))[:40]
    params = {"xnm": xnm, "xqm": xqm, "zjxb_ids": ",".join(ids)}
    code, body = _request("/kbcx/xskbqr_cxZjxbxx.html?gnmkdm=N2158", params)
    body = body.strip()
    if body in ("null", ""):
        return {"ok": True, "说明": "当前学期还没有可确认的选课记录", "条数": 0}
    if body.startswith("["):
        data = json.loads(body)
        return {"ok": True, "条数": len(data), "明细": data}
    if body.startswith("{"):
        data = json.loads(body)
        rows = data.get("jxbList") or data.get("items") or []
        return {"ok": True, "条数": len(rows), "明细": rows}
    return {"ok": False, "error": f"HTTP {code}: {body[:100]}"}

def personal_schedule(term: str | None = None) -> dict:
    """个人课表查询。"""
    return {"ok": True, **fs.get_schedule(term)}


# 功能注册表: 名称 -> 函数
REGISTRY = {
    "查询个人信息": personal_info,
    "学生成绩查询": grades,
    "考试信息查询": exams,
    "班级课表查询": class_schedule,
    "学生课表查询（按周次）": week_schedule,
    "学生成绩总表打印": grade_report,
    "结业换证考试查询": certificate_exam,
    "查询空闲教室": free_rooms,
    "学籍预警查询": student_alert,
    "学业预警处理查询": academic_alert,
    "学生学业情况查询": academic_status,
    "学生选课情况确认": course_confirm,
    "个人课表查询": personal_schedule,
}


def run(name: str, **kwargs) -> dict:
    fn = REGISTRY.get(name)
    if not fn:
        return {"ok": False, "error": f"未实现: {name}"}
    try:
        return fn(**kwargs)
    except fs.SessionExpired as exc:
        return {"ok": False, "error": str(exc), "need_session": True}
    except TypeError:
        return fn()
