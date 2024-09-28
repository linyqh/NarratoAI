import locale
import os
import requests
import threading
from typing import Any
from loguru import logger
import json
from uuid import uuid4
import urllib3
from datetime import datetime, timedelta

from app.models import const
from app.utils import check_script

urllib3.disable_warnings()


def get_response(status: int, data: Any = None, message: str = ""):
    obj = {
        "status": status,
    }
    if data:
        obj["data"] = data
    if message:
        obj["message"] = message
    return obj


def to_json(obj):
    try:
        # 定义一个辅助函数来处理不同类型的对象
        def serialize(o):
            # 如果对象是可序列化类型，直接返回
            if isinstance(o, (int, float, bool, str)) or o is None:
                return o
            # 如果对象是二进制数据，转换为base64编码的字符串
            elif isinstance(o, bytes):
                return "*** binary data ***"
            # 如果对象是字典，递归处理每个键值对
            elif isinstance(o, dict):
                return {k: serialize(v) for k, v in o.items()}
            # 如果对象是列表或元组，递归处理每个元素
            elif isinstance(o, (list, tuple)):
                return [serialize(item) for item in o]
            # 如果对象是自定义类型，尝试返回其__dict__属性
            elif hasattr(o, "__dict__"):
                return serialize(o.__dict__)
            # 其他情况返回None（或者可以选择抛出异常）
            else:
                return None

        # 使用serialize函数处理输入对象
        serialized_obj = serialize(obj)

        # 序列化处理后的对象为JSON字符串
        return json.dumps(serialized_obj, ensure_ascii=False, indent=4)
    except Exception as e:
        return None


def get_uuid(remove_hyphen: bool = False):
    u = str(uuid4())
    if remove_hyphen:
        u = u.replace("-", "")
    return u


def root_dir():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))


def storage_dir(sub_dir: str = "", create: bool = False):
    d = os.path.join(root_dir(), "storage")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if create and not os.path.exists(d):
        os.makedirs(d)

    return d


def resource_dir(sub_dir: str = ""):
    d = os.path.join(root_dir(), "resource")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    return d


def task_dir(sub_dir: str = ""):
    d = os.path.join(storage_dir(), "tasks")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if not os.path.exists(d):
        os.makedirs(d)
    return d


def font_dir(sub_dir: str = ""):
    d = resource_dir(f"fonts")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if not os.path.exists(d):
        os.makedirs(d)
    return d


def song_dir(sub_dir: str = ""):
    d = resource_dir(f"songs")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if not os.path.exists(d):
        os.makedirs(d)
    return d


def public_dir(sub_dir: str = ""):
    d = resource_dir(f"public")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if not os.path.exists(d):
        os.makedirs(d)
    return d


def run_in_background(func, *args, **kwargs):
    def run():
        try:
            func(*args, **kwargs)
        except Exception as e:
            logger.error(f"run_in_background error: {e}")

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def time_convert_seconds_to_hmsm(seconds) -> str:
    hours = int(seconds // 3600)
    seconds = seconds % 3600
    minutes = int(seconds // 60)
    milliseconds = int(seconds * 1000) % 1000
    seconds = int(seconds % 60)
    return "{:02d}:{:02d}:{:02d},{:03d}".format(hours, minutes, seconds, milliseconds)


def text_to_srt(idx: int, msg: str, start_time: float, end_time: float) -> str:
    start_time = time_convert_seconds_to_hmsm(start_time)
    end_time = time_convert_seconds_to_hmsm(end_time)
    srt = """%d
%s --> %s
%s
        """ % (
        idx,
        start_time,
        end_time,
        msg,
    )
    return srt


def str_contains_punctuation(word):
    for p in const.PUNCTUATIONS:
        if p in word:
            return True
    return False


def split_string_by_punctuations(s):
    result = []
    txt = ""

    previous_char = ""
    next_char = ""
    for i in range(len(s)):
        char = s[i]
        if char == "\n":
            result.append(txt.strip())
            txt = ""
            continue

        if i > 0:
            previous_char = s[i - 1]
        if i < len(s) - 1:
            next_char = s[i + 1]

        if char == "." and previous_char.isdigit() and next_char.isdigit():
            # 取现1万，按2.5%收取手续费, 2.5 中的 . 不能作为换行标记
            txt += char
            continue

        if char not in const.PUNCTUATIONS:
            txt += char
        else:
            result.append(txt.strip())
            txt = ""
    result.append(txt.strip())
    # filter empty string
    result = list(filter(None, result))
    return result


def md5(text):
    import hashlib

    return hashlib.md5(text.encode("utf-8")).hexdigest()


def get_system_locale():
    try:
        loc = locale.getdefaultlocale()
        # zh_CN, zh_TW return zh
        # en_US, en_GB return en
        language_code = loc[0].split("_")[0]
        return language_code
    except Exception as e:
        return "en"


def load_locales(i18n_dir):
    _locales = {}
    for root, dirs, files in os.walk(i18n_dir):
        for file in files:
            if file.endswith(".json"):
                lang = file.split(".")[0]
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    _locales[lang] = json.loads(f.read())
    return _locales


def parse_extension(filename):
    return os.path.splitext(filename)[1].strip().lower().replace(".", "")


def script_dir(sub_dir: str = ""):
    d = resource_dir(f"scripts")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if not os.path.exists(d):
        os.makedirs(d)
    return d


def video_dir(sub_dir: str = ""):
    d = resource_dir(f"videos")
    if sub_dir:
        d = os.path.join(d, sub_dir)
    if not os.path.exists(d):
        os.makedirs(d)
    return d


def split_timestamp(timestamp):
    """
    拆分时间戳
    """
    start, end = timestamp.split('-')
    start_hour, start_minute = map(int, start.split(':'))
    end_hour, end_minute = map(int, end.split(':'))

    start_time = '00:{:02d}:{:02d}'.format(start_hour, start_minute)
    end_time = '00:{:02d}:{:02d}'.format(end_hour, end_minute)

    return start_time, end_time


def reduce_video_time(txt: str, duration: float = 0.21531):
    """
    按照字数缩减视频时长，一个字耗时约 0.21531 s,
    Returns:
    """
    # 返回结果四舍五入为整数
    duration = len(txt) * duration
    return int(duration)


def get_current_country():
    """
    判断当前网络IP地址所在的国家
    """
    try:
        # 使用ipapi.co的免费API获取IP地址信息
        response = requests.get('https://ipapi.co/json/')
        data = response.json()

        # 获取国家名称
        country = data.get('country_name')

        if country:
            logger.debug(f"当前网络IP地址位于：{country}")
            return country
        else:
            logger.debug("无法确定当前网络IP地址所在的国家")
            return None

    except requests.RequestException:
        logger.error("获取IP地址信息时发生错误，请检查网络连接")
        return None


def time_to_seconds(time_str: str) -> float:
    parts = time_str.split(':')
    if len(parts) == 2:
        m, s = map(float, parts)
        return m * 60 + s
    elif len(parts) == 3:
        h, m, s = map(float, parts)
        return h * 3600 + m * 60 + s
    else:
        raise ValueError(f"Invalid time format: {time_str}")


def seconds_to_time(seconds: float) -> str:
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def calculate_total_duration(scenes):
    total_seconds = 0
    
    for scene in scenes:
        start, end = scene['timestamp'].split('-')
        start_time = datetime.strptime(start, '%M:%S')
        end_time = datetime.strptime(end, '%M:%S')
        
        duration = end_time - start_time
        total_seconds += duration.total_seconds()
    
    return total_seconds


def add_new_timestamps(scenes):
    """
    新增新视频的时间戳，并为"原生播放"的narration添加唯一标识符
    Args:
        scenes: 场景列表

    Returns:
        更新后的场景列表
    """
    current_time = timedelta()
    updated_scenes = []

    # 保存脚本前先检查脚本是否正确
    check_script.check_script(scenes, calculate_total_duration(scenes))

    for scene in scenes:
        new_scene = scene.copy()  # 创建场景的副本，以保留原始数据
        start, end = new_scene['timestamp'].split('-')
        start_time = datetime.strptime(start, '%M:%S')
        end_time = datetime.strptime(end, '%M:%S')
        duration = end_time - start_time

        new_start = current_time
        current_time += duration
        new_end = current_time

        # 将 timedelta 转换为分钟和秒
        new_start_str = f"{int(new_start.total_seconds() // 60):02d}:{int(new_start.total_seconds() % 60):02d}"
        new_end_str = f"{int(new_end.total_seconds() // 60):02d}:{int(new_end.total_seconds() % 60):02d}"

        new_scene['new_timestamp'] = f"{new_start_str}-{new_end_str}"

        # 为"原生播放"的narration添加唯一标识符
        if new_scene.get('narration') == "" or new_scene.get('narration') == None:
            unique_id = str(uuid4())[:8]  # 使用UUID的前8个字符作为唯一标识符
            new_scene['narration'] = f"原声播放_{unique_id}"

        updated_scenes.append(new_scene)

    return updated_scenes


def clean_model_output(output):
    """
    模型输出包含 ```json 标记时的处理
    """
    if "```json" in output:
        print("##########")
        output = output.replace("```json", "").replace("```", "")
    return output.strip()
