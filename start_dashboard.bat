@echo off
chcp 65001 >nul
title Agent Chat Cluster - Dashboard

cd /d G:\agent-chat-cluster

echo ============================================
echo   Agent Chat Cluster - Dashboard
echo ============================================
echo.

:: 检查 Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH
    pause
    exit /b 1
)

:: 检查 server.py
if not exist "web\server.py" (
    echo [ERROR] web\server.py not found
    pause
    exit /b 1
)

echo [INFO] Starting dashboard server...
echo [INFO] URL: http://127.0.0.1:8765
echo [INFO] Press Ctrl+C to stop
echo.

:: 延迟 2 秒后打开浏览器
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8765"

:: 启动服务器
python web/server.py --port 8765 --host 127.0.0.1

echo.
echo [INFO] Dashboard stopped.
pause
