@echo off
rem 以 debug 模式启动浏览器（默认 Edge，端口 9222）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_browser_debug.ps1" %*
