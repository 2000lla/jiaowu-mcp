# Windows 部署经验总结（DSH 桌面版）

> 记录 2026-11-13 在 Windows 11 + DeepSeek Harness（DSH）桌面版上部署本插件、
> 打通企业微信扫码登录的完整过程，含三个环境坑的排查与解决。
> Linux/macOS 按 README 的 `setup.sh` 走即可，一般无需本文。
> 学校实例为广西农业职业技术大学（配置见 README「实例」节）。

## 环境

| 项 | 值 |
|---|---|
| 系统 | Windows 11 + PowerShell 7 |
| Python | 3.11.4（系统安装，`%LOCALAPPDATA%\Programs\Python`） |
| Chrome | 156（系统安装） |
| DSH | 桌面版，会话权限 danger-full-access |
| pip 镜像 | 清华 `pypi.tuna.tsinghua.edu.cn`（已全局配置） |

## 部署步骤（PowerShell 版 setup）

`setup.sh` 是 bash 脚本，Windows 上等价操作：

```powershell
git clone https://github.com/2000lla/jiaowu-mcp.git
cd jiaowu-mcp
python -m venv .venv
# 注意：不要先跑 pip install --upgrade pip（见坑 1）
.\.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt `
    --timeout 15 --retries 2 --no-input --disable-pip-version-check
Copy-Item config.example.json config.local.json
# 编辑 config.local.json：vpn_base / resource_name / jwxt_host / user / password
```

生成 `dsh-bundle/cordis.patch.yml`：把 example 里的 `__JIAOWU_DIR__` 替换为仓库
绝对路径，并**把 `.venv/bin/python` 改为 `.venv/Scripts/python.exe`**（Windows 布局）：

```yaml
- insert:
    - id: jiaowu-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: jiaowu
        transport: stdio
        command: <repo>/.venv/Scripts/python.exe
        args:
          - <repo>/mcp_server.py
        cwd: <repo>
        failOnStartupError: true
```

在 DSH 里安装 bundle（让 agent 执行，或 Plugins 面板手动安装）：

```text
plugin_manager install_bundle target=link:<repo>/dsh-bundle
```

安装即时生效（`application: applied`），无需重启。验证：

- `list_mcp_resources server=jiaowu` 能返回 serverInfo 即连接成功；
- `.\.venv\Scripts\python.exe test_mcp.py`：列出 5 个工具、13 项功能；
  未登录时各项返回 `need_session` 属正常。

## 坑 1：pip 自升级挂起

**现象**：`pip install --upgrade pip` 挂起 10 分钟以上无任何输出；
实测镜像连通性完全正常（0.2s 响应）。

**解决**：跳过自升级，直接装依赖，并加快速失败参数：
`--timeout 15 --retries 2 --no-input --disable-pip-version-check`。
venv 自带的 pip 版本足够用。

## 坑 2：DSH 工作区 Low 完整性（本次最大的坑）

**现象**：`qr_login.py` 启动即失败，Selenium Manager 报：

```text
Cache folder (C:\Users\<user>\.cache\selenium) cannot be created: 拒绝访问。 (os error 5)
拒绝访问。 (os error 5) at path "C:\Users\<user>\AppData\Local\Temp\selenium-managerXXXX"
```

但 PowerShell 里手动 `New-Item` 建同样的目录却成功；`icacls` 看 ACL 也正常
（用户有完全控制）。

**排查**：对比父子进程令牌 `whoami /all`：

| 进程 | 完整性级别 |
|---|---|
| pwsh（DSH 工具进程） | High (S-1-16-12288) |
| 工作区内 `.venv\Scripts\python.exe` | **Low (S-1-16-4096)** |
| 工作区外的系统 python.exe | High |
| cmd.exe（系统二进制） | 不受影响 |

再看 ACL：工作区带 `Mandatory Label\Low Mandatory Level` 标签，而 Temp、
`~/.cache` 是默认的 Medium。**低完整性进程默认不能向上写 Medium 对象**——
所以工作区内的 python / selenium-manager 写 Temp 必败，写工作区正常。
经 cmd 中转启动工作区 python 也一样被降级，说明是按可执行文件位置区分的。

**结论**：DSH 会把工作区内的可执行文件降为 Low 完整性运行。MCP 服务本身不受影响
（只读写工作区内的 `.session.json` / `outputs/`），但登录流程的 Chrome /
Selenium Manager 需要写 Temp，必须绕开。

**解决**（不改任何系统权限）：

1. chromedriver 放到**工作区外**（如 `%USERPROFILE%\.cache\selenium\chromedriver-win64\`），
   用 `CHROMEDRIVER` 环境变量指定——`login_once._driver_path()` 优先读它，
   从而完全绕开 Selenium Manager；
2. 用**工作区外的系统 Python** 跑 `qr_login.py`，`PYTHONPATH` 指向 venv 的
   `Lib\site-packages` 复用依赖；
3. Chrome 由工作区外的 chromedriver 拉起，继承正常完整性，可写 Temp；
   其 `--user-data-dir`（`.chrome-profile`）在工作区内，向下写允许。

以上已封装为仓库根目录的 **`relogin.ps1`**（含驱动自动下载），一键执行：

```powershell
.\relogin.ps1                # 重新扫码
.\relogin.ps1 --from-session # 先尝试复用已有票据
```

## 坑 3：outputs/ 目录缺失（首次运行 bug，已修复）

**现象**：全新克隆后首次扫码，`capture_qr()` 抛
`FileNotFoundError: outputs/_qr_full.png`。

**原因**：`save_screenshot()` 不会创建父目录，失败时静默返回 False；
而 `outputs/` 只在课表落盘时才被创建。

**修复**：`capture_qr()` 截图前 `core.OUT.mkdir(parents=True, exist_ok=True)`
（已提交）。旧版本手动 `mkdir outputs` 即可绕过。

## chromedriver 国内下载

Chrome for Testing 官方源在国内网络常不可达，用 npmmirror 镜像：

```text
https://cdn.npmmirror.com/binaries/chrome-for-testing/<version>/win64/chromedriver-win64.zip
```

注意**精确版本经常缺失**（如浏览器 156.0.8078.74，镜像只有 .73 / .80）。
版本列表可查 `https://registry.npmmirror.com/-/binary/chrome-for-testing/`，
取同 build（前三段相同）最接近的版本即可，主版本一致就兼容。
`relogin.ps1` 已内置这套回退逻辑。

## 登录与会话维护

扫码流程：`qr_login.py` 输出 `QR_READY <repo>/outputs/qr_login.png` →
把图片展示给用户 → 手机企业微信扫码确认 → 脚本自动点「教务系统」入口 →
学号密码登录正方教务 → 写入 `.session.json`。DSH 里直接说
"帮我跑 qr_login.py，把二维码给我扫"即可。

会话过期后工具返回 `need_session`，两种恢复方式：

- `.\relogin.ps1` 重新扫码（Windows / DSH 环境）；
- 浏览器登录 WebVPN 教务系统后，用 `import_session` 工具导入 cookie 与地址栏前缀。

安全注意：

- `config.local.json`、`.session.json` 均已 gitignore，只存本地，勿提交勿外传；
- 账号密码建议自行填入 `config.local.json`，避免经过聊天、日志等渠道；
- 票据是 session cookie，服务端超时即失效，插件不自动续期。

## 坑 4：PowerShell 脚本的编码与执行策略

- **含中文的 `.ps1` 必须存为 UTF-8 with BOM**。Windows PowerShell 5.1 对无 BOM
  文件按 ANSI（中文系统即 GBK）解析，中文注释/全角括号会破坏语法
  （报"表达式或语句中包含意外的标记"）。PowerShell 7 默认 UTF-8 无此问题，
  但带 BOM 两边都兼容。
- 本机执行策略为 `RemoteSigned` 时，带"网络来源"标记（Zone.Identifier）的
  脚本会被要求签名。`git clone` 下来的文件不带标记，可直接运行；
  若个别文件被拦，`Unblock-File .\relogin.ps1`，或进程级绕过：
  `powershell -ExecutionPolicy Bypass -File .\relogin.ps1`。
- PS 5.1 下 `$ErrorActionPreference='Stop'` 时，原生命令的 stderr 重定向
  （`2>$null`）会把 stderr 当错误记录抛出；脚本里改用目录探测代替 import 探测。

## 排查命令备忘

```powershell
whoami /all                     # 完整性级别 / 令牌组（对比父子进程）
icacls <path>                   # 看 ACL 与 Mandatory Label
Test-NetConnection <host> -Port 443
git clone ...                   # 进度走 stderr，PowerShell 会误报 NativeCommandError，
                                # 以目录内容判断成败
```

另：`raw.githubusercontent.com` 在部分网络下抓取失败，可改用
`https://api.github.com/repos/<owner>/<repo>/contents/<path>`（base64 返回）。
