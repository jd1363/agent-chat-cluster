@echo off
chcp 65001 >nul
title Agent Chat Cluster - Stop Dashboard

echo ============================================
echo   Agent Chat Cluster - Stop Dashboard
echo ============================================
echo.

:: 查找占用 8765 端口的进程并终止
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
    echo [INFO] Killing PID %%a ...
    taskkill /PID %%a /F
)

echo [INFO] Done.
pause
