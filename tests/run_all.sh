#!/usr/bin/env bash
# 一键跑全部 P0 测试
# 用法：bash tests/run_all.sh
set -e

BLENDER="/c/Program Files/Blender Foundation/Blender 5.2/blender.exe"
DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=============================================="
echo "  Cine Controller P0 测试套件"
echo "=============================================="

for t in shake_ui_and_api_test shake_test camera_view_test dolly_distance_test icons_and_help_test automation_test path_follow_test pose_import_test position_import_test preferences_test cinematography_test cinematography_panel_test curve_controller_test default_axes_test internal_controller_test bind_reset_test run_tests native_reference_test upgrade_test panel_and_ownership_test save_reload_test bake_test viewport_render_test offset_pan_test target_lifecycle_test focus_reload_test render_restart_test; do
    echo ""
    echo ">>> 运行 $t ..."
    "$BLENDER" --factory-startup -b --python-exit-code 1 -P "$DIR/tests/$t.py"
done

echo ""
echo "=============================================="
echo "  全部测试完成"
echo "=============================================="
