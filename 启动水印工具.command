#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  osascript -e 'display alert "未找到 Python 3" message "请先安装 Python 3 后再启动。"' 2>/dev/null
  exit 1
fi

python3 app.py
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
  echo ""
  echo "水印工具启动失败，错误代码：$EXIT_CODE"
  echo "请复制上方错误信息发送给开发者。"
  echo ""
  read -r -p "按回车键关闭窗口…"
fi

exit "$EXIT_CODE"
