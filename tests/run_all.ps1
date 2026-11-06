param(
    [string]$Blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Blender)) {
    throw "找不到 Blender，请通过 -Blender 指定 blender.exe 的完整路径。"
}
$testNames = @(
    'position_import_test',
    'preferences_test',
    'cinematography_test', 'cinematography_panel_test',
    'curve_controller_test', 'default_axes_test', 'internal_controller_test', 'bind_reset_test', 'run_tests',
    'native_reference_test', 'upgrade_test', 'panel_and_ownership_test',
    'save_reload_test', 'bake_test', 'viewport_render_test',
    'offset_pan_test', 'target_lifecycle_test', 'focus_reload_test',
    'render_restart_test'
)
$logDirectory = Join-Path $PSScriptRoot '_output'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
foreach ($testName in $testNames) {
    $testPath = Join-Path $PSScriptRoot "$testName.py"
    $testOutput = & $Blender --factory-startup -b --python-exit-code 1 -P $testPath 2>&1
    $testExit = $LASTEXITCODE
    $logPath = Join-Path $logDirectory "$testName.log"
    $testOutput | Set-Content -LiteralPath $logPath -Encoding utf8
    $cycle = $testOutput -match 'Dependency cycle detected'
    if ($testExit -ne 0 -or $cycle) {
        $testOutput | Write-Output
        throw "测试失败：$testName，日志：$logPath"
    }
    Write-Output "通过：$testName"
    $testOutput | Select-String '^\[PASS\]|^====='
}
Write-Output "全部 $($testNames.Count) 套测试通过，未检测到依赖循环。"
