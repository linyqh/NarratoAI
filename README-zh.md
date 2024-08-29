
<div align="center">
<h1 align="center" style="font-size: 2cm;"> NarratoAI 😎📽️ </h1>
<h3 align="center">一站式 AI 影视解说+自动化剪辑工具🎬🎞️ </h3>


<h3>📖 <a href="README.md">English</a> | 简体中文 </h3>
<div align="center">

[//]: # (  <a href="https://trendshift.io/repositories/8731" target="_blank"><img src="https://trendshift.io/api/badge/repositories/8731" alt="harry0703%2FNarratoAI | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>)
</div>
<br>
NarratoAI 是一个自动化影视解说工具，基于LLM实现文案撰写、自动化视频剪辑、配音和字幕生成的一站式流程，助力高效内容创作。
<br>

[![madewithlove](https://img.shields.io/badge/made_with-%E2%9D%A4-red?style=for-the-badge&labelColor=orange)](https://github.com/linyqh/NarratoAI)
[![GitHub license](https://img.shields.io/github/license/linyqh/NarratoAI?style=for-the-badge)](https://github.com/linyqh/NarratoAI/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/linyqh/NarratoAI?style=for-the-badge)](https://github.com/linyqh/NarratoAI/issues)
[![GitHub stars](https://img.shields.io/github/stars/linyqh/NarratoAI?style=for-the-badge)](https://github.com/linyqh/NarratoAI/stargazers)

<a href="https://github.com/linyqh/NarratoAI/wiki" target="_blank">💬 加入开源社区，获取项目动态和最新资讯。</a>

<h3>首页</h3>

![](docs/index-zh.png)

<h3>视频审查界面</h3>

![](docs/check-zh.png)

</div>

## 配置要求 📦

- 建议最低 CPU 4核或以上，内存 8G 或以上，显卡非必须
- Windows 10 或 MacOS 11.0 以上系统

## 快速开始 🚀
### 申请 Google AI studio 账号
1. 访问 https://aistudio.google.com/app/prompts/new_chat 申请账号
2. 点击 `Get API Key` 申请 API Key
3. 申请的 API Key 填入 `config.example.toml` 文件中的 `gemini_api_key` 配置

### 配置 proxy VPN
> 配置vpn的方法不限，只要能正常访问 Google 网络即可，本文采用的是 chash
1. 记住 clash 服务的端口，一般为 `http://127.0.0.1:7890`
2. 若端口不为 `7890`，请修改 `docker-compose.yml` 文件中的 `VPN_PROXY_URL` 为你的代理地址
   ```yaml
   environment:
     - "VPN_PROXY_URL=http://host.docker.internal:7890" # 修改为你的代理端口；host.docker.internal表示物理机的IP
   ```
3. (可选)或者修改 `config.example.toml` 文件中的 `proxy` 配置
   ```toml
   [proxy]
    ### Use a proxy to access the Pexels API
    ### Format: "http://<username>:<password>@<proxy>:<port>"
    ### Example: "http://user:pass@proxy:1234"
    ### Doc: https://requests.readthedocs.io/en/latest/user/advanced/#proxies

    http = "http://xx.xx.xx.xx:7890"
    https = "http://xx.xx.xx.xx:7890"
   ```
### docker部署🐳
#### ① 拉取项目，启动Docker
```shell
git clone https://github.com/linyqh/NarratoAI.git
cd NarratoAI
docker-compose up
```
#### ② 访问Web界面

打开浏览器，访问 http://127.0.0.1:8501

#### ③ 访问API文档

打开浏览器，访问 http://127.0.0.1:8080/docs 或者 http://127.0.0.1:8080/redoc

## 使用方法
#### 1. 基础配置，选择模型，填入APIKey，选择模型
> 目前暂时只支持 `Gemini` 模型，其他模式待后续更新，欢迎大家提交 [PR](https://github.com/linyqh/NarratoAI/pulls)，参与开发 🎉🎉🎉
<div align="center">
  <img src="docs/img001-zh.png" alt="001" width="1000"/>
</div>

#### 2. 选择需要解说的视频，点击生成视频脚本
> 平台内置了一个演示视频，若要使用自己的视频，将mp4文件放在 `resource/videos` 目录下，刷新浏览器即可，
> 注意：文件名随意，但文件名不能包含中文，特殊字符，空格，反斜杠等
<div align="center">
  <img src="docs/img002-zh.png" alt="002" width="400"/>
</div>

#### 3. 保存脚本，开始剪辑
> 保存脚本后，刷新浏览器，在脚本文件的下拉框就会有新生成的 `.json` 脚本文件，选择json文件和视频就可以开始剪辑了。
<div align="center">
  <img src="docs/img003-zh.png" alt="003" width="400"/>
</div>

#### 4. 检查视频，若视频存在不符合规则的片段，可以点击重新生成或者手动编辑
<div align="center">
  <img src="docs/img004-zh.png" alt="003" width="1000"/>
</div>

#### 5. 配置视频基本参数
<div align="center">
  <img src="docs/img005-zh.png" alt="003" width="700"/>
</div>

#### 6. 开始生成
<div align="center">
  <img src="docs/img006-zh.png" alt="003" width="1000"/>
</div>

#### 7. 视频生成完成
<div align="center">
  <img src="docs/img007-zh.png" alt="003" width="1000"/>
</div>

## 开发 💻
1. 安装依赖
```shell
conda create -n narratoai python=3.10
conda activate narratoai
cd narratoai
pip install -r requirements.txt
```

2. 安装 ImageMagick
###### Windows:

- 下载 https://imagemagick.org/archive/binaries/ImageMagick-7.1.1-36-Q16-x64-static.exe
- 安装下载好的 ImageMagick，注意不要修改安装路径
- 修改 `配置文件 config.toml` 中的 `imagemagick_path` 为你的实际安装路径（一般在 `C:\Program Files\ImageMagick-7.1.1-Q16\magick.exe`）

###### MacOS:

```shell
brew install imagemagick
````

###### Ubuntu

```shell
sudo apt-get install imagemagick
```

###### CentOS

```shell
sudo yum install ImageMagick
```
3. 启动 webui
```shell
streamlit run ./webui/Main.py --browser.serverAddress=127.0.0.1 --server.enableCORS=True --browser.gatherUsageStats=False
```
4. 访问 http://127.0.0.1:8501


## 反馈建议 📢

### 👏👏👏 可以提交 [issue](https://github.com/linyqh/NarratoAI/issues)或者 [pull request](https://github.com/linyqh/NarratoAI/pulls) 🎉🎉🎉

## 参考项目 📚
- https://github.com/FujiwaraChoki/MoneyPrinter
- https://github.com/harry0703/MoneyPrinterTurbo

该项目基于以上项目重构而来，增加了影视解说功能，感谢大佬的开源精神 🥳🥳🥳 

## 许可证 📝

点击查看 [`LICENSE`](LICENSE) 文件

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=linyqh/NarratoAI&type=Date)](https://star-history.com/#linyqh/NarratoAI&Date)

