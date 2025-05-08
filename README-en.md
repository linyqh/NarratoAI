
<div align="center">
<h1 align="center" style="font-size: 2cm;"> NarratoAI 😎📽️ </h1>
<h3 align="center">An all-in-one AI-powered tool for film commentary and automated video editing.🎬🎞️ </h3>


<h3>📖 English | <a href="README.md">简体中文</a> | <a href="README-ja.md">日本語</a> </h3>
<div align="center">

[//]: # (  <a href="https://trendshift.io/repositories/8731" target="_blank"><img src="https://trendshift.io/api/badge/repositories/8731" alt="harry0703%2FNarratoAI | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>)
</div>
<br>
NarratoAI is an automated video narration tool that provides an all-in-one solution for script writing, automated video editing, voice-over, and subtitle generation, powered by LLM to enhance efficient content creation.
<br>

[![madewithlove](https://img.shields.io/badge/made_with-%E2%9D%A4-red?style=for-the-badge&labelColor=orange)](https://github.com/linyqh/NarratoAI)
[![GitHub license](https://img.shields.io/github/license/linyqh/NarratoAI?style=for-the-badge)](https://github.com/linyqh/NarratoAI/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/linyqh/NarratoAI?style=for-the-badge)](https://github.com/linyqh/NarratoAI/issues)
[![GitHub stars](https://img.shields.io/github/stars/linyqh/NarratoAI?style=for-the-badge)](https://github.com/linyqh/NarratoAI/stargazers)

<a href="https://github.com/linyqh/NarratoAI/wiki" target="_blank">💬 Join the open source community to get project updates and the latest news.</a>

<h3>Home</h3>

![](docs/index-en.png)

<h3>Video Review Interface</h3>

![](docs/check-en.png)

</div>

## Future Plans 🥳 
- [x] Windows Integration Pack Release
- [ ] Optimized the story generation process and improved the generation effect 
- [ ] Support local large model MiniCPM-V 
- [ ] Support local large model Qwen2-VL 
- [ ] ...

## System Requirements 📦

- Recommended minimum: CPU with 4 cores or more, 8GB RAM or more, GPU is not required
- Windows 10 or MacOS 11.0 or above

## Quick Start 🚀
### 1. Apply for Google AI Studio Account
1. Visit https://aistudio.google.com/app/prompts/new_chat to apply for an account.
2. Click `Get API Key` to request an API Key.
3. Enter the obtained API Key into the `gemini_api_key` setting in the `config.example.toml` file.

### 2. Configure Proxy VPN
> The method to configure VPN is not restricted, as long as you can access Google's network. Here, `clash` is used as an example.
1. Note the port of the clash service, usually `http://127.0.0.1:7890`.
2. If the port is not `7890`, modify the `VPN_PROXY_URL` in the `docker-compose.yml` file to your proxy address.
   ```yaml
   environment:
     - "VPN_PROXY_URL=http://host.docker.internal:7890" # Change to your proxy port; host.docker.internal represents the IP of the physical machine.
    ```

3. (Optional) Or modify the `proxy` settings in the `config.example.toml` file.
   ```toml
   [proxy]
    ### Use a proxy to access the Pexels API
    ### Format: "http://<username>:<password>@<proxy>:<port>"
    ### Example: "http://user:pass@proxy:1234"
    ### Doc: https://requests.readthedocs.io/en/latest/user/advanced/#proxies

    http = "http://xx.xx.xx.xx:7890"
    https = "http://xx.xx.xx.xx:7890"
   ```


### 3. Get Started 📥 with the Modpack (for Windows users)
NarratoAI Modpack v0.1.2 is released 🚀 

Hurry up and follow the WeChat public account [NarratoAI助手] and reply to the keyword [整合包] to get the latest download link! Give it a try! 

Note: 
- Currently only available for Windows, Mac version is in development, Linux version will be available in a future release.



### 4. Get started 🐳 with docker (for Mac and Linux users)
#### ① clone project, Start Docker
```shell
git clone https://github.com/linyqh/NarratoAI.git
cd NarratoAI
docker-compose up
```
#### ② Access the Web Interface

Open your browser and go to http://127.0.0.1:8501

#### ③ Access the API Documentation

Open your browser and go to http://127.0.0.1:8080/docs or http://127.0.0.1:8080/redoc

## Usage
#### 1. Basic Configuration, Select Model, Enter API Key, and Choose Model
> Currently, only the `Gemini` model is supported. Other modes will be added in future updates. Contributions are welcome via [PR](https://github.com/linyqh/NarratoAI/pulls) to join in the development 🎉🎉🎉
<div align="center">
  <img src="docs/img001-en.png" alt="001" width="1000"/>
</div>

#### 2. Select the Video for Narration and Click to Generate Video Script
> A demo video is included in the platform. To use your own video, place the mp4 file in the `resource/videos` directory and refresh your browser.
> Note: The filename can be anything, but it must not contain Chinese characters, special characters, spaces, backslashes, etc.
<div align="center">
  <img src="docs/img002-en.png" alt="002" width="400"/>
</div>

#### 3. Save the Script and Start Editing
> After saving the script, refresh the browser, and the newly generated `.json` script file will appear in the script file dropdown. Select the json file and video to start editing.
<div align="center">
  <img src="docs/img003-en.png" alt="003" width="400"/>
</div>

#### 4. Review the Video; if there are segments that don't meet the rules, click to regenerate or manually edit them.
<div align="center">
  <img src="docs/img004-en.png" alt="003" width="1000"/>
</div>

#### 5. Configure Basic Video Parameters
<div align="center">
  <img src="docs/img005-en.png" alt="003" width="700"/>
</div>

#### 6. Start Generating
<div align="center">
  <img src="docs/img006-en.png" alt="003" width="1000"/>
</div>

#### 7. Video Generation Complete
<div align="center">
  <img src="docs/img007-en.png" alt="003" width="1000"/>
</div>

## Development 💻
1. Install Dependencies
```shell
conda create -n narratoai python=3.10
conda activate narratoai
cd narratoai
pip install -r requirements.txt
```
2. Install ImageMagick
###### Windows:

- Download https://imagemagick.org/archive/binaries/ImageMagick-7.1.1-38-Q16-x64-static.exe
- Install the downloaded ImageMagick, ensuring you do not change the installation path
- Update `imagemagick_path` in the `config.toml` file to your actual installation path (typically `C:\Program Files\ImageMagick-7.1.1-Q16\magick.exe`)

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

3. initiate webui
```shell
streamlit run ./webui/Main.py --browser.serverAddress=127.0.0.1 --server.enableCORS=True --browser.gatherUsageStats=False
```
4. Access http://127.0.0.1:8501

## Feedback & Suggestions 📢

### 👏 1. You can submit [issues](https://github.com/linyqh/NarratoAI/issues) or [pull requests](https://github.com/linyqh/NarratoAI/pulls) 

### 💬 2. [Join the open source community exchange group]((https://github.com/linyqh/NarratoAI/wiki))

### 👉 3. [frequently asked questions](https://thread-marsupial-df8.notion.site/105866888dab80988650fa063b1df4eb)

## Reference Projects 📚
- https://github.com/FujiwaraChoki/MoneyPrinter
- https://github.com/harry0703/MoneyPrinterTurbo

This project was refactored based on the above projects with the addition of video narration features. Thanks to the original authors for their open-source spirit 🥳🥳🥳 

## License 📝

Click to view the [`LICENSE`](LICENSE) file

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=linyqh/NarratoAI&type=Date)](https://star-history.com/#linyqh/NarratoAI&Date)
