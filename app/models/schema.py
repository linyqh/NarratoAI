import warnings
from enum import Enum
from typing import Any, List, Optional, Union

import pydantic
from pydantic import BaseModel, Field

# 忽略 Pydantic 的特定警告
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="Field name.*shadows an attribute in parent.*",
)


class AudioVolumeDefaults:
    """音量配置默认值常量类 - 确保全局一致性"""

    # 语音音量默认值
    VOICE_VOLUME = 1.0
    TTS_VOLUME = 1.0

    # 原声音量默认值 - 提高原声音量以平衡TTS
    ORIGINAL_VOLUME = 1.2

    # 背景音乐音量默认值
    BGM_VOLUME = 0.3

    # 音量范围
    MIN_VOLUME = 0.0
    MAX_VOLUME = 2.0  # 允许原声音量超过1.0以平衡TTS

    # 智能音量调整
    ENABLE_SMART_VOLUME = True  # 是否启用智能音量分析和调整


class VideoConcatMode(str, Enum):
    random = "random"
    sequential = "sequential"


class VideoAspect(str, Enum):
    landscape = "16:9"
    landscape_2 = "4:3"
    portrait = "9:16"
    portrait_2 = "3:4"
    square = "1:1"

    def to_resolution(self):
        if self == VideoAspect.landscape.value:
            return 1920, 1080
        elif self == VideoAspect.portrait.value:
            return 1080, 1920
        elif self == VideoAspect.square.value:
            return 1080, 1080
        return 1080, 1920


class _Config:
    arbitrary_types_allowed = True


@pydantic.dataclasses.dataclass(config=_Config)
class MaterialInfo:
    provider: str = "pexels"
    url: str = ""
    duration: int = 0


# VoiceNames = [
#     # zh-CN
#     "female-zh-CN-XiaoxiaoNeural",
#     "female-zh-CN-XiaoyiNeural",
#     "female-zh-CN-liaoning-XiaobeiNeural",
#     "female-zh-CN-shaanxi-XiaoniNeural",
#
#     "male-zh-CN-YunjianNeural",
#     "male-zh-CN-YunxiNeural",
#     "male-zh-CN-YunxiaNeural",
#     "male-zh-CN-YunyangNeural",
#
#     # "female-zh-HK-HiuGaaiNeural",
#     # "female-zh-HK-HiuMaanNeural",
#     # "male-zh-HK-WanLungNeural",
#     #
#     # "female-zh-TW-HsiaoChenNeural",
#     # "female-zh-TW-HsiaoYuNeural",
#     # "male-zh-TW-YunJheNeural",
#
#     # en-US
#     "female-en-US-AnaNeural",
#     "female-en-US-AriaNeural",
#     "female-en-US-AvaNeural",
#     "female-en-US-EmmaNeural",
#     "female-en-US-JennyNeural",
#     "female-en-US-MichelleNeural",
#
#     "male-en-US-AndrewNeural",
#     "male-en-US-BrianNeural",
#     "male-en-US-ChristopherNeural",
#     "male-en-US-EricNeural",
#     "male-en-US-GuyNeural",
#     "male-en-US-RogerNeural",
#     "male-en-US-SteffanNeural",
# ]


class VideoParams(BaseModel):
    """
    {
      "video_subject": "",
      "video_aspect": "横屏 16:9（西瓜视频）",
      "voice_name": "女生-晓晓",
      "bgm_name": "random",
      "font_name": "STHeitiMedium 黑体-中",
      "text_color": "#FFFFFF",
      "font_size": 60,
      "stroke_color": "#000000",
      "stroke_width": 1.5
    }
    """

    video_subject: str
    video_script: str = ""  # 用于生成视频的脚本
    video_terms: Optional[Union[str, list]] = None  # 用于生成视频的关键词
    video_aspect: Optional[VideoAspect] = VideoAspect.portrait.value
    video_concat_mode: Optional[VideoConcatMode] = VideoConcatMode.random.value
    video_clip_duration: Optional[int] = 5
    video_count: Optional[int] = 1

    video_source: Optional[str] = "pexels"
    video_materials: Optional[List[MaterialInfo]] = None  # 用于生成视频的素材

    video_language: Optional[str] = ""  # auto detect

    voice_name: Optional[str] = ""
    voice_volume: Optional[float] = AudioVolumeDefaults.VOICE_VOLUME
    voice_rate: Optional[float] = 1.0
    bgm_type: Optional[str] = "random"
    bgm_file: Optional[str] = ""
    bgm_volume: Optional[float] = AudioVolumeDefaults.BGM_VOLUME

    subtitle_enabled: Optional[bool] = True
    subtitle_position: Optional[str] = "bottom"  # top, bottom, center
    custom_position: float = 70.0
    font_name: Optional[str] = "STHeitiMedium.ttc"
    text_fore_color: Optional[str] = "#FFFFFF"
    text_background_color: Optional[str] = "transparent"

    font_size: int = 60
    stroke_color: Optional[str] = "#000000"
    stroke_width: float = 1.5
    n_threads: Optional[int] = 2
    paragraph_number: Optional[int] = 1





class VideoClipParams(BaseModel):
    """
    NarratoAI 数据模型
    """
    video_clip_json: Optional[list] = Field(default=[], description="LLM 生成的视频剪辑脚本内容")
    video_clip_json_path: Optional[str] = Field(default="", description="LLM 生成的视频剪辑脚本路径")
    video_origin_path: Optional[str] = Field(default="", description="原视频路径")
    video_aspect: Optional[VideoAspect] = Field(default=VideoAspect.portrait.value, description="视频比例")
    video_language: Optional[str] = Field(default="zh-CN", description="视频语言")

    # video_clip_duration: Optional[int] = 5      # 视频片段时长
    # video_count: Optional[int] = 1      # 视频片段数量
    # video_source: Optional[str] = "local"
    # video_concat_mode: Optional[VideoConcatMode] = VideoConcatMode.random.value

    voice_name: Optional[str] = Field(default="zh-CN-YunjianNeural", description="语音名称")
    voice_volume: Optional[float] = Field(default=AudioVolumeDefaults.VOICE_VOLUME, description="解说语音音量")
    voice_rate: Optional[float] = Field(default=1.0, description="语速")
    voice_pitch: Optional[float] = Field(default=1.0, description="语调")
    tts_engine: Optional[str] = Field(default="", description="TTS 引擎")
    bgm_name: Optional[str] = Field(default="random", description="背景音乐名称")
    bgm_type: Optional[str] = Field(default="random", description="背景音乐类型")
    bgm_file: Optional[str] = Field(default="", description="背景音乐文件")

    subtitle_enabled: bool = True
    font_name: str = "SimHei"  # 默认使用黑体
    font_size: int = 36
    text_fore_color: str = "white"              # 文本前景色
    text_back_color: Optional[str] = None       # 文本背景色
    stroke_color: str = "black"                 # 描边颜色
    stroke_width: float = 1.5                   # 描边宽度
    subtitle_position: str = "bottom"   # top, bottom, center, custom
    custom_position: float = 70.0       # 自定义位置

    n_threads: Optional[int] = Field(default=16, description="线程数")    # 线程数，有助于提升视频处理速度

    tts_volume: Optional[float] = Field(default=AudioVolumeDefaults.TTS_VOLUME, description="解说语音音量（后处理）")
    original_volume: Optional[float] = Field(default=AudioVolumeDefaults.ORIGINAL_VOLUME, description="视频原声音量")
    bgm_volume: Optional[float] = Field(default=AudioVolumeDefaults.BGM_VOLUME, description="背景音乐音量")





class SubtitlePosition(str, Enum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"

