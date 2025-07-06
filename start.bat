@echo off
:: 设置控制台代码页为UTF-8，解决中文显示问题
chcp 65001 >nul
:: 关闭命令回显，使脚本运行时更整洁

:: 获取当前脚本所在目录路径并存储在变量中
set "CURRENT_DIR=%~dp0"
echo ***** 当前工作目录: %CURRENT_DIR% *****

:: ==================== FFmpeg 配置 ====================
:: 设置 FFmpeg 可执行文件的完整路径
set "FFMPEG_BINARY=%CURRENT_DIR%lib\ffmpeg\ffmpeg-7.0-essentials_build\ffmpeg.exe"
set "FFMPEG_PATH=%CURRENT_DIR%lib\ffmpeg\ffmpeg-7.0-essentials_build"
echo ***** FFmpeg 执行文件路径: %FFMPEG_BINARY% *****

:: 将 FFmpeg 目录添加到系统 PATH 环境变量，使其可以在命令行中直接调用
set "PATH=%FFMPEG_PATH%;%PATH%"

:: ==================== ImageMagick 配置 ====================
:: 设置 ImageMagick 可执行文件的完整路径（用于图像处理）
set "IMAGEMAGICK_BINARY=%CURRENT_DIR%lib\imagemagic\ImageMagick-7.1.1-29-portable-Q16-x64\magick.exe"
set "IMAGEMAGICK_PATH=%CURRENT_DIR%lib\imagemagic\ImageMagick-7.1.1-29-portable-Q16-x64"
echo ***** ImageMagick 执行文件路径: %IMAGEMAGICK_BINARY% *****

:: 将 ImageMagick 目录添加到系统 PATH 环境变量
set "PATH=%IMAGEMAGICK_PATH%;%PATH%"

:: ==================== Python 环境配置 ====================
:: 设置 Python 模块搜索路径，确保能够正确导入项目模块
set "PYTHONPATH=%CURRENT_DIR%NarratoAI;%PYTHONPATH%"
echo ***** Python模块搜索路径: %PYTHONPATH% *****

:: ==================== 项目特定环境变量配置 ====================
:: 设置项目根目录和依赖工具的路径，供应用程序内部使用
set "NARRATO_ROOT=%CURRENT_DIR%NarratoAI"
set "NARRATO_FFMPEG=%FFMPEG_BINARY%"
set "NARRATO_IMAGEMAGICK=%IMAGEMAGICK_BINARY%"

:: ==================== Streamlit 配置 ====================
:: 设置 Streamlit（Python Web应用框架）的配置文件路径
set "USER_HOME=%USERPROFILE%"
set "STREAMLIT_DIR=%USER_HOME%\.streamlit"
set "CREDENTIAL_FILE=%STREAMLIT_DIR%\credentials.toml"
echo ***** Streamlit 凭证文件路径: %CREDENTIAL_FILE% *****

:: 检查并创建 Streamlit 配置目录和凭证文件（如果不存在）
if not exist "%STREAMLIT_DIR%" (
    echo 创建 Streamlit 配置目录...
    mkdir "%STREAMLIT_DIR%"
    (
        echo [general]
        echo email=""
    ) > "%CREDENTIAL_FILE%"
    echo Streamlit 配置文件已创建!
)

:: ==================== 依赖检查 ====================
:: 验证必要的外部工具是否存在，确保应用可以正常运行
if not exist "%FFMPEG_BINARY%" (
    echo 错误: 未找到 FFmpeg 执行文件，路径: %FFMPEG_BINARY%
    echo 请确保已正确安装 FFmpeg 或检查路径配置
    pause
    exit /b 1
)

if not exist "%IMAGEMAGICK_BINARY%" (
    echo 错误: 未找到 ImageMagick 执行文件，路径: %IMAGEMAGICK_BINARY%
    echo 请确保已正确安装 ImageMagick 或检查路径配置
    pause
    exit /b 1
)

:: ==================== 启动应用 ====================
:: 切换到项目目录并启动应用
echo ***** 切换工作目录到: %CURRENT_DIR%NarratoAI *****
cd /d "%CURRENT_DIR%NarratoAI"

echo ***** 正在启动 NarratoAI 应用... *****
:: 使用项目自带的Python解释器启动Streamlit应用
"%CURRENT_DIR%lib\python\python.exe" -m streamlit run webui.py  --browser.serverAddress="127.0.0.1" --server.enableCORS=True  --server.maxUploadSize=2048 --browser.gatherUsageStats=False
:: 参数说明:
::   --browser.serverAddress="127.0.0.1" - 将服务器绑定到本地地址
::   --server.enableCORS=True - 启用跨域资源共享
::   --server.maxUploadSize=2048 - 设置最大上传文件大小为2048MB
::   --browser.gatherUsageStats=False - 禁用使用统计收集

:: 应用关闭后暂停，让用户看到最终输出
pause
