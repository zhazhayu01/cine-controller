#!/usr/bin/env bash
# 一键跑全部 P0 测试
# 用法：bash tests/run_all.sh
set -e

BLENDER="/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"
DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=============================================="
echo "  Cine Controller P0 测试套件"
echo "=============================================="

for t in run_tests save_reload_test bake_test viewport_render_test; do
    echo ""
    echo ">>> 运行 $t ..."
    "$BLENDER" -b -P "$DIR/tests/$t.py"
done

echo ""
echo "=============================================="
echo "  全部测试完成"
echo "=============================================="
