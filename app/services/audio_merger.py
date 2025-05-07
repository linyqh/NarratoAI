import os
import json
import subprocess
import edge_tts
from edge_tts import submaker
from pydub import AudioSegment
from typing import List, Dict
from loguru import logger
from app.utils import utils


def check_ffmpeg():
    """检查FFmpeg是否已安装"""
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def merge_audio_files(task_id: str, total_duration: float, list_script: list):
    """
    合并音频文件
    
    Args:
        task_id: 任务ID
        total_duration: 总时长
        list_script: 完整脚本信息，包含duration时长和audio路径
    
    Returns:
        str: 合并后的音频文件路径
    """
    # 检查FFmpeg是否安装
    if not check_ffmpeg():
        logger.error("FFmpeg未安装，无法合并音频文件")
        return None

    # 创建一个空的音频片段
    final_audio = AudioSegment.silent(duration=total_duration * 1000)  # 总时长以毫秒为单位

    # 计算每个片段的开始位置（基于duration字段）
    current_position = 0  # 初始位置（秒）
    
    # 遍历脚本中的每个片段
    for segment in list_script:
        try:
            # 获取片段时长（秒）
            duration = segment['duration']
            
            # 检查audio字段是否为空
            if segment['audio'] and os.path.exists(segment['audio']):
                # 加载TTS音频文件
                tts_audio = AudioSegment.from_file(segment['audio'])
                
                # 将TTS音频添加到最终音频
                final_audio = final_audio.overlay(tts_audio, position=current_position * 1000)
            else:
                # audio为空，不添加音频，仅保留间隔
                logger.info(f"片段 {segment.get('timestamp', '')} 没有音频文件，保留 {duration} 秒的间隔")
            
            # 更新下一个片段的开始位置
            current_position += duration

        except Exception as e:
            logger.error(f"处理音频片段时出错: {str(e)}")
            # 即使处理失败，也要更新位置，确保后续片段位置正确
            if 'duration' in segment:
                current_position += segment['duration']
            continue

    # 保存合并后的音频文件
    output_audio_path = os.path.join(utils.task_dir(task_id), "merger_audio.mp3")
    final_audio.export(output_audio_path, format="mp3")
    logger.info(f"合并后的音频文件已保存: {output_audio_path}")

    return output_audio_path


def time_to_seconds(time_str):
    """
    将时间字符串转换为秒数，支持多种格式：
    1. 'HH:MM:SS,mmm' (时:分:秒,毫秒)
    2. 'MM:SS,mmm' (分:秒,毫秒)
    3. 'SS,mmm' (秒,毫秒)
    """
    try:
        # 处理毫秒部分
        if ',' in time_str:
            time_part, ms_part = time_str.split(',')
            ms = float(ms_part) / 1000
        else:
            time_part = time_str
            ms = 0

        # 分割时间部分
        parts = time_part.split(':')

        if len(parts) == 3:  # HH:MM:SS
            h, m, s = map(int, parts)
            seconds = h * 3600 + m * 60 + s
        elif len(parts) == 2:  # MM:SS
            m, s = map(int, parts)
            seconds = m * 60 + s
        else:  # SS
            seconds = int(parts[0])

        return seconds + ms
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing time {time_str}: {str(e)}")
        return 0.0


def extract_timestamp(filename):
    """
    从文件名中提取开始和结束时间戳
    例如: "audio_00_06,500-00_24,800.mp3" -> (6.5, 24.8)
    """
    try:
        # 从文件名中提取时间部分
        time_part = filename.split('_', 1)[1].split('.')[0]  # 获取 "00_06,500-00_24,800" 部分
        start_time, end_time = time_part.split('-')  # 分割成开始和结束时间

        # 将下划线格式转换回冒号格式
        start_time = start_time.replace('_', ':')
        end_time = end_time.replace('_', ':')

        # 将时间戳转换为秒
        start_seconds = time_to_seconds(start_time)
        end_seconds = time_to_seconds(end_time)

        return start_seconds, end_seconds
    except Exception as e:
        logger.error(f"Error extracting timestamp from {filename}: {str(e)}")
        return 0.0, 0.0


if __name__ == "__main__":
    # 示例用法
    total_duration = 90

    video_script = [
        {'picture': '【解说】好的，各位，欢迎回到我的频道！《庆余年 2》刚开播就给了我们一个王炸！范闲在北齐"死"了？这怎么可能！',
         'timestamp': '00:00:00-00:00:26',
         'narration': '好的各位，欢迎回到我的频道！《庆余年 2》刚开播就给了我们一个王炸！范闲在北齐"死"了？这怎么可能！上集片尾那个巨大的悬念，这一集就立刻揭晓了！范闲假死归来，他面临的第一个，也是最大的难关，就是如何面对他最敬爱的，同时也是最可怕的那个人——庆帝！',
         'OST': 0, 'duration': 26, 
         'audio': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_00_00-00_01_15.mp3'},
        {'picture': '【解说】上一集我们看到，范闲在北齐遭遇了惊天变故，生死不明！', 'timestamp': '00:01:15-00:01:29',
         'narration': '但我们都知道，他绝不可能就这么轻易退场！第二集一开场，范闲就已经秘密回到了京都。他的生死传闻，可不像我们想象中那样只是小范围流传，而是…',
         'OST': 0, 'duration': 14, 
         'audio': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_01_15-00_04_40.mp3'},
        {'picture': '画面切到王启年小心翼翼地向范闲汇报。', 'timestamp': '00:04:41-00:04:58',
         'narration': '我发现大人的死讯不光是在民间,在官场上也它传开了,所以呢,所以啊,可不是什么好事,将来您跟陛下怎么交代,这可是欺君之罪',
         'OST': 1, 'duration': 17, 
         'audio': ''},
        {'picture': '【解说】"欺君之罪"！在封建王朝，这可是抄家灭族的大罪！搁一般人，肯定脚底抹油溜之大吉了。',
         'timestamp': '00:04:58-00:05:20',
         'narration': '"欺君之罪"！在封建王朝，这可是抄家灭族的大罪！搁一般人，肯定脚底抹油溜之大吉了。但范闲是谁啊？他偏要反其道而行之！他竟然决定，直接去见庆帝！冒着天大的风险，用"假死"这个事实去赌庆帝的态度！',
         'OST': 0, 'duration': 22, 
         'audio': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_04_58-00_05_45.mp3'},
        {'picture': '【解说】但想见庆帝，哪有那么容易？范闲艺高人胆大，竟然选择了最激进的方式——闯宫！',
         'timestamp': '00:05:45-00:05:53',
         'narration': '但想见庆帝，哪有那么容易？范闲艺高人胆大，竟然选择了最激进的方式——闯宫！',
         'OST': 0, 'duration': 8, 
         'audio': '/Users/apple/Desktop/home/NarratoAI/storage/tasks/qyn2-2-demo/audio_00_05_45-00_06_00.mp3'},
        {'picture': '画面切换到范闲蒙面闯入皇宫，被侍卫包围的场景。', 'timestamp': '00:06:00-00:06:03',
         'narration': '抓刺客',
         'OST': 1, 'duration': 3, 
         'audio': ''}]

    output_file = merge_audio_files("test456", total_duration, video_script)
    print(output_file)
