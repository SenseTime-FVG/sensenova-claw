@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM -- resolve project root (canonical path) --
pushd "%~dp0.."
set "ROOT_DIR=%CD%"
popd
echo ROOT_DIR=%ROOT_DIR%

set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"

REM -- jump to main --
goto main

:check_port
set "port=%~1"
netstat -ano | findstr ":%port%" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [ERROR] port %port% is already in use.
    exit /b 1
)
exit /b 0

:main
echo ----------------------------------------
if not exist "%USERPROFILE%\.SenseAssistant\config.yml" (
    if exist "%ROOT_DIR%\config.yml" (
        echo config.yml not found, copying from repo root...
        mkdir "%USERPROFILE%\.SenseAssistant" >nul 2>&1
        copy /Y "%ROOT_DIR%\config.yml" "%USERPROFILE%\.SenseAssistant\config.yml" >nul
        echo Done: config.yml copied to %USERPROFILE%\.SenseAssistant\config.yml
    ) else (
        echo [WARN] No config.yml or config.yml found, using defaults.
    )
)

echo Checking ports...
call :check_port %BACKEND_PORT%
if %errorlevel% neq 0 exit /b 1
call :check_port %FRONTEND_PORT%
if %errorlevel% neq 0 exit /b 1

echo.
echo Starting backend...
cd /d "%ROOT_DIR%"

where uv >nul 2>&1
if %errorlevel% equ 0 (
    start "Sensenova-Claw Backend" cmd /k "cd /d "%ROOT_DIR%" && uv run uvicorn sensenova_claw.app.gateway.main:app --reload --host 0.0.0.0 --port %BACKEND_PORT%"
) else (
    start "Sensenova-Claw Backend" cmd /k "cd /d "%ROOT_DIR%" && python -m uvicorn sensenova_claw.app.gateway.main:app --reload --host 0.0.0.0 --port %BACKEND_PORT%"
)

timeout /t 3 /nobreak >nul

echo Starting frontend...
cd /d "%ROOT_DIR%\sensenova_claw\app\web"
start "Sensenova-Claw Frontend" cmd /k "cd /d "%ROOT_DIR%\sensenova_claw\app\web" && npm run dev"

timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo   Sensenova-Claw Dev Environment Started
echo ========================================
echo   Backend : http://localhost:%BACKEND_PORT%
echo   Frontend: http://localhost:%FRONTEND_PORT%
echo.
echo   Press any key to exit (sub-windows stay open)
echo ========================================
echo.

pause

endlocal
