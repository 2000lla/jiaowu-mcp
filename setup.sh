#!/usr/bin/env bash
# 初始化本地运行环境，并生成 DSH 插件用的 patch 文件。
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

echo "==> 目录: $DIR"

if [ ! -d "$DIR/.venv" ]; then
  echo "==> 创建虚拟环境"
  "$PY" -m venv "$DIR/.venv"
fi

echo "==> 安装依赖 (mcp)"
"$DIR/.venv/bin/python" -m pip install -q --upgrade pip
"$DIR/.venv/bin/python" -m pip install -q -r "$DIR/requirements-mcp.txt"

if [ ! -f "$DIR/config.local.json" ]; then
  cp "$DIR/config.example.json" "$DIR/config.local.json"
  chmod 600 "$DIR/config.local.json" 2>/dev/null || true
  echo "==> 已生成 config.local.json，请填入学校的 VPN 地址与入口名称"
fi

sed "s|__JIAOWU_DIR__|$DIR|g" \
  "$DIR/dsh-bundle/cordis.patch.yml.example" \
  > "$DIR/dsh-bundle/cordis.patch.yml"
echo "==> 已生成 dsh-bundle/cordis.patch.yml"

cat <<'TIP'

下一步:
  1. 编辑 config.local.json，填 vpn_base / resource_name
  2. 扫码登录生成会话:   .venv/bin/python login_once.py
  3. 想接入 DSH:  在 Plugins 里安装 dsh-bundle 目录
     （或用 plugin_manager 的 install_bundle 指向该目录）
  4. 自检:   .venv/bin/python test_mcp.py
TIP
