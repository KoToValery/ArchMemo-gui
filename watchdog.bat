@echo off
setlocal
set SCRIPT_DIR=%~dp0
set APP_FILE=%SCRIPT_DIR%app.py
set LOG_FILE=%SCRIPT_DIR%watchdog.log

echo Starting watchdog for ArchiMemo-gui... >> %LOG_FILE%

:loop
echo [%date% %time%] Starting app... >> %LOG_FILE%
python "%APP_FILE%" >> %LOG_FILE% 2>&1
echo [%date% %time%] App crashed with exit code %errorlevel%. Restarting in 5 seconds... >> %LOG_FILE%
timeout /t 5
goto loop
