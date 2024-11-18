import os
import subprocess
import random
import traceback
from urllib.parse import urlencode

import requests
from typing import List
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

from app.config import config
from app.models.schema import VideoAspect, VideoConcatMode, MaterialInfo
from app.utils import utils

requested_count = 0


def get_api_key(cfg_key: str):
    api_keys = config.app.get(cfg_key)
    if not api_keys:
        raise ValueError(
            f"\n\n##### {cfg_key} is not set #####\n\nPlease set it in the config.toml file: {config.config_file}\n\n"
            f"{utils.to_json(config.app)}"
        )

    # if only one key is provided, return it
    if isinstance(api_keys, str):
        return api_keys

    global requested_count
    requested_count += 1
    return api_keys[requested_count % len(api_keys)]


def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_orientation = aspect.name
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    headers = {"Authorization": api_key}
    # Build URL
    params = {"query": search_term, "per_page": 20, "orientation": video_orientation}
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url,
            headers=headers,
            proxies=config.proxy,
            verify=False,
            timeout=(30, 60),
        )
        response = r.json()
        video_items = []
        if "videos" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["videos"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["video_files"]
            # loop through each url to determine the best quality
            for video in video_files:
                w = int(video["width"])
                h = int(video["height"])
                if w == video_width and h == video_height:
                    item = MaterialInfo()
                    item.provider = "pexels"
                    item.url = video["link"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def search_videos_pixabay(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)

    video_width, video_height = aspect.to_resolution()

    api_key = get_api_key("pixabay_api_keys")
    # Build URL
    params = {
        "q": search_term,
        "video_type": "all",  # Accepted values: "all", "film", "animation"
        "per_page": 50,
        "key": api_key,
    }
    query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url, proxies=config.proxy, verify=False, timeout=(30, 60)
        )
        response = r.json()
        video_items = []
        if "hits" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["hits"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["videos"]
            # loop through each url to determine the best quality
            for video_type in video_files:
                video = video_files[video_type]
                w = int(video["width"])
                h = int(video["height"])
                if w >= video_width:
                    item = MaterialInfo()
                    item.provider = "pixabay"
                    item.url = video["url"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def save_video(video_url: str, save_dir: str = "") -> str:
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = video_url.split("?")[0]
    url_hash = utils.md5(url_without_query)
    video_id = f"vid-{url_hash}"
    video_path = f"{save_dir}/{video_id}.mp4"

    # if video already exists, return the path
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"video already exists: {video_path}")
        return video_path

    # if video does not exist, download it
    with open(video_path, "wb") as f:
        f.write(
            requests.get(
                video_url, proxies=config.proxy, verify=False, timeout=(60, 240)
            ).content
        )

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        try:
            clip = VideoFileClip(video_path)
            duration = clip.duration
            fps = clip.fps
            clip.close()
            if duration > 0 and fps > 0:
                return video_path
        except Exception as e:
            try:
                os.remove(video_path)
            except Exception as e:
                logger.warning(f"无效的视频文件: {video_path} => {str(e)}")
    return ""


def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
) -> List[str]:
    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0
    search_videos = search_videos_pexels
    if source == "pixabay":
        search_videos = search_videos_pixabay

    for search_term in search_terms:
        video_items = search_videos(
            search_term=search_term,
            minimum_duration=max_clip_duration,
            video_aspect=video_aspect,
        )
        logger.info(f"found {len(video_items)} videos for '{search_term}'")

        for item in video_items:
            if item.url not in valid_video_urls:
                valid_video_items.append(item)
                valid_video_urls.append(item.url)
                found_duration += item.duration

    logger.info(
        f"found total videos: {len(valid_video_items)}, required duration: {audio_duration} seconds, found duration: {found_duration} seconds"
    )
    video_paths = []

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    if video_contact_mode.value == VideoConcatMode.random.value:
        random.shuffle(valid_video_items)

    total_duration = 0.0
    for item in valid_video_items:
        try:
            logger.info(f"downloading video: {item.url}")
            saved_video_path = save_video(
                video_url=item.url, save_dir=material_directory
            )
            if saved_video_path:
                logger.info(f"video saved: {saved_video_path}")
                video_paths.append(saved_video_path)
                seconds = min(max_clip_duration, item.duration)
                total_duration += seconds
                if total_duration > audio_duration:
                    logger.info(
                        f"total duration of downloaded videos: {total_duration} seconds, skip downloading more"
                    )
                    break
        except Exception as e:
            logger.error(f"failed to download video: {utils.to_json(item)} => {str(e)}")
    logger.success(f"downloaded {len(video_paths)} videos")
    return video_paths


def time_to_seconds(time_str: str) -> float:
    """
    将时间字符串转换为秒数
    支持格式：
    1. "MM:SS" (分:秒)
    2. "SS" (纯秒数)
    """
    parts = time_str.split(':')
    if len(parts) == 2:
        minutes, seconds = map(float, parts)
        return minutes * 60 + seconds
    return float(time_str)


def format_timestamp(seconds: float) -> str:
    """
    将秒数转换为 "MM:SS" 格式的时间字符串
    """
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"


def save_clip_video(timestamp: str, origin_video: str, save_dir: str = "") -> dict:
    """
    保存剪辑后的视频
    Args:
        timestamp: 需要裁剪的单个时间戳，支持两种格式：
                  1. '00:36-00:40' (分:秒-分:秒)
                  2. 'SS-SS' (秒-秒)
        origin_video: 原视频路径
        save_dir: 存储目录

    Returns:
        裁剪后的视频路径，格式为 {timestamp: video_path}
    """
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    video_id = f"vid-{timestamp.replace(':', '_')}"
    video_path = f"{save_dir}/{video_id}.mp4"

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"video already exists: {video_path}")
        return {timestamp: video_path}

    try:
        # 先加载视频获取总时长
        video = VideoFileClip(origin_video)
        total_duration = video.duration
        
        # 获取目标时间段
        start_str, end_str = timestamp.split('-')
        start = time_to_seconds(start_str)
        end = time_to_seconds(end_str)
        
        # 验证时间段是否有效
        if start >= total_duration:
            logger.warning(f"起始时间 {format_timestamp(start)} ({start:.2f}秒) 超出视频总时长 {format_timestamp(total_duration)} ({total_duration:.2f}秒)")
            video.close()
            return {}
            
        if end > total_duration:
            logger.warning(f"结束时间 {format_timestamp(end)} ({end:.2f}秒) 超出视频总时长 {format_timestamp(total_duration)} ({total_duration:.2f}秒)，将自动调整为视频结尾")
            end = total_duration
            
        if end <= start:
            logger.warning(f"结束时间 {format_timestamp(end)} 必须大于起始时间 {format_timestamp(start)}")
            video.close()
            return {}
            
        # 剪辑视频
        duration = end - start
        logger.info(f"开始剪辑视频: {format_timestamp(start)} - {format_timestamp(end)}，时长 {format_timestamp(duration)}")
        subclip = video.subclip(start, end)
        
        try:
            # 检查视频是否有音频轨道并写入文件
            subclip.write_videofile(video_path, audio=(subclip.audio is not None), logger=None)
            
            # 验证生成的视频文件
            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                with VideoFileClip(video_path) as clip:
                    if clip.duration > 0 and clip.fps > 0:
                        return {timestamp: video_path}
                    
            raise ValueError("视频文件验证失败")
            
        except Exception as e:
            logger.warning(f"视频文件处理失败: {video_path} => {str(e)}")
            if os.path.exists(video_path):
                os.remove(video_path)
                
    except Exception as e:
        logger.warning(f"视频剪辑失败: \n{str(traceback.format_exc())}")
        if os.path.exists(video_path):
            os.remove(video_path)
    finally:
        # 确保视频对象被正确关闭
        try:
            video.close()
            if 'subclip' in locals():
                subclip.close()
        except:
            pass
    
    return {}


def clip_videos(task_id: str, timestamp_terms: List[str], origin_video: str, progress_callback=None) -> dict:
    """
    剪辑视频
    Args:
        task_id: 任务id
        timestamp_terms: 需要剪辑的时间戳列表，如:['00:00-00:20', '00:36-00:40', '07:07-07:22']
        origin_video: 原视频路径
        progress_callback: 进度回调函数

    Returns:
        剪辑后的视频路径
    """
    video_paths = {}
    total_items = len(timestamp_terms)
    for index, item in enumerate(timestamp_terms):
        material_directory = config.app.get("material_directory", "").strip()
        if material_directory == "task":
            material_directory = utils.task_dir(task_id)
        elif material_directory and not os.path.isdir(material_directory):
            material_directory = ""

        try:
            saved_video_path = save_clip_video(timestamp=item, origin_video=origin_video, save_dir=material_directory)
            if saved_video_path:
                logger.info(f"video saved: {saved_video_path}")
                video_paths.update(saved_video_path)
            
            # 更新进度
            if progress_callback:
                progress_callback(index + 1, total_items)
        except Exception as e:
            logger.error(f"视频裁剪失败: {utils.to_json(item)} =>\n{str(traceback.format_exc())}")
            return {}
    logger.success(f"裁剪 {len(video_paths)} videos")
    return video_paths


def merge_videos(video_paths, ost_list):
    """
    合并多个视频为一个视频，可选择是否保留每个视频的原声。

    :param video_paths: 视频文件路径列表
    :param ost_list: 是否保留原声的布尔值列表
    :return: 合并后的视频文件路径
    """
    if len(video_paths) != len(ost_list):
        raise ValueError("视频路径列表和保留原声列表长度必须相同")

    if not video_paths:
        raise ValueError("视频路径列表不能为空")

    # 准备临时文件列表
    temp_file = "temp_file_list.txt"
    with open(temp_file, "w") as f:
        for video_path, keep_ost in zip(video_paths, ost_list):
            if keep_ost:
                f.write(f"file '{video_path}'\n")
            else:
                # 如果不保留原声，创建一个无声的临时视频
                silent_video = f"silent_{os.path.basename(video_path)}"
                subprocess.run(["ffmpeg", "-i", video_path, "-c:v", "copy", "-an", silent_video], check=True)
                f.write(f"file '{silent_video}'\n")

    # 合并视频
    output_file = "combined.mp4"
    ffmpeg_cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", temp_file,
        "-c:v", "copy",
        "-c:a", "aac",
        "-strict", "experimental",
        output_file
    ]

    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"视频合并成功：{output_file}")
    except subprocess.CalledProcessError as e:
        print(f"视频合并失败：{e}")
        return None
    finally:
        # 清理临时文件
        os.remove(temp_file)
        for video_path, keep_ost in zip(video_paths, ost_list):
            if not keep_ost:
                silent_video = f"silent_{os.path.basename(video_path)}"
                if os.path.exists(silent_video):
                    os.remove(silent_video)

    return output_file


# 使用示例
# if __name__ == "__main__":
#     video_paths = ['/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-01_17-01_37.mp4', '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-00_00-00_06.mp4',
#                    '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-00_06-00_09.mp4', '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-01_03-01_10.mp4',
#                    '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-01_10-01_17.mp4', '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-00_24-00_27.mp4',
#                    '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-01_28-01_36.mp4', '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-00_32-00_41.mp4',
#                    '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-01_36-01_58.mp4', '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-00_12-00_15.mp4',
#                    '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-00_09-00_12.mp4', '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-02_12-02_25.mp4',
#                    '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-02_03-02_12.mp4', '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-01_58-02_03.mp4',
#                    '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-03_14-03_18.mp4', '/Users/apple/Desktop/home/NarratoAI/storage/cache_videos/vid-03_18-03_20.mp4']
#
#     ost_list = [True, False, False, False, False, False, False, False, True, False, False, False, False, False, False,
#                 False]
#
#     result = merge_videos(video_paths, ost_list)
#     if result:
#         print(f"合并后的视频文件：{result}")
#     else:
#         print("视频合并失败")
#


if __name__ == "__main__":
    save_clip_video('00:50-01:41', 'E:\\projects\\NarratoAI\\resource\\videos\\WeChat_20241110144511.mp4')
