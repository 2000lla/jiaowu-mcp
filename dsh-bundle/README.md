# 教务课表与查询 (jiaowu)

把本地 `jiaowu/mcp_server.py` 这个 MCP 服务接入 DSH 的配置型 bundle。

## 提供的能力

| 工具 | 用途 |
|---|---|
| `get_schedule(term?)` | 个人课表 |
| `query_info(feature, term?, date?)` | 13 项教务查询：成绩、考试、个人信息、班级课表、空闲教室、选课确认、学籍/学业预警、成绩总表等 |
| `list_features()` | 列出可用查询名 |
| `session_status()` | 会话是否有效 |
| `import_session(cookie, prefix?)` | 导入浏览器 cookie 以恢复会话 |

## 前置条件

- `jiaowu/.venv` 已装好 `mcp`（`requirements-mcp.txt`）
- `jiaowu/.session.json` 存在且未过期（由 `login_once.py` 扫码生成，或用 `import_session` 导入）

## 实现方式

纯 HTTP，不启动浏览器。MCP 客户端以 stdio 方式拉起 `.venv/bin/python mcp_server.py`，
命令行与工作目录在 `cordis.patch.yml` 里指定。

## 限制

- 凭证是 WebVPN 的 session cookie，服务端超时后失效；失效时工具返回 `need_session`。
- 会话续期需要浏览器扫码，本插件不负责续期。
- 凭证只落在本机 `jiaowu/.session.json`，不外发。
