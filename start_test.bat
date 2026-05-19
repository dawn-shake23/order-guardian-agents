@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo ============================================================
echo   RAG 闭环验证
echo ============================================================
echo.

:: ---- 找到 Python ----
set "PY_CMD="
py --version >nul 2>&1 && set "PY_CMD=py"
if "%PY_CMD%"=="" python --version >nul 2>&1 && set "PY_CMD=python"
if "%PY_CMD%"=="" python3 --version >nul 2>&1 && set "PY_CMD=python3"
if "%PY_CMD%"=="" (
    echo [错误] 未找到 Python
    pause & exit /b 1
)
echo [OK] 使用: %PY_CMD%

:: ---- 装依赖 ----
echo [1/3] 安装依赖...
%PY_CMD% -m pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul

:: ---- 数据 ----
if not exist "data" mkdir data
set NEED_GEN=0
if not exist "data\knowledge_base.json" set NEED_GEN=1
if %NEED_GEN%==1 %PY_CMD% infrastructure/data_generator.py

:: ---- 配置 ----
set DASHSCOPE_API_KEY=sk-f783c98548d4404d9d3ef8eee4f8c931
set PYTHONIOENCODING=utf-8

:: ---- 运行 ----
echo [2/3] 加载配置...
echo [3/3] 运行10步验证...
echo.
%PY_CMD% test_rag.py

echo.
echo ============================================================
echo   完成
echo ============================================================
pause
