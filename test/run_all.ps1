$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $T "..")
$R = Join-Path $T "results"
New-Item -ItemType Directory -Force -Path $R | Out-Null

if ($env:USE_UV -eq "1" -and (Get-Command uv -ErrorAction SilentlyContinue)) {
    if (-not $env:UV_CACHE_DIR) {
        $env:UV_CACHE_DIR = Join-Path ([System.IO.Path]::GetTempPath()) "uv_cache"
    }
    $PytestRunner = @("uv", "run", "python", "-m", "pytest")
    $PythonRunner = @("uv", "run", "python")
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PytestRunner = @("py", "-3", "-m", "pytest")
    $PythonRunner = @("py", "-3")
} else {
    $PytestRunner = @("python", "-m", "pytest")
    $PythonRunner = @("python")
}

function Run-Suite {
    param(
        [string]$Label,
        [string]$Xml,
        [string[]]$Paths
    )

    Write-Host "=== $Label ===" -ForegroundColor Cyan
    $Args = @()
    if ($PytestRunner.Length -gt 1) {
        $Args += $PytestRunner[1..($PytestRunner.Length - 1)]
    }
    $Args += $Paths
    $Args += "--junitxml=$Xml"
    $Args += "-q"
    & $PytestRunner[0] @Args
    if ($LASTEXITCODE -ne 0) {
        throw "$Label 失败"
    }
}

Run-Suite "L1 单元" (Join-Path $R "unit.xml") @((Join-Path $Root "tests\unit"))
Run-Suite "L2 集成" (Join-Path $R "integration.xml") @((Join-Path $Root "tests\integration"))
Run-Suite "L3 API" (Join-Path $R "api.xml") @(
    (Join-Path $Root "tests\unit\test_agents_api.py"),
    (Join-Path $Root "tests\unit\test_config_api.py"),
    (Join-Path $Root "tests\unit\test_gateway_api.py"),
    (Join-Path $Root "tests\unit\test_skill_api.py"),
    (Join-Path $Root "tests\unit\test_tools_api.py"),
    (Join-Path $Root "tests\unit\test_workspace_api.py")
)
Run-Suite "跨功能" (Join-Path $R "cross.xml") @((Join-Path $Root "tests\cross_feature"))
Run-Suite "E2E 后端" (Join-Path $R "e2e_backend.xml") @((Join-Path $Root "tests\e2e"))

Write-Host "=== 生成矩阵 ===" -ForegroundColor Cyan
$PyArgs = @()
if ($PythonRunner.Length -gt 1) {
    $PyArgs += $PythonRunner[1..($PythonRunner.Length - 1)]
}
$PyArgs += (Join-Path $T "generate_matrix.py")
& $PythonRunner[0] @PyArgs

Write-Host "完成 → $R" -ForegroundColor Green
Write-Host "真实 API 回归可额外执行: uv run python tests/e2e/run_e2e.py --provider openai" -ForegroundColor Cyan
