@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================================
echo   Order Guardian Agents - 订单异常治理系统
echo ============================================================
echo.

:: 检查 .env 文件
if not exist ".env" (
    echo [警告] .env 文件不存在，使用确定性哈希模式
    echo 请复制 .env.example 为 .env 并填入 DASHSCOPE_API_KEY
) else (
    echo [OK] .env 已配置
)

:: 加载环境变量
for /f "tokens=1,2 delims==" %%a in (.env) do (
    set %%a=%%b
)

:: 检查数据文件
if not exist "data\orders.json" (
    echo [生成] 数据文件不存在，正在生成1000条测试数据...
    python infrastructure/data_generator.py
    echo.
)

:: 安装依赖（首次运行）
pip install -r requirements.txt --quiet 2>nul

echo [启动] Order Guardian Agents...
echo.

python main.py

echo.
echo ============================================================
echo   运行完成
echo ============================================================
pause
