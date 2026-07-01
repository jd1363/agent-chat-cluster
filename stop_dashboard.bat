@echo off
chcp 65001 >nul
title Stop Dashboard

:: 查找并 kill 占用 8765 端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
    echo [INFO] Killing PID %%a on port 8765
    taskkill /F /PID %%a >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Failed to kill PID %%a
    ) else (
        echo [OK] PID %%a killed
    )
    goto :done
)
echo [INFO] No process found on port 8765

:done
pause
