# 教务系统 MCP 服务 + DSH 插件

把学校教务系统（正方 ZFSoft，经学校 WebVPN 访问）封装成 **MCP 服务**，
并附带一个可直接安装到 [DeepSeek Harness](https://github.com/) 的配置型插件。

所有查询都是 **纯 HTTP**：不启动浏览器、不依赖 Selenium，MCP 运行期只依赖
Python 标准库和 `mcp` 包。浏览器只在首次扫码登录时用一次。

> 本项目不含任何账号、密码或会话凭证。凭证由你在本机扫码生成，保存在
> `.session.json`，已被 `.gitignore` 排除。

## 结构

```
.
├── mcp_server.py        MCP 服务（stdio）：5 个工具
├── modules.py           13 项教务查询的纯 HTTP 实现
├── fetch_schedule.py    课表核心（分页/字段归一化）
├── jwcore.py            纯工具函数：学期推算、节次解析、渲染
├── login_once.py        扫码 + 账号登录，生成 .session.json（需要浏览器）
├── test_mcp.py          stdio 冒烟测试
├── setup.sh             初始化环境 + 生成插件 patch
├── config.example.json  环境配置模板
└── dsh-bundle/          DSH 插件包
    ├── package.json
    ├── cordis.patch.yml.example
    ├── locale/{zh,en}.json
    └── icon.svg
```

## 快速开始

```bash
git clone <repo> && cd <repo>
./setup.sh                      # 建 venv、装 mcp、生成 config.local.json 和插件 patch
vim config.local.json           # 填学校的 VPN 地址与入口名称
.venv/bin/python login_once.py  # 扫码登录（需要浏览器 + 手机企业微信）
.venv/bin/python test_mcp.py    # 自检
```

`login_once.py` 成功后会把 WebVPN 票据和资源前缀写入 `.session.json`，之后
MCP 服务直接用这个文件，**不再需要浏览器**。

### 配置

`config.local.json`：

| 字段 | 说明 |
|---|---|
| `vpn_base` | WebVPN 主页地址，如 `https://vpn.example.edu.cn` |
| `resource_name` | VPN 首页上教务系统入口的文字，如 `教务系统` |
| `jwxt_host` | 教务系统主机名（仅供识别） |
| `user` / `password` | 可选。无浏览器环境下自动登录时使用；也可用环境变量 `JWC_USER` / `JWC_PASS` |

## MCP 工具

| 工具 | 说明 |
|---|---|
| `get_schedule(term?)` | 个人课表 |
| `query_info(feature, term?, date?)` | 13 项「信息查询」功能 |
| `list_features()` | 列出可用查询名 |
| `session_status()` | 会话是否有效 |
| `import_session(cookie, prefix?)` | 导入浏览器 cookie |

`query_info` 支持的功能：个人信息、学生成绩、考试信息、班级课表、个人课表、
按周次课表、成绩总表、结业换证考试、空闲教室、学籍预警、学业预警处理、
学业情况、选课情况确认。

`term` 形如 `2026-1`（2026-2027 学年第 1 学期），省略则按当前日期推断。

## 作为 DSH 插件安装

```bash
./setup.sh    # 会按本机绝对路径生成 dsh-bundle/cordis.patch.yml
```

然后在 **Plugins** 面板安装 `dsh-bundle` 目录（或让 agent 用
`plugin_manager` 的 `install_bundle` 指向该目录）。安装后 MCP 工具会以
`mcp__jiaowu__*` 的形式出现在会话中。

插件是**配置型 bundle**：不写 Host/Client 代码，只插入一条
`@deepseek-ai/dsh-mcp-client` 配置，以 stdio 方式拉起 `mcp_server.py`。

## 安全说明

- `.session.json` 等同于你教务系统的登录态，**不要提交、不要外传**。
- 服务端只在本机读写该文件；工具不会把凭证发往任何第三方。
- 票据是 session cookie，服务端超时后失效。失效时工具返回 `need_session`，
  用 `import_session` 导入新 cookie，或重新跑 `login_once.py`。
- 不要把 HTTP 传输直接暴露到公网：MCP 的 HTTP 传输默认无鉴权。

## 已知限制

- 会话票据是否绑定来源 IP 未验证；跨机器迁移凭证前请先测试。
- 若学校对某个模块（如「创新创业报名」）没有给学生账号授权，接口会返回
  「没有访问权限」，这不是代码问题。
- 接口路径依赖教务系统版本，升级后可能需要重新抓取。

## 许可

[MIT](LICENSE)

## 免责声明

本项目仅用于访问你**本人**的教务数据，请遵守所在学校的信息系统使用规定。
作者不对使用方式或由此产生的后果负责。
