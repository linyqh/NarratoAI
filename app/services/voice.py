import os
import re
import json
import traceback
import edge_tts
import asyncio
import requests
import uuid
from loguru import logger
from typing import List, Union, Tuple
from datetime import datetime
from xml.sax.saxutils import unescape
from edge_tts import submaker, SubMaker
# from edge_tts.submaker import mktimestamp  # 函数可能不存在，我们自己实现
from moviepy.video.tools import subtitles
try:
    from moviepy import AudioFileClip
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    logger.warning("moviepy 未安装，将使用估算方法计算音频时长")
import time

from app.config import config
from app.utils import utils


def mktimestamp(time_seconds: float) -> str:
    """
    将秒数转换为 SRT 时间戳格式

    Args:
        time_seconds: 时间（秒）

    Returns:
        str: SRT 格式的时间戳，如 "00:01:23.456"
    """
    hours = int(time_seconds // 3600)
    minutes = int((time_seconds % 3600) // 60)
    seconds = time_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def get_all_azure_voices(filter_locals=None) -> list[str]:
    if filter_locals is None:
        filter_locals = ["zh-CN", "en-US", "zh-HK", "zh-TW", "vi-VN"]
    voices_str = """
Name: af-ZA-AdriNeural
Gender: Female

Name: af-ZA-WillemNeural
Gender: Male

Name: am-ET-AmehaNeural
Gender: Male

Name: am-ET-MekdesNeural
Gender: Female

Name: ar-AE-FatimaNeural
Gender: Female

Name: ar-AE-HamdanNeural
Gender: Male

Name: ar-BH-AliNeural
Gender: Male

Name: ar-BH-LailaNeural
Gender: Female

Name: ar-DZ-AminaNeural
Gender: Female

Name: ar-DZ-IsmaelNeural
Gender: Male

Name: ar-EG-SalmaNeural
Gender: Female

Name: ar-EG-ShakirNeural
Gender: Male

Name: ar-IQ-BasselNeural
Gender: Male

Name: ar-IQ-RanaNeural
Gender: Female

Name: ar-JO-SanaNeural
Gender: Female

Name: ar-JO-TaimNeural
Gender: Male

Name: ar-KW-FahedNeural
Gender: Male

Name: ar-KW-NouraNeural
Gender: Female

Name: ar-LB-LaylaNeural
Gender: Female

Name: ar-LB-RamiNeural
Gender: Male

Name: ar-LY-ImanNeural
Gender: Female

Name: ar-LY-OmarNeural
Gender: Male

Name: ar-MA-JamalNeural
Gender: Male

Name: ar-MA-MounaNeural
Gender: Female

Name: ar-OM-AbdullahNeural
Gender: Male

Name: ar-OM-AyshaNeural
Gender: Female

Name: ar-QA-AmalNeural
Gender: Female

Name: ar-QA-MoazNeural
Gender: Male

Name: ar-SA-HamedNeural
Gender: Male

Name: ar-SA-ZariyahNeural
Gender: Female

Name: ar-SY-AmanyNeural
Gender: Female

Name: ar-SY-LaithNeural
Gender: Male

Name: ar-TN-HediNeural
Gender: Male

Name: ar-TN-ReemNeural
Gender: Female

Name: ar-YE-MaryamNeural
Gender: Female

Name: ar-YE-SalehNeural
Gender: Male

Name: az-AZ-BabekNeural
Gender: Male

Name: az-AZ-BanuNeural
Gender: Female

Name: bg-BG-BorislavNeural
Gender: Male

Name: bg-BG-KalinaNeural
Gender: Female

Name: bn-BD-NabanitaNeural
Gender: Female

Name: bn-BD-PradeepNeural
Gender: Male

Name: bn-IN-BashkarNeural
Gender: Male

Name: bn-IN-TanishaaNeural
Gender: Female

Name: bs-BA-GoranNeural
Gender: Male

Name: bs-BA-VesnaNeural
Gender: Female

Name: ca-ES-EnricNeural
Gender: Male

Name: ca-ES-JoanaNeural
Gender: Female

Name: cs-CZ-AntoninNeural
Gender: Male

Name: cs-CZ-VlastaNeural
Gender: Female

Name: cy-GB-AledNeural
Gender: Male

Name: cy-GB-NiaNeural
Gender: Female

Name: da-DK-ChristelNeural
Gender: Female

Name: da-DK-JeppeNeural
Gender: Male

Name: de-AT-IngridNeural
Gender: Female

Name: de-AT-JonasNeural
Gender: Male

Name: de-CH-JanNeural
Gender: Male

Name: de-CH-LeniNeural
Gender: Female

Name: de-DE-AmalaNeural
Gender: Female

Name: de-DE-ConradNeural
Gender: Male

Name: de-DE-FlorianMultilingualNeural
Gender: Male

Name: de-DE-KatjaNeural
Gender: Female

Name: de-DE-KillianNeural
Gender: Male

Name: de-DE-SeraphinaMultilingualNeural
Gender: Female

Name: el-GR-AthinaNeural
Gender: Female

Name: el-GR-NestorasNeural
Gender: Male

Name: en-AU-NatashaNeural
Gender: Female

Name: en-AU-WilliamNeural
Gender: Male

Name: en-CA-ClaraNeural
Gender: Female

Name: en-CA-LiamNeural
Gender: Male

Name: en-GB-LibbyNeural
Gender: Female

Name: en-GB-MaisieNeural
Gender: Female

Name: en-GB-RyanNeural
Gender: Male

Name: en-GB-SoniaNeural
Gender: Female

Name: en-GB-ThomasNeural
Gender: Male

Name: en-HK-SamNeural
Gender: Male

Name: en-HK-YanNeural
Gender: Female

Name: en-IE-ConnorNeural
Gender: Male

Name: en-IE-EmilyNeural
Gender: Female

Name: en-IN-NeerjaExpressiveNeural
Gender: Female

Name: en-IN-NeerjaNeural
Gender: Female

Name: en-IN-PrabhatNeural
Gender: Male

Name: en-KE-AsiliaNeural
Gender: Female

Name: en-KE-ChilembaNeural
Gender: Male

Name: en-NG-AbeoNeural
Gender: Male

Name: en-NG-EzinneNeural
Gender: Female

Name: en-NZ-MitchellNeural
Gender: Male

Name: en-NZ-MollyNeural
Gender: Female

Name: en-PH-JamesNeural
Gender: Male

Name: en-PH-RosaNeural
Gender: Female

Name: en-SG-LunaNeural
Gender: Female

Name: en-SG-WayneNeural
Gender: Male

Name: en-TZ-ElimuNeural
Gender: Male

Name: en-TZ-ImaniNeural
Gender: Female

Name: en-US-AnaNeural
Gender: Female

Name: en-US-AndrewNeural
Gender: Male

Name: en-US-AriaNeural
Gender: Female

Name: en-US-AvaNeural
Gender: Female

Name: en-US-BrianNeural
Gender: Male

Name: en-US-ChristopherNeural
Gender: Male

Name: en-US-EmmaNeural
Gender: Female

Name: en-US-EricNeural
Gender: Male

Name: en-US-GuyNeural
Gender: Male

Name: en-US-JennyNeural
Gender: Female

Name: en-US-MichelleNeural
Gender: Female

Name: en-US-RogerNeural
Gender: Male

Name: en-US-SteffanNeural
Gender: Male

Name: en-ZA-LeahNeural
Gender: Female

Name: en-ZA-LukeNeural
Gender: Male

Name: es-AR-ElenaNeural
Gender: Female

Name: es-AR-TomasNeural
Gender: Male

Name: es-BO-MarceloNeural
Gender: Male

Name: es-BO-SofiaNeural
Gender: Female

Name: es-CL-CatalinaNeural
Gender: Female

Name: es-CL-LorenzoNeural
Gender: Male

Name: es-CO-GonzaloNeural
Gender: Male

Name: es-CO-SalomeNeural
Gender: Female

Name: es-CR-JuanNeural
Gender: Male

Name: es-CR-MariaNeural
Gender: Female

Name: es-CU-BelkysNeural
Gender: Female

Name: es-CU-ManuelNeural
Gender: Male

Name: es-DO-EmilioNeural
Gender: Male

Name: es-DO-RamonaNeural
Gender: Female

Name: es-EC-AndreaNeural
Gender: Female

Name: es-EC-LuisNeural
Gender: Male

Name: es-ES-AlvaroNeural
Gender: Male

Name: es-ES-ElviraNeural
Gender: Female

Name: es-ES-XimenaNeural
Gender: Female

Name: es-GQ-JavierNeural
Gender: Male

Name: es-GQ-TeresaNeural
Gender: Female

Name: es-GT-AndresNeural
Gender: Male

Name: es-GT-MartaNeural
Gender: Female

Name: es-HN-CarlosNeural
Gender: Male

Name: es-HN-KarlaNeural
Gender: Female

Name: es-MX-DaliaNeural
Gender: Female

Name: es-MX-JorgeNeural
Gender: Male

Name: es-NI-FedericoNeural
Gender: Male

Name: es-NI-YolandaNeural
Gender: Female

Name: es-PA-MargaritaNeural
Gender: Female

Name: es-PA-RobertoNeural
Gender: Male

Name: es-PE-AlexNeural
Gender: Male

Name: es-PE-CamilaNeural
Gender: Female

Name: es-PR-KarinaNeural
Gender: Female

Name: es-PR-VictorNeural
Gender: Male

Name: es-PY-MarioNeural
Gender: Male

Name: es-PY-TaniaNeural
Gender: Female

Name: es-SV-LorenaNeural
Gender: Female

Name: es-SV-RodrigoNeural
Gender: Male

Name: es-US-AlonsoNeural
Gender: Male

Name: es-US-PalomaNeural
Gender: Female

Name: es-UY-MateoNeural
Gender: Male

Name: es-UY-ValentinaNeural
Gender: Female

Name: es-VE-PaolaNeural
Gender: Female

Name: es-VE-SebastianNeural
Gender: Male

Name: et-EE-AnuNeural
Gender: Female

Name: et-EE-KertNeural
Gender: Male

Name: fa-IR-DilaraNeural
Gender: Female

Name: fa-IR-FaridNeural
Gender: Male

Name: fi-FI-HarriNeural
Gender: Male

Name: fi-FI-NooraNeural
Gender: Female

Name: fil-PH-AngeloNeural
Gender: Male

Name: fil-PH-BlessicaNeural
Gender: Female

Name: fr-BE-CharlineNeural
Gender: Female

Name: fr-BE-GerardNeural
Gender: Male

Name: fr-CA-AntoineNeural
Gender: Male

Name: fr-CA-JeanNeural
Gender: Male

Name: fr-CA-SylvieNeural
Gender: Female

Name: fr-CA-ThierryNeural
Gender: Male

Name: fr-CH-ArianeNeural
Gender: Female

Name: fr-CH-FabriceNeural
Gender: Male

Name: fr-FR-DeniseNeural
Gender: Female

Name: fr-FR-EloiseNeural
Gender: Female

Name: fr-FR-HenriNeural
Gender: Male

Name: fr-FR-RemyMultilingualNeural
Gender: Male

Name: fr-FR-VivienneMultilingualNeural
Gender: Female

Name: ga-IE-ColmNeural
Gender: Male

Name: ga-IE-OrlaNeural
Gender: Female

Name: gl-ES-RoiNeural
Gender: Male

Name: gl-ES-SabelaNeural
Gender: Female

Name: gu-IN-DhwaniNeural
Gender: Female

Name: gu-IN-NiranjanNeural
Gender: Male

Name: he-IL-AvriNeural
Gender: Male

Name: he-IL-HilaNeural
Gender: Female

Name: hi-IN-MadhurNeural
Gender: Male

Name: hi-IN-SwaraNeural
Gender: Female

Name: hr-HR-GabrijelaNeural
Gender: Female

Name: hr-HR-SreckoNeural
Gender: Male

Name: hu-HU-NoemiNeural
Gender: Female

Name: hu-HU-TamasNeural
Gender: Male

Name: id-ID-ArdiNeural
Gender: Male

Name: id-ID-GadisNeural
Gender: Female

Name: is-IS-GudrunNeural
Gender: Female

Name: is-IS-GunnarNeural
Gender: Male

Name: it-IT-DiegoNeural
Gender: Male

Name: it-IT-ElsaNeural
Gender: Female

Name: it-IT-GiuseppeNeural
Gender: Male

Name: it-IT-IsabellaNeural
Gender: Female

Name: ja-JP-KeitaNeural
Gender: Male

Name: ja-JP-NanamiNeural
Gender: Female

Name: jv-ID-DimasNeural
Gender: Male

Name: jv-ID-SitiNeural
Gender: Female

Name: ka-GE-EkaNeural
Gender: Female

Name: ka-GE-GiorgiNeural
Gender: Male

Name: kk-KZ-AigulNeural
Gender: Female

Name: kk-KZ-DauletNeural
Gender: Male

Name: km-KH-PisethNeural
Gender: Male

Name: km-KH-SreymomNeural
Gender: Female

Name: kn-IN-GaganNeural
Gender: Male

Name: kn-IN-SapnaNeural
Gender: Female

Name: ko-KR-HyunsuNeural
Gender: Male

Name: ko-KR-InJoonNeural
Gender: Male

Name: ko-KR-SunHiNeural
Gender: Female

Name: lo-LA-ChanthavongNeural
Gender: Male

Name: lo-LA-KeomanyNeural
Gender: Female

Name: lt-LT-LeonasNeural
Gender: Male

Name: lt-LT-OnaNeural
Gender: Female

Name: lv-LV-EveritaNeural
Gender: Female

Name: lv-LV-NilsNeural
Gender: Male

Name: mk-MK-AleksandarNeural
Gender: Male

Name: mk-MK-MarijaNeural
Gender: Female

Name: ml-IN-MidhunNeural
Gender: Male

Name: ml-IN-SobhanaNeural
Gender: Female

Name: mn-MN-BataaNeural
Gender: Male

Name: mn-MN-YesuiNeural
Gender: Female

Name: mr-IN-AarohiNeural
Gender: Female

Name: mr-IN-ManoharNeural
Gender: Male

Name: ms-MY-OsmanNeural
Gender: Male

Name: ms-MY-YasminNeural
Gender: Female

Name: mt-MT-GraceNeural
Gender: Female

Name: mt-MT-JosephNeural
Gender: Male

Name: my-MM-NilarNeural
Gender: Female

Name: my-MM-ThihaNeural
Gender: Male

Name: nb-NO-FinnNeural
Gender: Male

Name: nb-NO-PernilleNeural
Gender: Female

Name: ne-NP-HemkalaNeural
Gender: Female

Name: ne-NP-SagarNeural
Gender: Male

Name: nl-BE-ArnaudNeural
Gender: Male

Name: nl-BE-DenaNeural
Gender: Female

Name: nl-NL-ColetteNeural
Gender: Female

Name: nl-NL-FennaNeural
Gender: Female

Name: nl-NL-MaartenNeural
Gender: Male

Name: pl-PL-MarekNeural
Gender: Male

Name: pl-PL-ZofiaNeural
Gender: Female

Name: ps-AF-GulNawazNeural
Gender: Male

Name: ps-AF-LatifaNeural
Gender: Female

Name: pt-BR-AntonioNeural
Gender: Male

Name: pt-BR-FranciscaNeural
Gender: Female

Name: pt-BR-ThalitaNeural
Gender: Female

Name: pt-PT-DuarteNeural
Gender: Male

Name: pt-PT-RaquelNeural
Gender: Female

Name: ro-RO-AlinaNeural
Gender: Female

Name: ro-RO-EmilNeural
Gender: Male

Name: ru-RU-DmitryNeural
Gender: Male

Name: ru-RU-SvetlanaNeural
Gender: Female

Name: si-LK-SameeraNeural
Gender: Male

Name: si-LK-ThiliniNeural
Gender: Female

Name: sk-SK-LukasNeural
Gender: Male

Name: sk-SK-ViktoriaNeural
Gender: Female

Name: sl-SI-PetraNeural
Gender: Female

Name: sl-SI-RokNeural
Gender: Male

Name: so-SO-MuuseNeural
Gender: Male

Name: so-SO-UbaxNeural
Gender: Female

Name: sq-AL-AnilaNeural
Gender: Female

Name: sq-AL-IlirNeural
Gender: Male

Name: sr-RS-NicholasNeural
Gender: Male

Name: sr-RS-SophieNeural
Gender: Female

Name: su-ID-JajangNeural
Gender: Male

Name: su-ID-TutiNeural
Gender: Female

Name: sv-SE-MattiasNeural
Gender: Male

Name: sv-SE-SofieNeural
Gender: Female

Name: sw-KE-RafikiNeural
Gender: Male

Name: sw-KE-ZuriNeural
Gender: Female

Name: sw-TZ-DaudiNeural
Gender: Male

Name: sw-TZ-RehemaNeural
Gender: Female

Name: ta-IN-PallaviNeural
Gender: Female

Name: ta-IN-ValluvarNeural
Gender: Male

Name: ta-LK-KumarNeural
Gender: Male

Name: ta-LK-SaranyaNeural
Gender: Female

Name: ta-MY-KaniNeural
Gender: Female

Name: ta-MY-SuryaNeural
Gender: Male

Name: ta-SG-AnbuNeural
Gender: Male

Name: ta-SG-VenbaNeural
Gender: Female

Name: te-IN-MohanNeural
Gender: Male

Name: te-IN-ShrutiNeural
Gender: Female

Name: th-TH-NiwatNeural
Gender: Male

Name: th-TH-PremwadeeNeural
Gender: Female

Name: tr-TR-AhmetNeural
Gender: Male

Name: tr-TR-EmelNeural
Gender: Female

Name: uk-UA-OstapNeural
Gender: Male

Name: uk-UA-PolinaNeural
Gender: Female

Name: ur-IN-GulNeural
Gender: Female

Name: ur-IN-SalmanNeural
Gender: Male

Name: ur-PK-AsadNeural
Gender: Male

Name: ur-PK-UzmaNeural
Gender: Female

Name: uz-UZ-MadinaNeural
Gender: Female

Name: uz-UZ-SardorNeural
Gender: Male

Name: vi-VN-HoaiMyNeural
Gender: Female

Name: vi-VN-NamMinhNeural
Gender: Male

Name: zh-CN-XiaoxiaoNeural
Gender: Female

Name: zh-CN-XiaoyiNeural
Gender: Female

Name: zh-CN-YunjianNeural
Gender: Male

Name: zh-CN-YunxiNeural
Gender: Male

Name: zh-CN-YunxiaNeural
Gender: Male

Name: zh-CN-YunyangNeural
Gender: Male

Name: zh-CN-liaoning-XiaobeiNeural
Gender: Female

Name: zh-CN-shaanxi-XiaoniNeural
Gender: Female

Name: zh-HK-HiuGaaiNeural
Gender: Female

Name: zh-HK-HiuMaanNeural
Gender: Female

Name: zh-HK-WanLungNeural
Gender: Male

Name: zh-TW-HsiaoChenNeural
Gender: Female

Name: zh-TW-HsiaoYuNeural
Gender: Female

Name: zh-TW-YunJheNeural
Gender: Male

Name: zu-ZA-ThandoNeural
Gender: Female

Name: zu-ZA-ThembaNeural
Gender: Male


Name: en-US-AvaMultilingualNeural-V2
Gender: Female

Name: en-US-AndrewMultilingualNeural-V2
Gender: Male

Name: en-US-EmmaMultilingualNeural-V2
Gender: Female

Name: en-US-BrianMultilingualNeural-V2
Gender: Male

Name: de-DE-FlorianMultilingualNeural-V2
Gender: Male

Name: de-DE-SeraphinaMultilingualNeural-V2
Gender: Female

Name: fr-FR-RemyMultilingualNeural-V2
Gender: Male

Name: fr-FR-VivienneMultilingualNeural-V2
Gender: Female

Name: zh-CN-XiaoxiaoMultilingualNeural-V2
Gender: Female

Name: zh-CN-YunxiNeural-V2
Gender: Male
    """.strip()
    voices = []
    name = ""
    for line in voices_str.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("Name: "):
            name = line[6:].strip()
        if line.startswith("Gender: "):
            gender = line[8:].strip()
            if name and gender:
                # voices.append({
                #     "name": name,
                #     "gender": gender,
                # })
                if filter_locals:
                    for filter_local in filter_locals:
                        if name.lower().startswith(filter_local.lower()):
                            voices.append(f"{name}-{gender}")
                else:
                    voices.append(f"{name}-{gender}")
                name = ""
    voices.sort()
    return voices


def parse_voice_name(name: str):
    # zh-CN-XiaoyiNeural-Female
    # zh-CN-YunxiNeural-Male
    # zh-CN-XiaoxiaoMultilingualNeural-V2-Female
    name = name.replace("-Female", "").replace("-Male", "").strip()
    return name


def is_azure_v2_voice(voice_name: str):
    voice_name = parse_voice_name(voice_name)
    if voice_name.endswith("-V2"):
        return voice_name.replace("-V2", "").strip()
    return ""


def should_use_azure_speech_services(voice_name: str) -> bool:
    """判断音色是否应该使用Azure Speech Services"""
    if not voice_name or is_soulvoice_voice(voice_name):
        return False

    voice_name = voice_name.strip()

    # 如果是带-V2后缀的，肯定是Azure Speech Services
    if voice_name.endswith("-V2"):
        return True

    # 检查是否为Azure官方音色格式 (如: zh-CN-YunzeNeural)
    # Azure音色通常格式为: [语言]-[地区]-[名称]Neural
    import re
    pattern = r'^[a-z]{2}-[A-Z]{2}-\w+Neural$'
    if re.match(pattern, voice_name):
        return True

    return False


def tts(
    text: str, voice_name: str, voice_rate: float, voice_pitch: float, voice_file: str, tts_engine: str
) -> Union[SubMaker, None]:
    logger.info(f"使用 TTS 引擎: '{tts_engine}', 语音: '{voice_name}'")

    if tts_engine == "tencent_tts":
        logger.info("分发到腾讯云 TTS")
        return tencent_tts(text, voice_name, voice_file, speed=voice_rate)
    
    if tts_engine == "qwen3_tts":
        logger.info("分发到 Qwen3 TTS", voice_name)
        return qwen3_tts(text, voice_name, voice_file, speed=voice_rate)
    
    if tts_engine == "soulvoice":
        logger.info("分发到 SoulVoice TTS")
        return soulvoice_tts(text, voice_name, voice_file, speed=voice_rate)

    if tts_engine == "azure_speech":
        if should_use_azure_speech_services(voice_name):
            logger.info("分发到 Azure Speech Services (V2)")
            return azure_tts_v2(text, voice_name, voice_file)
        logger.info("分发到 Edge TTS (Azure V1)")
        return azure_tts_v1(text, voice_name, voice_rate, voice_pitch, voice_file)
    
    if tts_engine == "edge_tts":
        logger.info("分发到 Edge TTS")
        return azure_tts_v1(text, voice_name, voice_rate, voice_pitch, voice_file)
    
    if tts_engine == "indextts2":
        logger.info("分发到 IndexTTS2")
        return indextts2_tts(text, voice_name, voice_file, speed=voice_rate)

    # Fallback for unknown engine - default to azure v1
    logger.warning(f"未知的 TTS 引擎: '{tts_engine}', 将默认使用 Edge TTS (Azure V1)。")
    return azure_tts_v1(text, voice_name, voice_rate, voice_pitch, voice_file)


def convert_rate_to_percent(rate: float) -> str:
    if rate == 1.0:
        return "+0%"
    percent = round((rate - 1.0) * 100)
    if percent > 0:
        return f"+{percent}%"
    else:
        return f"{percent}%"


def convert_pitch_to_percent(rate: float) -> str:
    if rate == 1.0:
        return "+0Hz"
    percent = round((rate - 1.0) * 100)
    if percent > 0:
        return f"+{percent}Hz"
    else:
        return f"{percent}Hz"


def azure_tts_v1(
    text: str, voice_name: str, voice_rate: float, voice_pitch: float, voice_file: str
) -> Union[SubMaker, None]:
    voice_name = parse_voice_name(voice_name)
    text = text.strip()
    rate_str = convert_rate_to_percent(voice_rate)
    pitch_str = convert_pitch_to_percent(voice_pitch)
    for i in range(3):
        try:
            logger.info(f"第 {i+1} 次使用 edge_tts 生成音频")

            async def _do() -> tuple[SubMaker, bytes]:
                communicate = edge_tts.Communicate(text, voice_name, rate=rate_str, pitch=pitch_str, proxy=config.proxy.get("http"))
                sub_maker = edge_tts.SubMaker()
                audio_data = bytes()  # 用于存储音频数据
                
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_data += chunk["data"]
                    elif chunk["type"] == "WordBoundary":
                        sub_maker.create_sub(
                            (chunk["offset"], chunk["duration"]), chunk["text"]
                        )
                return sub_maker, audio_data

            # 获取音频数据和字幕信息
            sub_maker, audio_data = asyncio.run(_do())
            
            # 验证数据是否有效
            if not sub_maker or not sub_maker.subs or not audio_data:
                logger.warning(f"failed, invalid data generated")
                if i < 2:
                    time.sleep(1)
                continue

            # 数据有效，写入文件
            with open(voice_file, "wb") as file:
                file.write(audio_data)
            return sub_maker
        except Exception as e:
            logger.error(f"生成音频文件时出错: {str(e)}")
            if i < 2:
                time.sleep(1)
    return None


def azure_tts_v2(text: str, voice_name: str, voice_file: str) -> Union[SubMaker, None]:
    # 直接使用官方音色名称，不需要V2后缀验证
    # Azure Speech Services 的音色名称如: zh-CN-YunzeNeural, en-US-AvaMultilingualNeural
    processed_voice_name = voice_name.strip()
    if not processed_voice_name:
        logger.error(f"invalid voice name: {voice_name} (empty)")
        raise ValueError(f"invalid voice name: {voice_name} (empty)")
    text = text.strip()

    # 检查Azure Speech SDK是否可用
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError as e:
        logger.error("Azure Speech SDK 未安装。请运行: pip install azure-cognitiveservices-speech")
        logger.error("或者使用 Edge TTS 引擎作为替代方案")
        return None

    def _format_duration_to_offset(duration) -> int:
        if isinstance(duration, str):
            time_obj = datetime.strptime(duration, "%H:%M:%S.%f")
            milliseconds = (
                (time_obj.hour * 3600000)
                + (time_obj.minute * 60000)
                + (time_obj.second * 1000)
                + (time_obj.microsecond // 1000)
            )
            return milliseconds * 10000

        if isinstance(duration, int):
            return duration

        return 0

    for i in range(3):
        try:
            logger.info(f"start, voice name: {processed_voice_name}, try: {i + 1}")

            sub_maker = SubMaker()

            def speech_synthesizer_word_boundary_cb(evt: speechsdk.SessionEventArgs):
                duration = _format_duration_to_offset(str(evt.duration))
                offset = _format_duration_to_offset(evt.audio_offset)
                sub_maker.subs.append(evt.text)
                sub_maker.offset.append((offset, offset + duration))

            # Creates an instance of a speech config with specified subscription key and service region.
            speech_key = config.azure.get("speech_key", "")
            service_region = config.azure.get("speech_region", "")
            audio_config = speechsdk.audio.AudioOutputConfig(
                filename=voice_file, use_default_speaker=True
            )
            speech_config = speechsdk.SpeechConfig(
                subscription=speech_key, region=service_region
            )
            speech_config.speech_synthesis_voice_name = processed_voice_name
            # speech_config.set_property(property_id=speechsdk.PropertyId.SpeechServiceResponse_RequestSentenceBoundary,
            #                            value='true')
            speech_config.set_property(
                property_id=speechsdk.PropertyId.SpeechServiceResponse_RequestWordBoundary,
                value="true",
            )

            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3
            )
            speech_synthesizer = speechsdk.SpeechSynthesizer(
                audio_config=audio_config, speech_config=speech_config
            )
            speech_synthesizer.synthesis_word_boundary.connect(
                speech_synthesizer_word_boundary_cb
            )

            result = speech_synthesizer.speak_text_async(text).get()
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.success(f"azure v2 speech synthesis succeeded: {voice_file}")
                return sub_maker
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = result.cancellation_details
                logger.error(
                    f"azure v2 speech synthesis canceled: {cancellation_details.reason}"
                )
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    logger.error(
                        f"azure v2 speech synthesis error: {cancellation_details.error_details}"
                    )
            if i < 2:  # 如果不是最后一次重试，则等待1秒
                time.sleep(1)
            logger.info(f"completed, output file: {voice_file}")
        except Exception as e:
            logger.error(f"failed, error: {str(e)}")
            if i < 2:  # 如果不是最后一次重试，则等待1秒
                time.sleep(3)
    return None


def _format_text(text: str) -> str:
    text = text.replace("\n", " ")
    text = text.replace("\"", " ")
    text = text.replace("[", " ")
    text = text.replace("]", " ")
    text = text.replace("(", " ")
    text = text.replace(")", " ")
    text = text.replace("）", " ")
    text = text.replace("（", " ")
    text = text.replace("{", " ")
    text = text.replace("}", " ")
    text = text.strip()
    return text


def create_subtitle_from_multiple(text: str, sub_maker_list: List[SubMaker], list_script: List[dict], 
                                  subtitle_file: str):
    """
    根据多个 SubMaker 对象、完整文本和原始脚本创建优化的字幕文件
    1. 使用原始脚本中的时间戳
    2. 跳过 OST 为 true 的部分
    3. 将字幕文件按照标点符号分割成多行
    4. 根据完整文本分段，保持原文的语句结构
    5. 生成新的字幕文件，时间戳包含小时单位
    """
    text = _format_text(text)
    sentences = utils.split_string_by_punctuations(text)

    def formatter(idx: int, start_time: str, end_time: str, sub_text: str) -> str:
        return f"{idx}\n{start_time.replace('.', ',')} --> {end_time.replace('.', ',')}\n{sub_text}\n"

    sub_items = []
    sub_index = 0
    sentence_index = 0

    try:
        sub_maker_index = 0
        for script_item in list_script:
            if script_item['OST']:
                continue

            start_time, end_time = script_item['timestamp'].split('-')
            if sub_maker_index >= len(sub_maker_list):
                logger.error(f"Sub maker list index out of range: {sub_maker_index}")
                break
            sub_maker = sub_maker_list[sub_maker_index]
            sub_maker_index += 1

            script_duration = utils.time_to_seconds(end_time) - utils.time_to_seconds(start_time)
            audio_duration = get_audio_duration(sub_maker)
            time_ratio = script_duration / audio_duration if audio_duration > 0 else 1

            current_sub = ""
            current_start = None
            current_end = None

            for offset, sub in zip(sub_maker.offset, sub_maker.subs):
                sub = unescape(sub).strip()
                sub_start = utils.seconds_to_time(utils.time_to_seconds(start_time) + offset[0] / 10000000 * time_ratio)
                sub_end = utils.seconds_to_time(utils.time_to_seconds(start_time) + offset[1] / 10000000 * time_ratio)
                
                if current_start is None:
                    current_start = sub_start
                current_end = sub_end
                
                current_sub += sub
                
                # 检查当前累积的字幕是否匹配下一个句子
                while sentence_index < len(sentences) and sentences[sentence_index] in current_sub:
                    sub_index += 1
                    line = formatter(
                        idx=sub_index,
                        start_time=current_start,
                        end_time=current_end,
                        sub_text=sentences[sentence_index].strip(),
                    )
                    sub_items.append(line)
                    current_sub = current_sub.replace(sentences[sentence_index], "", 1).strip()
                    current_start = current_end
                    sentence_index += 1

                # 如果当前字幕长度超过15个字符，也生成一个新的字幕项
                if len(current_sub) > 15:
                    sub_index += 1
                    line = formatter(
                        idx=sub_index,
                        start_time=current_start,
                        end_time=current_end,
                        sub_text=current_sub.strip(),
                    )
                    sub_items.append(line)
                    current_sub = ""
                    current_start = current_end

            # 处理剩余的文本
            if current_sub.strip():
                sub_index += 1
                line = formatter(
                    idx=sub_index,
                    start_time=current_start,
                    end_time=current_end,
                    sub_text=current_sub.strip(),
                )
                sub_items.append(line)

        if len(sub_items) == 0:
            logger.error("No subtitle items generated")
            return

        with open(subtitle_file, "w", encoding="utf-8") as file:
            file.write("\n".join(sub_items))

        logger.info(f"completed, subtitle file created: {subtitle_file}")
    except Exception as e:
        logger.error(f"failed, error: {str(e)}")
        traceback.print_exc()


def create_subtitle(sub_maker: submaker.SubMaker, text: str, subtitle_file: str):
    """
    优化字幕文件
    1. 将字幕文件按照标点符号分割成多行
    2. 逐行匹配字幕文件中的文本
    3. 生成新的字幕文件
    """

    text = _format_text(text)

    def formatter(idx: int, start_time: float, end_time: float, sub_text: str) -> str:
        """
        1
        00:00:00,000 --> 00:00:02,360
        跑步是一项简单易行的运动
        """
        start_t = mktimestamp(start_time).replace(".", ",")
        end_t = mktimestamp(end_time).replace(".", ",")
        return f"{idx}\n" f"{start_t} --> {end_t}\n" f"{sub_text}\n"

    start_time = -1.0
    sub_items = []
    sub_index = 0

    script_lines = utils.split_string_by_punctuations(text)

    def match_line(_sub_line: str, _sub_index: int):
        if len(script_lines) <= _sub_index:
            return ""

        _line = script_lines[_sub_index]
        if _sub_line == _line:
            return script_lines[_sub_index].strip()

        _sub_line_ = re.sub(r"[^\w\s]", "", _sub_line)
        _line_ = re.sub(r"[^\w\s]", "", _line)
        if _sub_line_ == _line_:
            return _line_.strip()

        _sub_line_ = re.sub(r"\W+", "", _sub_line)
        _line_ = re.sub(r"\W+", "", _line)
        if _sub_line_ == _line_:
            return _line.strip()

        return ""

    sub_line = ""

    try:
        for _, (offset, sub) in enumerate(zip(sub_maker.offset, sub_maker.subs)):
            _start_time, end_time = offset
            if start_time < 0:
                start_time = _start_time

            # 将 100纳秒单位转换为秒
            start_time_seconds = start_time / 10000000
            end_time_seconds = end_time / 10000000

            sub = unescape(sub)
            sub_line += sub
            sub_text = match_line(sub_line, sub_index)
            if sub_text:
                sub_index += 1
                line = formatter(
                    idx=sub_index,
                    start_time=start_time_seconds,
                    end_time=end_time_seconds,
                    sub_text=sub_text,
                )
                sub_items.append(line)
                start_time = -1.0
                sub_line = ""

        if len(sub_items) == len(script_lines):
            with open(subtitle_file, "w", encoding="utf-8") as file:
                file.write("\n".join(sub_items) + "\n")
            try:
                sbs = subtitles.file_to_subtitles(subtitle_file, encoding="utf-8")
                duration = max([tb for ((ta, tb), txt) in sbs])
                logger.info(
                    f"已创建字幕文件: {subtitle_file}, duration: {duration}"
                )
                return subtitle_file, duration
            except Exception as e:
                logger.error(f"failed, error: {str(e)}")
                os.remove(subtitle_file)
        else:
            logger.error(
                f"字幕创建失败, 字幕长度: {len(sub_items)}, script_lines len: {len(script_lines)}"
                f"\nsub_items:{json.dumps(sub_items, indent=4, ensure_ascii=False)}"
                f"\nscript_lines:{json.dumps(script_lines, indent=4, ensure_ascii=False)}"
            )
            # 返回默认值，避免 None 错误
            return subtitle_file, 3.0

    except Exception as e:
        logger.error(f"failed, error: {str(e)}")
        # 返回默认值，避免 None 错误
        return subtitle_file, 3.0


def get_audio_duration(sub_maker: submaker.SubMaker):
    """
    获取音频时长
    """
    if not sub_maker.offset:
        return 0.0
    return sub_maker.offset[-1][1] / 10000000


def tts_multiple(task_id: str, list_script: list, voice_name: str, voice_rate: float, voice_pitch: float, tts_engine: str = "azure"):
    """
    根据JSON文件中的多段文本进行TTS转换
    
    :param task_id: 任务ID
    :param list_script: 脚本列表
    :param voice_name: 语音名称
    :param voice_rate: 语音速率
    :param tts_engine: TTS 引擎
    :return: 生成的音频文件列表
    """
    voice_name = parse_voice_name(voice_name)
    output_dir = utils.task_dir(task_id)
    tts_results = []

    for item in list_script:
        if item['OST'] != 1:
            # 将时间戳中的冒号替换为下划线
            timestamp = item['timestamp'].replace(':', '_')
            audio_file = os.path.join(output_dir, f"audio_{timestamp}.mp3")
            subtitle_file = os.path.join(output_dir, f"subtitle_{timestamp}.srt")

            text = item['narration']

            sub_maker = tts(
                text=text,
                voice_name=voice_name,
                voice_rate=voice_rate,
                voice_pitch=voice_pitch,
                voice_file=audio_file,
                tts_engine=tts_engine,
            )

            if sub_maker is None:
                logger.error(f"无法为时间戳 {timestamp} 生成音频; "
                             f"如果您在中国，请使用VPN; "
                             f"或者使用其他 tts 引擎")
                continue
            else:
                # SoulVoice、Qwen3、IndexTTS2 引擎不生成字幕文件
                if is_soulvoice_voice(voice_name) or is_qwen_engine(tts_engine) or tts_engine == "indextts2":
                    # 获取实际音频文件的时长
                    duration = get_audio_duration_from_file(audio_file)
                    if duration <= 0:
                        # 如果无法获取文件时长，尝试从 SubMaker 获取
                        duration = get_audio_duration(sub_maker)
                        if duration <= 0:
                            # 最后的 fallback，基于文本长度估算
                            duration = max(1.0, len(text) / 3.0)
                            logger.warning(f"无法获取音频时长，使用文本估算: {duration:.2f}秒")
                    # 不创建字幕文件
                    subtitle_file = ""
                else:
                    _, duration = create_subtitle(sub_maker=sub_maker, text=text, subtitle_file=subtitle_file)

            tts_results.append({
                "_id": item['_id'],
                "timestamp": item['timestamp'],
                "audio_file": audio_file,
                "subtitle_file": subtitle_file,
                "duration": duration,
                "text": text,
            })
            logger.info(f"已生成音频文件: {audio_file}")

    return tts_results


def get_audio_duration_from_file(audio_file: str) -> float:
    """
    获取音频文件的时长（秒）
    """
    if MOVIEPY_AVAILABLE:
        try:
            audio_clip = AudioFileClip(audio_file)
            duration = audio_clip.duration
            audio_clip.close()
            return duration
        except Exception as e:
            logger.error(f"使用 moviepy 获取音频时长失败: {str(e)}")

    # Fallback: 使用更准确的估算方法
    try:
        import os
        file_size = os.path.getsize(audio_file)

        # 更准确的 MP3 时长估算
        # 假设 MP3 平均比特率为 128kbps = 16KB/s
        # 但实际文件还包含头部信息，所以调整系数
        estimated_duration = max(1.0, file_size / 20000)  # 调整为更保守的估算

        # 对于中文语音，根据文本长度进行二次校正
        # 一般中文语音速度约为 3-4 字/秒
        logger.warning(f"使用文件大小估算音频时长: {estimated_duration:.2f}秒")
        return estimated_duration
    except Exception as e:
        logger.error(f"获取音频时长失败: {str(e)}")
        # 如果所有方法都失败，返回一个基于文本长度的估算
        return 3.0  # 默认3秒，避免返回0

def parse_soulvoice_voice(voice_name: str) -> str:
    """
    解析 SoulVoice 语音名称
    支持格式：
    - soulvoice:speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr
    - speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr
    """
    if voice_name.startswith("soulvoice:"):
        return voice_name[10:]  # 移除 "soulvoice:" 前缀
    return voice_name

def parse_tencent_voice(voice_name: str) -> str:
    """
    解析腾讯云 TTS 语音名称
    支持格式：tencent:101001
    """
    if voice_name.startswith("tencent:"):
        return voice_name[8:]  # 移除 "tencent:" 前缀
    return voice_name


def parse_qwen3_voice(voice_name: str) -> str:
    """
    解析 Qwen3 语音名称
    """
    if isinstance(voice_name, str) and voice_name.startswith("qwen3:"):
        return voice_name[6:]
    return voice_name


def qwen3_tts(text: str, voice_name: str, voice_file: str, speed: float = 1.0) -> Union[SubMaker, None]:
    """
    使用通义千问 Qwen3 TTS 生成语音（仅使用 DashScope SDK）
    """
    # 读取配置
    tts_qwen_cfg = getattr(config, "tts_qwen", {}) or {}
    api_key = tts_qwen_cfg.get("api_key", "")
    model_name = tts_qwen_cfg.get("model_name", "qwen3-tts-flash")
    if not api_key:
        logger.error("Qwen3 TTS API key 未配置")
        return None

    # 准备参数
    voice_type = parse_qwen3_voice(voice_name)
    safe_speed = float(max(0.5, min(2.0, speed)))
    text = text.strip()



    # SDK 调用
    try:
        import dashscope
    except ImportError:
        logger.error("未安装 dashscope SDK，请执行: pip install dashscope")
        return None
    except Exception as e:
        logger.error(f"DashScope SDK 初始化失败: {e}")
        return None

    # Qwen3 TTS 直接使用英文参数，不需要映射
    mapped_voice = voice_type or "Cherry"

    for i in range(3):
        try:
            # 打印详细的请求参数日志
            logger.info(f"=== Qwen3 TTS 请求参数 (第 {i+1} 次调用) ===")

            # 官方推荐：使用 MultiModalConversation.call
            result = dashscope.MultiModalConversation.call(
                # 仅支持 qwen-tts 系列模型
                model=(model_name or "qwen3-tts-flash"),
                # 同时显式传入 api_key，并兼容示例中从环境变量读取
                api_key=api_key,
                text=text,
                voice=mapped_voice
            )
            logger.info(f"Qwen3 TTS API 响应: {result}")
        

            audio_bytes: bytes | None = None

            # 解析返回结果，提取音频URL并下载
            try:# 假设 result 是你收到的字符串
                audio_url = None
                
                if result.output and result.output.audio:
                    audio_url = result.output.audio.url
                # 从响应中提取音频URL
    
                if audio_url:
                    # 直接下载音频文件
                    response = requests.get(audio_url, timeout=30)
                    response.raise_for_status()
                    audio_bytes = response.content
                else:
                    logger.warning("API响应中未找到音频URL")
                    
            except Exception as e:
                logger.error(f"解析API响应失败: {str(e)}")

            if not audio_bytes:
                logger.warning("DashScope SDK 返回空音频数据，重试")
                if i < 2:
                    time.sleep(1)
                continue

            # 写入文件
            with open(voice_file, "wb") as f:
                f.write(audio_bytes)

            # 估算字幕
            sub = SubMaker()
            est_ms = max(800, int(len(text) * 180))
            sub.create_sub((0, est_ms), text)
            
            logger.info(f"Qwen3 TTS 生成成功（DashScope SDK），文件大小: {len(audio_bytes)} 字节")
            return sub

        except Exception as e:
            logger.error(f"DashScope SDK 合成失败: {e}")
            if i < 2:
                time.sleep(1)

    return None


def tencent_tts(text: str, voice_name: str, voice_file: str, speed: float = 1.0) -> Union[SubMaker, None]:
    """
    使用腾讯云 TTS 生成语音
    """
    try:
        # 导入腾讯云 SDK
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.tts.v20190823 import tts_client, models
        import base64
    except ImportError as e:
        logger.error(f"腾讯云 SDK 未安装: {e}")
        return None
    
    # 获取腾讯云配置
    tencent_config = config.tencent
    secret_id = tencent_config.get("secret_id")
    secret_key = tencent_config.get("secret_key")
    region = tencent_config.get("region", "ap-beijing")
    
    if not secret_id or not secret_key:
        logger.error("腾讯云 TTS 配置不完整，请检查 secret_id 和 secret_key")
        return None
    
    # 解析语音名称
    voice_type = parse_tencent_voice(voice_name)
    
    # 转换速度参数 (腾讯云支持 -2 到 2 的范围)
    speed_value = max(-2.0, min(2.0, (speed - 1.0) * 2))
    
    for i in range(3):
        try:
            logger.info(f"第 {i+1} 次使用腾讯云 TTS 生成音频")
            
            # 创建认证对象
            cred = credential.Credential(secret_id, secret_key)
            
            # 创建 HTTP 配置
            httpProfile = HttpProfile()
            httpProfile.endpoint = "tts.tencentcloudapi.com"
            
            # 创建客户端配置
            clientProfile = ClientProfile()
            clientProfile.httpProfile = httpProfile
            
            # 创建客户端
            client = tts_client.TtsClient(cred, region, clientProfile)
            
            req = models.TextToVoiceRequest()
            req.Text = text
            req.SessionId = str(uuid.uuid4())
            req.VoiceType = int(voice_type) if voice_type.isdigit() else 101001
            req.Speed = speed_value
            req.SampleRate = 16000
            req.Codec = "mp3"
            req.ProjectId = 0
            req.ModelType = 1
            req.PrimaryLanguage = 1
            req.EnableSubtitle = True

            # 发送请求
            resp = client.TextToVoice(req)
            
            # 检查响应
            if not resp.Audio:
                logger.warning(f"腾讯云 TTS 返回空音频数据")
                if i < 2:
                    time.sleep(1)
                continue
            
            # 解码音频数据
            audio_data = base64.b64decode(resp.Audio)
            
            # 写入文件
            with open(voice_file, "wb") as f:
                f.write(audio_data)

            # 创建字幕对象
            sub_maker = SubMaker()
            if resp.Subtitles:
                for sub in resp.Subtitles:
                    start_ms = sub.BeginTime
                    end_ms = sub.EndTime
                    text = sub.Text
                    # 转换为 100ns 单位
                    sub_maker.create_sub((start_ms * 10000, end_ms * 10000), text)
            else:
                # 如果没有字幕返回，则使用估算作为后备方案
                duration_ms = len(text) * 200
                sub_maker.create_sub((0, duration_ms * 10000), text)

            logger.info(f"腾讯云 TTS 生成成功，文件大小: {len(audio_data)} 字节")
            return sub_maker

        except Exception as e:
            logger.error(f"腾讯云 TTS 生成音频时出错: {str(e)}")
            if i < 2:
                 time.sleep(1)
     
    return None


def soulvoice_tts(text: str, voice_name: str, voice_file: str, speed: float = 1.0) -> Union[SubMaker, None]:
    """
    使用 SoulVoice API 进行文本转语音

    Args:
        text: 要转换的文本
        voice_name: 语音名称
        voice_file: 输出音频文件路径
        speed: 语音速度

    Returns:
        SubMaker: 包含时间戳信息的字幕制作器，失败时返回 None
    """
    # 获取配置
    api_key = config.soulvoice.get("api_key", "")
    api_url = config.soulvoice.get("api_url", "https://tts.scsmtech.cn/tts")
    default_model = config.soulvoice.get("model", "FunAudioLLM/CosyVoice2-0.5B")

    if not api_key:
        logger.error("SoulVoice API key 未配置")
        return None

    # 解析语音名称
    parsed_voice = parse_soulvoice_voice(voice_name)

    # 准备请求数据
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    data = {
        'text': text.strip(),
        'model': default_model,
        'voice': parsed_voice,
        'speed': speed
    }

    # 重试机制
    for attempt in range(3):
        try:
            logger.info(f"第 {attempt + 1} 次调用 SoulVoice API")

            # 设置代理
            proxies = {}
            if config.proxy.get("http"):
                proxies = {
                    'http': config.proxy.get("http"),
                    'https': config.proxy.get("https", config.proxy.get("http"))
                }

            # 调用 API
            response = requests.post(
                api_url,
                headers=headers,
                json=data,
                proxies=proxies,
                timeout=60
            )

            if response.status_code == 200:
                # 保存音频文件
                with open(voice_file, 'wb') as f:
                    f.write(response.content)

                logger.info(f"SoulVoice TTS 成功生成音频: {voice_file}")

                # SoulVoice 不支持精确字幕生成，返回简单的 SubMaker 对象
                sub_maker = SubMaker()
                sub_maker.subs = [text]  # 整个文本作为一个段落
                sub_maker.offset = [(0, 0)]  # 占位时间戳

                return sub_maker

            else:
                logger.error(f"SoulVoice API 调用失败: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            logger.error(f"SoulVoice API 调用超时 (尝试 {attempt + 1}/3)")
        except requests.exceptions.RequestException as e:
            logger.error(f"SoulVoice API 网络错误: {str(e)} (尝试 {attempt + 1}/3)")
        except Exception as e:
            logger.error(f"SoulVoice TTS 处理错误: {str(e)} (尝试 {attempt + 1}/3)")

        if attempt < 2:  # 不是最后一次尝试
            time.sleep(2)  # 等待2秒后重试

    logger.error("SoulVoice TTS 生成失败，已达到最大重试次数")
    return None


def is_soulvoice_voice(voice_name: str) -> bool:
    """
    检查是否为 SoulVoice 语音
    """
    return voice_name.startswith("soulvoice:") or voice_name.startswith("speech:")

def is_qwen_engine(tts_engine: str) -> bool:
    return tts_engine == "qwen3_tts"

def parse_soulvoice_voice(voice_name: str) -> str:
    """
    解析 SoulVoice 语音名称
    支持格式：
    - soulvoice:speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr
    - speech:mcg3fdnx:clzkyf4vy00e5qr6hywum4u84:bzznlkuhcjzpbosexitr
    """
    if voice_name.startswith("soulvoice:"):
        return voice_name[10:]  # 移除 "soulvoice:" 前缀
    return voice_name


def parse_indextts2_voice(voice_name: str) -> str:
    """
    解析 IndexTTS2 语音名称
    支持格式：indextts2:reference_audio_path
    返回参考音频文件路径
    """
    if voice_name.startswith("indextts2:"):
        return voice_name[10:]  # 移除 "indextts2:" 前缀
    return voice_name


def indextts2_tts(text: str, voice_name: str, voice_file: str, speed: float = 1.0) -> Union[SubMaker, None]:
    """
    使用 IndexTTS2 API 进行零样本语音克隆

    Args:
        text: 要转换的文本
        voice_name: 参考音频路径（格式：indextts2:path/to/audio.wav）
        voice_file: 输出音频文件路径
        speed: 语音速度（此引擎暂不支持速度调节）

    Returns:
        SubMaker: 包含时间戳信息的字幕制作器，失败时返回 None
    """
    # 获取配置
    api_url = config.indextts2.get("api_url", "http://192.168.3.6:8081/tts")
    infer_mode = config.indextts2.get("infer_mode", "普通推理")
    temperature = config.indextts2.get("temperature", 1.0)
    top_p = config.indextts2.get("top_p", 0.8)
    top_k = config.indextts2.get("top_k", 30)
    do_sample = config.indextts2.get("do_sample", True)
    num_beams = config.indextts2.get("num_beams", 3)
    repetition_penalty = config.indextts2.get("repetition_penalty", 10.0)

    # 解析参考音频路径
    reference_audio_path = parse_indextts2_voice(voice_name)
    
    if not reference_audio_path or not os.path.exists(reference_audio_path):
        logger.error(f"IndexTTS2 参考音频文件不存在: {reference_audio_path}")
        return None

    # 准备请求数据
    files = {
        'prompt_audio': open(reference_audio_path, 'rb')
    }
    
    data = {
        'text': text.strip(),
        'infer_mode': infer_mode,
        'temperature': temperature,
        'top_p': top_p,
        'top_k': top_k,
        'do_sample': do_sample,
        'num_beams': num_beams,
        'repetition_penalty': repetition_penalty,
    }

    # 重试机制
    for attempt in range(3):
        try:
            logger.info(f"第 {attempt + 1} 次调用 IndexTTS2 API")

            # 设置代理
            proxies = {}
            if config.proxy.get("http"):
                proxies = {
                    'http': config.proxy.get("http"),
                    'https': config.proxy.get("https", config.proxy.get("http"))
                }

            # 调用 API
            response = requests.post(
                api_url,
                files=files,
                data=data,
                proxies=proxies,
                timeout=120  # IndexTTS2 推理可能需要较长时间
            )

            if response.status_code == 200:
                # 保存音频文件
                with open(voice_file, 'wb') as f:
                    f.write(response.content)

                logger.info(f"IndexTTS2 成功生成音频: {voice_file}, 大小: {len(response.content)} 字节")

                # IndexTTS2 不支持精确字幕生成，返回简单的 SubMaker 对象
                sub_maker = SubMaker()
                # 估算音频时长（基于文本长度）
                estimated_duration_ms = max(1000, int(len(text) * 200))
                sub_maker.create_sub((0, estimated_duration_ms * 10000), text)

                return sub_maker

            else:
                logger.error(f"IndexTTS2 API 调用失败: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            logger.error(f"IndexTTS2 API 调用超时 (尝试 {attempt + 1}/3)")
        except requests.exceptions.RequestException as e:
            logger.error(f"IndexTTS2 API 网络错误: {str(e)} (尝试 {attempt + 1}/3)")
        except Exception as e:
            logger.error(f"IndexTTS2 TTS 处理错误: {str(e)} (尝试 {attempt + 1}/3)")
        finally:
            # 确保关闭文件
            try:
                files['prompt_audio'].close()
            except:
                pass

        if attempt < 2:  # 不是最后一次尝试
            time.sleep(2)  # 等待2秒后重试
            # 重新打开文件用于下次重试
            if attempt < 2:
                try:
                    files['prompt_audio'] = open(reference_audio_path, 'rb')
                except:
                    pass

    logger.error("IndexTTS2 TTS 生成失败，已达到最大重试次数")
    return None



