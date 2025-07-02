import os
import subprocess
import random
import traceback
from urllib.parse import urlencode
from datetime import datetime
import json

import requests
from typing import List, Optional
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

from app.config import config
from app.models.schema import VideoAspect, VideoConcatMode, MaterialInfo
from app.utils import utils
from app.utils import ffmpeg_utils

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
    支持格式: 'HH:MM:SS,mmm' (时:分:秒,毫秒)

    Args:
        time_str: 时间字符串,如 "00:00:20,100"

    Returns:
        float: 转换后的秒数(包含毫秒)
    """
    try:
        # 处理毫秒部分
        if ',' in time_str:
            time_part, ms_part = time_str.split(',')
            ms = int(ms_part) / 1000
        else:
            time_part = time_str
            ms = 0

        # 处理时分秒
        parts = time_part.split(':')
        if len(parts) == 3:  # HH:MM:SS
            h, m, s = map(int, parts)
            seconds = h * 3600 + m * 60 + s
        else:
            raise ValueError("时间格式必须为 HH:MM:SS,mmm")

        return seconds + ms

    except ValueError as e:
        logger.error(f"时间格式错误: {time_str}")
        raise ValueError(f"时间格式错误: 必须为 HH:MM:SS,mmm 格式") from e


def format_timestamp(seconds: float) -> str:
    """
    将秒数转换为可读的时间格式 (HH:MM:SS,mmm)

    Args:
        seconds: 秒数(可包含毫秒)

    Returns:
        str: 格式化的时间字符串,如 "00:00:20,100"
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds_remain = seconds % 60
    whole_seconds = int(seconds_remain)
    milliseconds = int((seconds_remain - whole_seconds) * 1000)

    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def _detect_hardware_acceleration() -> Optional[str]:
    """
    检测系统可用的硬件加速器

    Returns:
        Optional[str]: 硬件加速参数，如果不支持则返回None
    """
    # 使用集中式硬件加速检测
    hwaccel_type = ffmpeg_utils.get_ffmpeg_hwaccel_type()
    return hwaccel_type


def save_clip_video(timestamp: str, origin_video: str, save_dir: str = "") -> str:
    """
    保存剪辑后的视频

    Args:
        timestamp: 需要裁剪的时间戳,格式为 'HH:MM:SS,mmm-HH:MM:SS,mmm'
                  例如: '00:00:00,000-00:00:20,100'
        origin_video: 原视频路径
        save_dir: 存储目录

    Returns:
        dict: 裁剪后的视频路径,格式为 {timestamp: video_path}
    """
    # 使用新的路径结构
    if not save_dir:
        base_dir = os.path.join(utils.temp_dir(), "clip_video")
        video_hash = utils.md5(origin_video)
        save_dir = os.path.join(base_dir, video_hash)

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # 解析时间戳
    start_str, end_str = timestamp.split('-')

    # 格式化输出文件名（使用连字符替代冒号和逗号）
    safe_start_time = start_str.replace(':', '-').replace(',', '-')
    safe_end_time = end_str.replace(':', '-').replace(',', '-')
    output_filename = f"vid_{safe_start_time}@{safe_end_time}.mp4"
    video_path = os.path.join(save_dir, output_filename)

    # 如果视频已存在，直接返回
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"视频已存在: {video_path}")
        return video_path

    try:
        # 检查视频是否存在
        if not os.path.exists(origin_video):
            logger.error(f"源视频文件不存在: {origin_video}")
            return ''

        # 获取视频总时长
        try:
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", origin_video]
            total_duration = float(subprocess.check_output(probe_cmd).decode('utf-8').strip())
        except subprocess.CalledProcessError as e:
            logger.error(f"获取视频时长失败: {str(e)}")
            return ''

        # 计算时间点
        start = time_to_seconds(start_str)
        end = time_to_seconds(end_str)

        # 验证时间段
        if start >= total_duration:
            logger.warning(f"起始时间 {format_timestamp(start)} ({start:.3f}秒) 超出视频总时长 {format_timestamp(total_duration)} ({total_duration:.3f}秒)")
            return ''

        if end > total_duration:
            logger.warning(f"结束时间 {format_timestamp(end)} ({end:.3f}秒) 超出视频总时长 {format_timestamp(total_duration)} ({total_duration:.3f}秒)，将自动调整为视频结尾")
            end = total_duration

        if end <= start:
            logger.warning(f"结束时间 {format_timestamp(end)} 必须大于起始时间 {format_timestamp(start)}")
            return ''

        # 计算剪辑时长
        duration = end - start
        # logger.info(f"开始剪辑视频: {format_timestamp(start)} - {format_timestamp(end)}，时长 {format_timestamp(duration)}")

        # 获取硬件加速选项
        hwaccel = _detect_hardware_acceleration()
        hwaccel_args = []
        if hwaccel:
            hwaccel_args = ffmpeg_utils.get_ffmpeg_hwaccel_args()

        # 转换为FFmpeg兼容的时间格式（逗号替换为点）
        ffmpeg_start_time = start_str.replace(',', '.')
        ffmpeg_end_time = end_str.replace(',', '.')

        # 构建FFmpeg命令 - 使用新的智能编码器选择
        encoder = ffmpeg_utils.get_optimal_ffmpeg_encoder()

        ffmpeg_cmd = [
            "ffmpeg", "-y", *hwaccel_args,
            "-i", origin_video,
            "-ss", ffmpeg_start_time,
            "-to", ffmpeg_end_time,
            "-c:v", encoder,
            "-c:a", "aac",
            "-strict", "experimental",
            video_path
        ]

        # 根据编码器类型添加特定参数
        if "nvenc" in encoder:
            ffmpeg_cmd.insert(-1, "-preset")
            ffmpeg_cmd.insert(-1, "medium")
        elif "videotoolbox" in encoder:
            ffmpeg_cmd.insert(-1, "-profile:v")
            ffmpeg_cmd.insert(-1, "high")
        elif "qsv" in encoder:
            ffmpeg_cmd.insert(-1, "-preset")
            ffmpeg_cmd.insert(-1, "medium")
        elif encoder == "libx264":
            ffmpeg_cmd.insert(-1, "-preset")
            ffmpeg_cmd.insert(-1, "medium")
            ffmpeg_cmd.insert(-1, "-crf")
            ffmpeg_cmd.insert(-1, "23")

        # 执行FFmpeg命令
        # logger.info(f"裁剪视频片段: {timestamp} -> {ffmpeg_start_time}到{ffmpeg_end_time}")
        # logger.debug(f"执行命令: {' '.join(ffmpeg_cmd)}")

        # 在Windows系统上使用UTF-8编码处理输出，避免GBK编码错误
        is_windows = os.name == 'nt'
        if is_windows:
            process = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',  # 明确指定编码为UTF-8
                text=True,
                check=False  # 不抛出异常，我们会检查返回码
            )
        else:
            process = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False  # 不抛出异常，我们会检查返回码
            )

        # 检查是否成功
        if process.returncode != 0:
            logger.error(f"视频剪辑失败: {process.stderr}")
            if os.path.exists(video_path):
                os.remove(video_path)
            return ''

        # 验证生成的视频文件
        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
            # 检查视频是否可播放
            probe_cmd = ["ffprobe", "-v", "error", video_path]
            # 在Windows系统上使用UTF-8编码
            if is_windows:
                validate_result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
            else:
                validate_result = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if validate_result.returncode == 0:
                logger.info(f"视频剪辑成功: {video_path}")
                return video_path

        logger.error("视频文件验证失败")
        if os.path.exists(video_path):
            os.remove(video_path)
        return ''

    except Exception as e:
        logger.error(f"视频剪辑过程中发生错误: \n{str(traceback.format_exc())}")
        if os.path.exists(video_path):
            os.remove(video_path)
        return ''


def clip_videos(task_id: str, timestamp_terms: List[str], origin_video: str, progress_callback=None) -> dict:
    """
    剪辑视频
    Args:
        task_id: 任务id
        timestamp_terms: 需要剪辑的时间戳列表，如:['00:00:00,000-00:00:20,100', '00:00:43,039-00:00:46,959']
        origin_video: 原视频路径
        progress_callback: 进度回调函数

    Returns:
        剪辑后的视频路径
    """
    video_paths = {}
    total_items = len(timestamp_terms)
    for index, item in enumerate(timestamp_terms):
        material_directory = config.app.get("material_directory", "").strip()
        try:
            saved_video_path = save_clip_video(timestamp=item, origin_video=origin_video, save_dir=material_directory)
            if saved_video_path:
                video_paths.update({index+1:saved_video_path})

            # 更新进度
            if progress_callback:
                progress_callback(index + 1, total_items)
        except Exception as e:
            logger.error(f"视频裁剪失败: {utils.to_json(item)} =>\n{str(traceback.format_exc())}")
            return {}

    logger.success(f"裁剪 {len(video_paths)} videos")
    # logger.debug(json.dumps(video_paths, indent=4, ensure_ascii=False))
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
