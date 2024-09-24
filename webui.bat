@echo off
set CURRENT_DIR=%CD%
echo ***** Current directory: %CURRENT_DIR% *****
set PYTHONPATH=%CURRENT_DIR%

@echo off
setlocal enabledelayedexpansion

rem 创建链接和路径的数组
set "urls_paths[0]=https://zenodo.org/records/13293144/files/MicrosoftYaHeiBold.ttc|.\resource\fonts"
set "urls_paths[1]=https://zenodo.org/records/13293144/files/MicrosoftYaHeiNormal.ttc|.\resource\fonts"
set "urls_paths[2]=https://zenodo.org/records/13293144/files/STHeitiLight.ttc|.\resource\fonts"
set "urls_paths[3]=https://zenodo.org/records/13293144/files/STHeitiMedium.ttc|.\resource\fonts"
set "urls_paths[4]=https://zenodo.org/records/13293144/files/UTM%20Kabel%20KT.ttf|.\resource\fonts"
set "urls_paths[5]=https://zenodo.org/records/13293129/files/demo.mp4|.\resource\videos"
set "urls_paths[6]=https://zenodo.org/records/13293150/files/output000.mp3|.\resource\songs"
set "urls_paths[7]=https://zenodo.org/records/13293150/files/output001.mp3|.\resource\songs"
set "urls_paths[8]=https://zenodo.org/records/13293150/files/output002.mp3|.\resource\songs"
set "urls_paths[9]=https://zenodo.org/records/13293150/files/output003.mp3|.\resource\songs"
set "urls_paths[10]=https://zenodo.org/records/13293150/files/output004.mp3|.\resource\songs"
set "urls_paths[11]=https://zenodo.org/records/13293150/files/output005.mp3|.\resource\songs"
set "urls_paths[12]=https://zenodo.org/records/13293150/files/output006.mp3|.\resource\songs"
set "urls_paths[13]=https://zenodo.org/records/13293150/files/output007.mp3|.\resource\songs"
set "urls_paths[14]=https://zenodo.org/records/13293150/files/output008.mp3|.\resource\songs"
set "urls_paths[15]=https://zenodo.org/records/13293150/files/output009.mp3|.\resource\songs"
set "urls_paths[16]=https://zenodo.org/records/13293150/files/output010.mp3|.\resource\songs"

rem 循环下载所有文件并保存到指定路径
for /L %%i in (0,1,16) do (
    for /f "tokens=1,2 delims=|" %%a in ("!urls_paths[%%i]!") do (
        if not exist "%%b" mkdir "%%b"
        echo 正在下载 %%a 到 %%b
        curl -o "%%b\%%~nxa" %%a
    )
)

echo 所有文件已成功下载到指定目录
endlocal
pause


rem set HF_ENDPOINT=https://hf-mirror.com
streamlit run webui.py --browser.gatherUsageStats=False --server.enableCORS=True
