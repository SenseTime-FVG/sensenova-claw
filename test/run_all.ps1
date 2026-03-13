$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$B = Join-Path $T "..\backend"
$R = Join-Path $T "results"
New-Item -ItemType Directory -Force -Path $R | Out-Null
Set-Location $B

Write-Host "=== L1 单元 ===" -ForegroundColor Cyan
uv run python -m pytest "$T\unit" --junitxml="$R\unit.xml" -q

Write-Host "=== L2 集成 ===" -ForegroundColor Cyan
uv run python -m pytest "$T\integration" --junitxml="$R\integration.xml" -q

Write-Host "=== L3 API ===" -ForegroundColor Cyan
uv run python -m pytest "$T\api" --junitxml="$R\api.xml" -q

Write-Host "=== 跨功能 ===" -ForegroundColor Cyan
uv run python -m pytest "$T\cross_feature" --junitxml="$R\cross.xml" -q

Write-Host "=== 生成矩阵 ===" -ForegroundColor Cyan
uv run python "$T\generate_matrix.py"

Write-Host "完成 → $R" -ForegroundColor Green
