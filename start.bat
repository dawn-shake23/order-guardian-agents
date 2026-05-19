@echo off
title Order Guardian Agents
cd /d "%~dp0"

echo.
echo ============================================================
echo   Order Guardian Agents v2.0
echo   订单异常治理系统
echo ============================================================
echo.

:: ---- 1. 检查 py 启动器 ----
py --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo        下载: https://www.python.org/downloads/
    echo        安装时勾选 "Add Python to PATH"
    pause
    exit /b 1
)
for /f "tokens=1,2" %%a in ('py --version 2^>^&1') do echo [OK] %%a %%b

:: ---- 2. 装依赖 ----
echo.
echo [1/5] 安装依赖...
py -m pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul
if %errorlevel% neq 0 (
    py -m pip install -r requirements.txt --quiet 2>nul
)
echo [OK] 依赖就绪

:: ---- 3. 校验数据 ----
echo.
echo [2/5] 校验数据...
if not exist "data" mkdir data
if not exist "state_checkpoints" mkdir state_checkpoints

set NEED_GEN=0
if not exist "data\orders.json"     set NEED_GEN=1
if not exist "data\payments.json"   set NEED_GEN=1
if not exist "data\risks.json"      set NEED_GEN=1
if not exist "data\reconciliations.json" set NEED_GEN=1
if not exist "data\knowledge_base.json"  set NEED_GEN=1

if %NEED_GEN%==1 (
    echo [生成] 创建1000条测试数据...
    py infrastructure/data_generator.py
)
echo [OK] 数据就绪

:: ---- 4. 加载配置 ----
echo.
echo [3/5] 加载配置...
set DASHSCOPE_API_KEY=sk-f783c98548d4404d9d3ef8eee4f8c931
echo [OK] 环境变量就绪

:: ---- 5. 清理旧日志 ----
if exist "order-guardian.log" del "order-guardian.log" 2>nul

:: ---- 6. 启动 ----
echo.
echo [4/5] 初始化系统...
echo [5/5] 运行诊断场景...
echo.
echo ============================================================
echo.

py main.py

echo.
echo ============================================================
echo   完成. 日志: order-guardian.log
echo ============================================================
pause
