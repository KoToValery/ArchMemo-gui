@echo off
setlocal
set SCRIPT_DIR=%~dp0
set APP_URL=http://localhost:5000/run_full

echo [%date% %time%] Triggering scheduled full scan...
curl -X POST %APP_URL%
echo.
echo [%date% %time%] Done.
