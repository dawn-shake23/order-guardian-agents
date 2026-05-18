@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

echo.
echo ============================================================
echo   Order Guardian Agents v2.0
echo   订单异常治理系统 - 多智能体协作诊断
echo ============================================================
echo.

:: ── 1. 检查 Python ──────────────────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do echo [OK] Python %%i

:: ── 2. 加载 .env 配置 ───────────────────────────────────────
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if not "%%b"=="" set "%%a=%%b"
    )
    echo [OK] 环境变量已加载
) else (
    echo [警告] .env 不存在，使用确定性哈希模式
    echo   如需千问语义检索，请复制 .env.example 为 .env 并填入 API KEY
)

:: ── 3. 安装依赖 ─────────────────────────────────────────────
echo [安装] 检查 Python 依赖...
pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul
if %errorlevel% neq 0 (
    echo [重试] 安装依赖...
    pip install -r requirements.txt --quiet 2>nul
)
echo [OK] 依赖就绪

:: ── 4. 准备运行目录 ─────────────────────────────────────────
if not exist "data" mkdir data
if not exist "state_checkpoints" mkdir state_checkpoints

:: ── 5. 检查并生成数据 ───────────────────────────────────────
set "MISSING_DATA="
for %%f in (orders.json payments.json risks.json reconciliations.json knowledge_base.json) do (
    if not exist "data\%%f" set "MISSING_DATA=1"
)
if defined MISSING_DATA (
    echo [生成] 创建1000条测试数据...
    python infrastructure/data_generator.py
    if %errorlevel% neq 0 (
        echo [错误] 数据生成失败
        pause
        exit /b 1
    )
) else (
    echo [OK] 数据文件已就绪 ^(1000条^)
)

:: ── 6. 清理旧日志 ───────────────────────────────────────────
if exist "order-guardian.log" del "order-guardian.log" >nul 2>&1

:: ── 7. 启动系统 ─────────────────────────────────────────────
echo.
echo [启动] 初始化系统并执行诊断场景...
echo ============================================================
echo.

python main.py

:: ── 8. 完成 ─────────────────────────────────────────────────
echo.
echo ============================================================
echo   运行完成。日志文件: order-guardian.log
echo ============================================================
pause
