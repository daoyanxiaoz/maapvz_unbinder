@echo off
chcp 65001 >nul
echo 正在检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 未找到 Python，请安装 Python 3.6+ 并添加到 PATH。
    pause
    exit /b
)
echo Python 已就绪。
echo 正在检查 Java 环境...
java -version >nul 2>&1
if errorlevel 1 (
    echo 未找到 Java，请安装 JRE 并添加到 PATH。
    pause
    exit /b
)
echo Java 已就绪。
echo 开始执行自动打包脚本...
python auto_patch.py
pause