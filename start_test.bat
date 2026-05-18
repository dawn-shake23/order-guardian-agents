@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

echo.
echo ============================================================
echo   RAG 闭环验证 - 10步全链路测试
echo ============================================================
echo.

where python >nul 2>&1 || (echo [错误] 未找到Python & pause & exit /b 1)

:: 加载.env
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if not "%%b"=="" set "%%a=%%b"
    )
)

:: 安装依赖
pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul

:: 准备目录
if not exist "data" mkdir data

:: 检查数据
set "MISSING="
for %%f in (orders.json payments.json risks.json reconciliations.json knowledge_base.json) do (
    if not exist "data\%%f" set "MISSING=1"
)
if defined MISSING (
    echo [生成] 创建测试数据...
    python infrastructure/data_generator.py
)

echo [启动] RAG 闭环验证...
echo ============================================================
echo.

python test_rag.py

echo.
echo ============================================================
echo   测试完成
echo ============================================================
pause
