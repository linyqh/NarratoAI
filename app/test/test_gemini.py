import google.generativeai as genai
from app.config import config
import os

os.environ["HTTP_PROXY"] = config.proxy.get("http")
os.environ["HTTPS_PROXY"] = config.proxy.get("https")

genai.configure(api_key="")
model = genai.GenerativeModel("gemini-1.5-pro")


for i in range(50):
    response = model.generate_content("直接回复我文本'当前网络可用'")
    print(i, response.text)
