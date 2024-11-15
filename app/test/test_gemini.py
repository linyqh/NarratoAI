import google.generativeai as genai
from app.config import config
import os

os.environ["HTTP_PROXY"] = config.proxy.get("http")
os.environ["HTTPS_PROXY"] = config.proxy.get("https")

genai.configure(api_key=config.app.get("vision_gemini_api_key"))
model = genai.GenerativeModel("gemini-1.5-flash")
response = model.generate_content("Explain how AI works")
print(response.text)
