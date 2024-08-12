#!/bin/bash

# 从环境变量中加载VPN代理的配置URL
vpn_proxy_url="$VPN_PROXY_URL"
# 检查是否成功加载
if [ -z "$vpn_proxy_url" ]; then
    echo "VPN代理配置URL未设置，请检查环境变量VPN_PROXY_URL"
    exit 1
fi
# 使用VPN代理进行一些操作，比如通过代理下载文件
export http_proxy="$vpn_proxy_url"
export https_proxy="$vpn_proxy_url"

# 创建链接和路径的数组
declare -A urls_paths=(
    ["https://zenodo.org/records/13293144/files/MicrosoftYaHeiBold.ttc"]="./resource/fonts"
    ["https://zenodo.org/records/13293144/files/MicrosoftYaHeiNormal.ttc"]="./resource/fonts"
    ["https://zenodo.org/records/13293144/files/STHeitiLight.ttc"]="./resource/fonts"
    ["https://zenodo.org/records/13293144/files/STHeitiMedium.ttc"]="./resource/fonts"
    ["https://zenodo.org/records/13293144/files/UTM%20Kabel%20KT.ttf"]="./resource/fonts"
    ["https://zenodo.org/records/13293129/files/demo.mp4"]="./resource/videos"
    ["https://zenodo.org/records/13293150/files/output000.mp3"]="./resource/songs"
    ["https://zenodo.org/records/13293150/files/output001.mp3"]="./resource/songs"
    ["https://zenodo.org/records/13293150/files/output002.mp3"]="./resource/songs"
    ["https://zenodo.org/records/13293150/files/output003.mp3"]="./resource/songs"
    ["https://zenodo.org/records/13293150/files/output004.mp3"]="./resource/songs"
    ["https://zenodo.org/records/13293150/files/output005.mp3"]="./resource/songs"
    ["https://zenodo.org/records/13293150/files/output006.mp3"]="./resource/songs"
    ["https://zenodo.org/records/13293150/files/output007.mp3"]="./resource/songs"
    ["https://zenodo.org/records/13293150/files/output008.mp3"]="./resource/songs"
    ["https://zenodo.org/records/13293150/files/output009.mp3"]="./resource/songs"
    ["https://zenodo.org/records/13293150/files/output010.mp3"]="./resource/songs"
    # 添加更多链接及其对应的路径
)

# 循环下载所有文件并保存到指定路径
for url in "${!urls_paths[@]}"; do
    output_dir="${urls_paths[$url]}"
    mkdir -p "$output_dir"  # 创建目录（如果不存在）

    # 提取文件名
    filename=$(basename "$url")

    # 检查文件是否已经存在
    if [ -f "$output_dir/$filename" ]; then
        echo "文件 $filename 已经存在，跳过下载"
    else
        wget -P "$output_dir" "$url" &
    fi
done

# 等待所有下载完成
wait

echo "所有文件已成功下载到指定目录"


streamlit run ./webui/Main.py --browser.serverAddress="0.0.0.0" --server.enableCORS=True --browser.gatherUsageStats=False
