@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo ============================================================
echo   Order Guardian Agents v2.0
echo ============================================================
echo.

:: ---- 找到可用的 Python ----
set "PY_CMD="
py --version >nul 2>&1 && set "PY_CMD=py"
if "%PY_CMD%"=="" python --version >nul 2>&1 && set "PY_CMD=python"
if "%PY_CMD%"=="" python3 --version >nul 2>&1 && set "PY_CMD=python3"
if "%PY_CMD%"=="" (
    echo [错误] 未找到 Python (py / python / python3 都不行)
    echo        请安装 Python 3.10+
    echo        下载: https://www.python.org/downloads/
    echo        安装时必须勾选 "Add Python to PATH"
    pause
    exit /b 1
)
echo [OK] 使用: %PY_CMD%

:: ---- 1. 装依赖 ----
echo.
echo [1/5] 安装依赖...
%PY_CMD% -m pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul
if %errorlevel% neq 0 %PY_CMD% -m pip install -r requirements.txt --quiet 2>nul
echo [OK] 依赖就绪

:: ---- 2. 校验数据 ----
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
    %PY_CMD% infrastructure/data_generator.py
    if %errorlevel% neq 0 (
        echo [错误] 数据生成失败
        pause
        exit /b 1
    )
)
echo [OK] 数据就绪

:: ---- 3. 加载配置 ----
echo.
echo [3/5] 加载配置...
set DASHSCOPE_API_KEY=sk-f783c98548d4404d9d3ef8eee4f8c931
set PYTHONIOENCODING=utf-8
echo [OK] 环境变量就绪

:: ---- 4. 清理 ----
if exist "order-guardian.log" del "order-guardian.log" 2>nul

:: ---- 5. 启动 ----
echo.
echo [4/5] 初始化系统...
echo [5/5] 运行3个诊断场景...
echo.
echo ============================================================
echo.

%PY_CMD% main.py
set EXIT_CODE=%errorlevel%

echo.
echo ============================================================
if %EXIT_CODE% equ 0 (
    echo   运行成功
) else (
    echo   运行异常 (exit code: %EXIT_CODE%)
)
echo   日志: order-guardian.log
echo ============================================================
pause
