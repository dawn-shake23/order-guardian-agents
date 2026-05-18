@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   RAG 闭环验证测试
echo ============================================================
echo.

for /f "tokens=1,2 delims==" %%a in (.env) do set %%a=%%b
pip install -r requirements.txt --quiet 2>nul

python test_rag.py

pause
