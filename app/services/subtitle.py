import json
import os.path
import re
import traceback
from typing import Optional

from faster_whisper import WhisperModel
from timeit import default_timer as timer
from loguru import logger
import google.generativeai as genai

from app.config import config
from app.utils import utils

model_size = config.whisper.get("model_size", "faster-whisper-large-v2")
device = config.whisper.get("device", "cpu")
compute_type = config.whisper.get("compute_type", "int8")
model = None


def create(audio_file, subtitle_file: str = ""):
    """
    为给定的音频文件创建字幕文件。

    参数:
    - audio_file: 音频文件的路径。
    - subtitle_file: 字幕文件的输出路径（可选）。如果未提供，将根据音频文件的路径生成字幕文件。

    返回:
    无返回值，但会在指定路径生成字幕文件。
    """
    global model
    if not model:
        model_path = f"{utils.root_dir()}/app/models/faster-whisper-large-v2"
        model_bin_file = f"{model_path}/model.bin"
        if not os.path.isdir(model_path) or not os.path.isfile(model_bin_file):
            logger.error(
                "请先下载 whisper 模型\n\n"
                "********************************************\n"
                "下载地址：https://huggingface.co/guillaumekln/faster-whisper-large-v2\n"
                "存放路径：app/models \n"
                "********************************************\n"
            )
            return None

        logger.info(
            f"加载模型: {model_path}, 设备: {device}, 计算类型: {compute_type}"
        )
        try:
            model = WhisperModel(
                model_size_or_path=model_path, device=device, compute_type=compute_type, local_files_only=True
            )
        except Exception as e:
            logger.error(
                f"加载模型失败: {e} \n\n"
                f"********************************************\n"
                f"这可能是由网络问题引起的. \n"
                f"请手动下载模型并将其放入 'app/models' 文件夹中。 \n"
                f"see [README.md FAQ](https://github.com/linyqh/NarratoAI) for more details.\n"
                f"********************************************\n\n"
                f"{traceback.format_exc()}"
            )
            return None

    logger.info(f"start, output file: {subtitle_file}")
    if not subtitle_file:
        subtitle_file = f"{audio_file}.srt"

    segments, info = model.transcribe(
        audio_file,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    logger.info(
        f"检测到的语言: '{info.language}', probability: {info.language_probability:.2f}"
    )

    start = timer()
    subtitles = []

    def recognized(seg_text, seg_start, seg_end):
        seg_text = seg_text.strip()
        if not seg_text:
            return

        msg = "[%.2fs -> %.2fs] %s" % (seg_start, seg_end, seg_text)
        logger.debug(msg)

        subtitles.append(
            {"msg": seg_text, "start_time": seg_start, "end_time": seg_end}
        )

    for segment in segments:
        words_idx = 0
        words_len = len(segment.words)

        seg_start = 0
        seg_end = 0
        seg_text = ""

        if segment.words:
            is_segmented = False
            for word in segment.words:
                if not is_segmented:
                    seg_start = word.start
                    is_segmented = True

                seg_end = word.end
                # 如果包含标点,则断句
                seg_text += word.word

                if utils.str_contains_punctuation(word.word):
                    # remove last char
                    seg_text = seg_text[:-1]
                    if not seg_text:
                        continue

                    recognized(seg_text, seg_start, seg_end)

                    is_segmented = False
                    seg_text = ""

                if words_idx == 0 and segment.start < word.start:
                    seg_start = word.start
                if words_idx == (words_len - 1) and segment.end > word.end:
                    seg_end = word.end
                words_idx += 1

        if not seg_text:
            continue

        recognized(seg_text, seg_start, seg_end)

    end = timer()

    diff = end - start
    logger.info(f"complete, elapsed: {diff:.2f} s")

    idx = 1
    lines = []
    for subtitle in subtitles:
        text = subtitle.get("msg")
        if text:
            lines.append(
                utils.text_to_srt(
                    idx, text, subtitle.get("start_time"), subtitle.get("end_time")
                )
            )
            idx += 1

    sub = "\n".join(lines) + "\n"
    with open(subtitle_file, "w", encoding="utf-8") as f:
        f.write(sub)
    logger.info(f"subtitle file created: {subtitle_file}")


def file_to_subtitles(filename):
    """
    将字幕文件转换为字幕列表。

    参数:
    filename (str): 字幕文件的路径。

    返回:
    list: 包含字幕序号、出现时间、和字幕文本的元组列表。
    """
    if not filename or not os.path.isfile(filename):
        return []

    times_texts = []
    current_times = None
    current_text = ""
    index = 0
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            times = re.findall("([0-9]*:[0-9]*:[0-9]*,[0-9]*)", line)
            if times:
                current_times = line
            elif line.strip() == "" and current_times:
                index += 1
                times_texts.append((index, current_times.strip(), current_text.strip()))
                current_times, current_text = None, ""
            elif current_times:
                current_text += line
    return times_texts


def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def similarity(a, b):
    distance = levenshtein_distance(a.lower(), b.lower())
    max_length = max(len(a), len(b))
    return 1 - (distance / max_length)


def correct(subtitle_file, video_script):
    subtitle_items = file_to_subtitles(subtitle_file)
    script_lines = utils.split_string_by_punctuations(video_script)

    corrected = False
    new_subtitle_items = []
    script_index = 0
    subtitle_index = 0

    while script_index < len(script_lines) and subtitle_index < len(subtitle_items):
        script_line = script_lines[script_index].strip()
        subtitle_line = subtitle_items[subtitle_index][2].strip()

        if script_line == subtitle_line:
            new_subtitle_items.append(subtitle_items[subtitle_index])
            script_index += 1
            subtitle_index += 1
        else:
            combined_subtitle = subtitle_line
            start_time = subtitle_items[subtitle_index][1].split(" --> ")[0]
            end_time = subtitle_items[subtitle_index][1].split(" --> ")[1]
            next_subtitle_index = subtitle_index + 1

            while next_subtitle_index < len(subtitle_items):
                next_subtitle = subtitle_items[next_subtitle_index][2].strip()
                if similarity(
                    script_line, combined_subtitle + " " + next_subtitle
                ) > similarity(script_line, combined_subtitle):
                    combined_subtitle += " " + next_subtitle
                    end_time = subtitle_items[next_subtitle_index][1].split(" --> ")[1]
                    next_subtitle_index += 1
                else:
                    break

            if similarity(script_line, combined_subtitle) > 0.8:
                logger.warning(
                    f"Merged/Corrected - Script: {script_line}, Subtitle: {combined_subtitle}"
                )
                new_subtitle_items.append(
                    (
                        len(new_subtitle_items) + 1,
                        f"{start_time} --> {end_time}",
                        script_line,
                    )
                )
                corrected = True
            else:
                logger.warning(
                    f"Mismatch - Script: {script_line}, Subtitle: {combined_subtitle}"
                )
                new_subtitle_items.append(
                    (
                        len(new_subtitle_items) + 1,
                        f"{start_time} --> {end_time}",
                        script_line,
                    )
                )
                corrected = True

            script_index += 1
            subtitle_index = next_subtitle_index

    # 处理剩余的脚本行
    while script_index < len(script_lines):
        logger.warning(f"Extra script line: {script_lines[script_index]}")
        if subtitle_index < len(subtitle_items):
            new_subtitle_items.append(
                (
                    len(new_subtitle_items) + 1,
                    subtitle_items[subtitle_index][1],
                    script_lines[script_index],
                )
            )
            subtitle_index += 1
        else:
            new_subtitle_items.append(
                (
                    len(new_subtitle_items) + 1,
                    "00:00:00,000 --> 00:00:00,000",
                    script_lines[script_index],
                )
            )
        script_index += 1
        corrected = True

    if corrected:
        with open(subtitle_file, "w", encoding="utf-8") as fd:
            for i, item in enumerate(new_subtitle_items):
                fd.write(f"{i + 1}\n{item[1]}\n{item[2]}\n\n")
        logger.info("Subtitle corrected")
    else:
        logger.success("Subtitle is correct")


def create_with_gemini(audio_file: str, subtitle_file: str = "", api_key: Optional[str] = None) -> Optional[str]:
    if not api_key:
        logger.error("Gemini API key is not provided")
        return None

    genai.configure(api_key=api_key)

    logger.info(f"开始使用Gemini模型处理音频文件: {audio_file}")
    
    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
    prompt = "生成这段语音的转录文本。请以SRT格式输出，包含时间戳。"

    try:
        with open(audio_file, "rb") as f:
            audio_data = f.read()
        
        response = model.generate_content([prompt, audio_data])
        transcript = response.text

        if not subtitle_file:
            subtitle_file = f"{audio_file}.srt"

        with open(subtitle_file, "w", encoding="utf-8") as f:
            f.write(transcript)

        logger.info(f"Gemini生成的字幕文件已保存: {subtitle_file}")
        return subtitle_file
    except Exception as e:
        logger.error(f"使用Gemini处理音频时出错: {e}")
        return None


if __name__ == "__main__":
    task_id = "test456"
    task_dir = utils.task_dir(task_id)
    subtitle_file = f"{task_dir}/subtitle.srt"
    audio_file = f"{task_dir}/audio.wav"

    subtitles = file_to_subtitles(subtitle_file)
    print(subtitles)

    # script_file = f"{task_dir}/script.json"
    # with open(script_file, "r") as f:
    #     script_content = f.read()
    # s = json.loads(script_content)
    # script = s.get("script")
    #
    # correct(subtitle_file, script)

    subtitle_file = f"{task_dir}/subtitle111.srt"
    create(audio_file, subtitle_file)

    # # 使用Gemini模型处理音频
    # gemini_api_key = config.app.get("gemini_api_key")  # 请替换为实际的API密钥
    # gemini_subtitle_file = create_with_gemini(audio_file, api_key=gemini_api_key)
    #
    # if gemini_subtitle_file:
    #     print(f"Gemini生成的字幕文件: {gemini_subtitle_file}")
