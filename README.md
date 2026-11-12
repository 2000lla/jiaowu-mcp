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
├── qr_login.py          扫码登录，二维码存成图片、浏览器隐藏（生成 .session.json）
├── login_once.py        同上但窗口可见，排查问题用
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
.venv/bin/python qr_login.py    # 二维码会存成图片，扫码即可（见下）
.venv/bin/python test_mcp.py    # 自检
```

## 扫码登录（二维码在终端/图片里，不弹窗）

`qr_login.py` 把企业微信登录二维码**截出来存成图片**，不再弹出浏览器窗口：

```bash
.venv/bin/python qr_login.py
# 输出: QR_READY .../outputs/qr_login.png
```

把这张图片打开、用手机企业微信扫描确认即可。浏览器工作在屏幕外完成，
用户看不到窗口；登录成功后自动完成教务系统登录并写入 `.session.json`。

在支持图片显示的 agent（如 DeepSeek Harness）里，可以让它读这张图并直接展示：

> 帮我跑 qr_login.py，把二维码给我扫

### 为什么仍然需要一个浏览器进程

企业微信扫码是标准 OAuth：手机确认后，微信服务器**只会把 code 回跳到显示二维码的那个
浏览器**（`https://<vpn>/login?wechat_login=1&code=...`），WebVPN 服务端没有提供轮询接口。
所以必须有一个进程接收这次回跳，它可以是隐藏在屏幕外的 Chrome，但无法省掉。

可选的 `--mode`：

| 模式 | 行为 |
|---|---|
| `hidden`（默认） | 浏览器窗口移到屏幕外，看不到窗口 |
| `headless` | 纯无头。**注意：实测企业微信回跳在纯无头下不完成** |
| `visible` | 正常窗口，调试用 |

`login_once.py` 是同一套流程的可见窗口版本，方便排查问题。


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

## 实例：广西农业职业技术大学

本项目就是在这套环境下开发和验证的，可作为接入其他学校的参照。

`config.local.json`：

```json
{
  "vpn_base": "https://vpn.gxnzd.com.cn",
  "resource_name": "教务系统",
  "jwxt_host": "jwxt.gxnzd.com.cn"
}
```

接入特征：

| 项 | 情况 |
|---|---|
| WebVPN | 网瑞达「资源访问控制系统」，企业微信扫码登录 |
| 资源入口 | VPN 首页卡片文字为「教务系统」，点击进入正方教务系统 |
| 教务系统 | `jwxt.gxnzd.com.cn`，外网有 WAF 白名单，只能经 VPN 访问 |
| 二次登录 | 进入后仍需学号 + 密码（无 RSA，表单带 `csrftoken`） |
| 学生端「信息查询」 | 共 14 项，本项目实现 13 项 |

该实例下各功能对应的接口（换学校时需要重新抓取）：

| 功能 | gnmkdm | 数据接口 |
|---|---|---|
| 个人课表 | N2151 | `/kbcx/xskbcx_cxXsKb.html` |
| 按周次课表 | N2154 | `/kbcx/xskbcxMobile_cxXsKb.html` |
| 班级课表 | N214505 | `/kbdy/bjkbdy_cxBjkbdyTjkbList.html` |
| 学生成绩 | N305005 | `/cjcx/cjcx_cxXsgrcj.html?doType=query` |
| 成绩总表 | N558020 | `/bysxxcx/xscjzbdy_cxXscjzbdyIndex.html?doType=query` |
| 考试信息 | N358105 | `/kwgl/kscx_cxXsksxxIndex.html?doType=query` |
| 结业换证考试 | N581035 | `/jyhzgl/ksxxcx_cxXsksxxIndex.html?doType=query` |
| 个人信息 | N100801 | 直接解析页面 HTML |
| 学籍预警 | N105505 | `/xjyj/xjyj_cxXjyjList.html` |
| 学业预警处理 | N305516 | `/xyyjjk/xyyjclcx_cxXyyjclcxxsList.html` |
| 学业情况 | N105515 | `/xsxy/xsxyqk_cxJxzxjhxfyqKcxx.html` |
| 选课确认 | N2158 | `/kbcx/xskbqr_cxZjxbxx.html` |
| 空闲教室 | N2155 | `/cdjy/cdjy_cxAtyycdSchedule.html` |
| 创新创业报名 | N4755 | 学生账号无权限 |

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
