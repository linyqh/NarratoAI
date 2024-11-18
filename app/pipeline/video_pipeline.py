import requests
import json
import time
from typing import Dict, Any

class VideoPipeline:
    def __init__(self, base_url: str = "http://127.0.0.1:8080"):
        self.base_url = base_url
        
    def download_video(self, url: str, resolution: str = "1080p", 
                      output_format: str = "mp4", rename: str = None) -> Dict[str, Any]:
        """下载视频的第一步"""
        endpoint = f"{self.base_url}/api/v2/youtube/download"
        payload = {
            "url": url,
            "resolution": resolution,
            "output_format": output_format,
            "rename": rename or time.strftime("%Y-%m-%d")
        }
        
        response = requests.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()
    
    def generate_script(self, video_path: str, skip_seconds: int = 0,
                       threshold: int = 30, vision_batch_size: int = 10,
                       vision_llm_provider: str = "gemini") -> Dict[str, Any]:
        """生成脚本的第二步"""
        endpoint = f"{self.base_url}/api/v2/scripts/generate"
        payload = {
            "video_path": video_path,
            "skip_seconds": skip_seconds,
            "threshold": threshold,
            "vision_batch_size": vision_batch_size,
            "vision_llm_provider": vision_llm_provider
        }
        
        response = requests.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()
    
    def crop_video(self, video_path: str, script: list) -> Dict[str, Any]:
        """剪辑视频的第三步"""
        endpoint = f"{self.base_url}/api/v2/scripts/crop"
        payload = {
            "video_origin_path": video_path,
            "video_script": script
        }
        
        response = requests.post(endpoint, json=payload)
        response.raise_for_status()
        return response.json()
    
    def generate_final_video(self, task_id: str, video_path: str, 
                           script_path: str, script: list, subclip_videos: Dict[str, str]) -> Dict[str, Any]:
        """生成最终视频的第四步"""
        endpoint = f"{self.base_url}/api/v2/scripts/start-subclip"
        
        request_data = {
            "video_clip_json": script,
            "video_clip_json_path": script_path,
            "video_origin_path": video_path,
            "video_aspect": "16:9",
            "video_language": "zh-CN",
            "voice_name": "zh-CN-YunjianNeural",
            "voice_volume": 1,
            "voice_rate": 1.2,
            "voice_pitch": 1,
            "bgm_name": "random",
            "bgm_type": "random",
            "bgm_file": "",
            "bgm_volume": 0.3,
            "subtitle_enabled": True,
            "subtitle_position": "bottom",
            "font_name": "STHeitiMedium.ttc",
            "text_fore_color": "#FFFFFF",
            "text_background_color": "transparent",
            "font_size": 75,
            "stroke_color": "#000000",
            "stroke_width": 1.5,
            "custom_position": 70,
            "n_threads": 8
        }
        
        payload = {
            "request": request_data,
            "subclip_videos": subclip_videos
        }
        
        params = {"task_id": task_id}
        response = requests.post(endpoint, params=params, json=payload)
        response.raise_for_status()
        return response.json()
    
    def save_script_to_json(self, script: list) -> str:
        """保存脚本到json文件"""
        timestamp = time.strftime("%Y-%m%d-%H%M%S")
        script_path = f"E:\\projects\\NarratoAI\\resource\\scripts\\{timestamp}.json"
        
        try:
            with open(script_path, 'w', encoding='utf-8') as f:
                json.dump(script, f, ensure_ascii=False, indent=2)
            print(f"脚本已保存到: {script_path}")
            return script_path
        except Exception as e:
            print(f"保存脚本失败: {str(e)}")
            raise
    
    def run_pipeline(self, youtube_url: str) -> Dict[str, Any]:
        """运行完整的pipeline"""
        try:
            # 1. 下载视频
            print("开始下载视频...")
            download_result = self.download_video(youtube_url)
            video_path = download_result["output_path"]
            
            # 2. 生成脚本
            print("开始生成脚本...")
            script_result = self.generate_script(video_path)
            script = script_result["script"]
            
            # 2.1 保存脚本到json文件
            print("保存脚本到json文件...")
            script_path = self.save_script_to_json(script)
            script_result["script_path"] = script_path
            
            # 3. 剪辑视频
            print("开始剪辑视频...")
            crop_result = self.crop_video(video_path, script)
            subclip_videos = crop_result["subclip_videos"]
            
            # 4. 生成最终视频
            print("开始生成最终视频...")
            final_result = self.generate_final_video(
                crop_result["task_id"],
                video_path,
                script_path,
                script,
                subclip_videos
            )
            
            return {
                "status": "success",
                "download_result": download_result,
                "script_result": script_result,
                "crop_result": crop_result,
                "final_result": final_result
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

# 使用示例
if __name__ == "__main__":
    pipeline = VideoPipeline()
    result = pipeline.run_pipeline("https://www.youtube.com/watch?v=Kenm35gdqtk")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    result2 = pipeline.run_pipeline("https://www.youtube.com/watch?v=aEsHAcedzgw")
    print(json.dumps(result2, indent=2, ensure_ascii=False))
