@echo off
REM 获取脚本所在目录
cd /d "%~dp0"
call .venv\Scripts\activate
python server\app.py
pause
