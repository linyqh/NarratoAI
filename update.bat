@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
set "CURRENT_DIR=%~dp0"
echo ***** 当前目录: %CURRENT_DIR% *****

REM 清除可能影响的环境变量
set PYTHONPATH=
set PYTHONHOME=

REM 初始化代理设置为空
set "HTTP_PROXY="
set "HTTPS_PROXY="

:git_pull
echo 正在更新代码，请稍候...
REM 使用git更新代码并检查是否成功
"%CURRENT_DIR%lib\git\bin\git.exe" -C "%CURRENT_DIR%NarratoAI" pull > "%TEMP%\git_output.txt" 2>&1
set GIT_EXIT_CODE=%ERRORLEVEL%

if %GIT_EXIT_CODE% NEQ 0 (
    echo [错误] 代码更新失败！错误代码: %GIT_EXIT_CODE%
    type "%TEMP%\git_output.txt"
    
    findstr /C:"error: 403" /C:"fatal: unable to access" /C:"The requested URL returned error: 403" "%TEMP%\git_output.txt" >nul
    if !ERRORLEVEL! EQU 0 (
        echo.
        echo [提示] 检测到 GitHub 403 错误，可能是由于网络问题导致。
        
        if not defined HTTP_PROXY (
            echo.
            echo 请输入代理地址（例如 http://127.0.0.1:7890），或直接按回车跳过:
            set /p PROXY_INPUT="> "
            
            if not "!PROXY_INPUT!"=="" (
                set "HTTP_PROXY=!PROXY_INPUT!"
                set "HTTPS_PROXY=!PROXY_INPUT!"
                echo.
                echo [信息] 已设置代理: !PROXY_INPUT!
                echo 正在使用代理重试...
                goto git_pull
            ) else (
                echo.
                echo [警告] 未设置代理，建议:
                echo    - 手动设置系统代理
                echo    - 使用VPN或其他网络工具
                echo    - 重新运行此脚本并输入代理地址
            )
        ) else (
            echo.
            echo [警告] 使用代理 !HTTP_PROXY! 仍然失败。
            echo 您可以:
            echo    1. 输入新的代理地址（或直接按回车使用当前代理: !HTTP_PROXY!）
            echo    2. 输入 "clear" 清除代理设置
            set /p PROXY_INPUT="> "
            
            if "!PROXY_INPUT!"=="clear" (
                set "HTTP_PROXY="
                set "HTTPS_PROXY="
                echo [信息] 已清除代理设置
                goto end
            ) else if not "!PROXY_INPUT!"=="" (
                set "HTTP_PROXY=!PROXY_INPUT!"
                set "HTTPS_PROXY=!PROXY_INPUT!"
                echo [信息] 已更新代理为: !PROXY_INPUT!
                echo 正在使用新代理重试...
                goto git_pull
            ) else (
                echo [信息] 保持当前代理: !HTTP_PROXY!
                echo 您可以稍后再次尝试或手动解决网络问题
            )
        )
    ) else (
        echo.
        echo [警告] 遇到其他错误，请检查输出信息以获取更多详情。
    )
    goto end
) else (
    echo [成功] 代码已成功更新！
)

echo 正在更新pip，请稍候...
"%CURRENT_DIR%lib\python\python.exe" -m pip install --upgrade pip >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [警告] pip更新失败，将继续使用当前版本。
) else (
    echo [成功] pip已更新至最新版本！
)

echo 正在安装依赖，请稍候...
REM 确保使用正确的Python和pip
"%CURRENT_DIR%lib\python\python.exe" -m pip install -q -r "%CURRENT_DIR%NarratoAI\requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 依赖安装失败！请检查requirements.txt文件是否存在。
    goto end
) else (
    echo [成功] 依赖安装完成！
)

echo ===================================
echo      ✓ 程序更新已完成
echo ===================================

:end
if exist "%TEMP%\git_output.txt" del "%TEMP%\git_output.txt"
REM 清除设置的代理环境变量
if defined HTTP_PROXY (
    echo [信息] 本次会话的代理设置已清除
    set "HTTP_PROXY="
    set "HTTPS_PROXY="
)
pause