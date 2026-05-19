@echo off
title RAG Test
cd /d "%~dp0"

echo.
echo ============================================================
echo   RAG 闭环验证 - 10步全链路测试
echo ============================================================
echo.

py --version >nul 2>&1 || (echo [错误] 未找到Python & pause & exit /b 1)

echo [1/3] 安装依赖...
if not exist "data" mkdir data

set NEED_GEN=0
if not exist "data\knowledge_base.json" set NEED_GEN=1
if %NEED_GEN%==1 py infrastructure/data_generator.py

echo [2/3] 加载配置...
set DASHSCOPE_API_KEY=sk-f783c98548d4404d9d3ef8eee4f8c931

echo [3/3] 运行验证...
echo.
echo ============================================================
echo.

py test_rag.py

echo.
echo ============================================================
echo   完成
echo ============================================================
pause
