import json
from loguru import logger
import os
from datetime import datetime, timedelta
import re


def time_to_seconds(time_str):
    time_obj = datetime.strptime(time_str, "%M:%S")
    return timedelta(minutes=time_obj.minute, seconds=time_obj.second).total_seconds()


def seconds_to_time_str(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"


def check_script(file_path, total_duration):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    errors = []
    ost_narrations = set()
    last_end_time = 0

    logger.info(f"开始检查文件: {file_path}")
    logger.info(f"视频总时长: {total_duration:.2f} 秒")
    logger.info("=" * 50)

    for i, item in enumerate(data, 1):
        logger.info(f"\n检查第 {i} 项:")

        # 检查所有必需字段是否存在
        required_fields = ['picture', 'timestamp', 'narration', 'OST', 'new_timestamp']
        for field in required_fields:
            if field not in item:
                errors.append(f"第 {i} 项缺少 {field} 字段")
                logger.info(f"  - 错误: 缺少 {field} 字段")
            else:
                logger.info(f"  - {field}: {item[field]}")

        # 检查 OST 为 false 的情况
        if item.get('OST') == False:
            if not item.get('narration'):
                errors.append(f"第 {i} 项 OST 为 false，但 narration 为空")
                logger.info("  - 错误: OST 为 false，但 narration 为空")
            elif len(item['narration']) > 30:
                errors.append(f"第 {i} 项 OST 为 false，但 narration 超过 30 字")
                logger.info(f"  - 错误: OST 为 false，但 narration 超过 30 字 (当前: {len(item['narration'])} 字)")
            else:
                logger.info("  - OST 为 false，narration 检查通过")

        # 检查 OST 为 true 的情况
        if item.get('OST') == True:
            if not item.get('narration').startswith('原声播放_'):
                errors.append(f"第 {i} 项 OST 为 true，但 narration 不是 '原声播放_xxx' 格式")
                logger.info("  - 错误: OST 为 true，但 narration 不是 '原声播放_xxx' 格式")
            elif item['narration'] in ost_narrations:
                errors.append(f"第 {i} 项 OST 为 true，但 narration '{item['narration']}' 不是唯一值")
                logger.info(f"  - 错误: OST 为 true，但 narration '{item['narration']}' 不是唯一值")
            else:
                logger.info("  - OST 为 true，narration 检查通过")
                ost_narrations.add(item['narration'])

        # 检查 timestamp 是否重叠
        if 'timestamp' in item:
            start, end = map(time_to_seconds, item['timestamp'].split('-'))
            if start < last_end_time:
                errors.append(f"第 {i} 项 timestamp '{item['timestamp']}' 与前一项重叠")
                logger.info(f"  - 错误: timestamp '{item['timestamp']}' 与前一项重叠")
            else:
                logger.info(f"  - timestamp '{item['timestamp']}' 检查通过")
            last_end_time = end

            # 检查 timestamp 是否超过总时长
            if end > total_duration:
                errors.append(f"第 {i} 项 timestamp '{item['timestamp']}' 超过总时长 {total_duration:.2f} 秒")
                logger.info(f"  - 错误: timestamp '{item['timestamp']}' 超过总时长 {total_duration:.2f} 秒")
            else:
                logger.info(f"  - timestamp 在总时长范围内")

    # 检查 new_timestamp 是否连续
    logger.info("\n检查 new_timestamp 连续性:")
    last_end_time = 0
    for i, item in enumerate(data, 1):
        if 'new_timestamp' in item:
            start, end = map(time_to_seconds, item['new_timestamp'].split('-'))
            if start != last_end_time:
                errors.append(f"第 {i} 项 new_timestamp '{item['new_timestamp']}' 与前一项不连续")
                logger.info(f"  - 错误: 第 {i} 项 new_timestamp '{item['new_timestamp']}' 与前一项不连续")
            else:
                logger.info(f"  - 第 {i} 项 new_timestamp '{item['new_timestamp']}' 连续性检查通过")
            last_end_time = end

    if errors:
        logger.info("检查结果：不通过")
        logger.info("发现以下错误：")
        for error in errors:
            logger.info(f"- {error}")
        fix_script(file_path, data, errors)
    else:
        logger.info("检查结果：通过")
        logger.info("所有项目均符合规则要求。")


def fix_script(file_path, data, errors):
    logger.info("\n开始修复脚本...")
    fixed_data = []
    for i, item in enumerate(data, 1):
        if item['OST'] == False and (not item['narration'] or len(item['narration']) > 30):
            if not item['narration']:
                logger.info(f"第 {i} 项 narration 为空，需要人工参与修复。")
                fixed_data.append(item)
            else:
                logger.info(f"修复第 {i} 项 narration 超过 30 字的问题...")
                fixed_items = split_narration(item)
                fixed_data.extend(fixed_items)
        else:
            fixed_data.append(item)

    for error in errors:
        if not error.startswith("第") or "OST 为 false" not in error:
            logger.info(f"需要人工参与修复: {error}")

    # 生成新的文件名
    file_name, file_ext = os.path.splitext(file_path)
    new_file_path = f"{file_name}_revise{file_ext}"

    # 保存修复后的数据到新文件
    with open(new_file_path, 'w', encoding='utf-8') as f:
        json.dump(fixed_data, f, ensure_ascii=False, indent=4)

    logger.info(f"\n脚本修复完成，已保存到新文件: {new_file_path}")


def split_narration(item):
    narration = item['narration']
    chunks = smart_split(narration)

    start_time, end_time = map(time_to_seconds, item['timestamp'].split('-'))
    new_start_time, new_end_time = map(time_to_seconds, item['new_timestamp'].split('-'))

    total_duration = end_time - start_time
    new_total_duration = new_end_time - new_start_time
    chunk_duration = total_duration / len(chunks)
    new_chunk_duration = new_total_duration / len(chunks)

    fixed_items = []
    for i, chunk in enumerate(chunks):
        new_item = item.copy()
        new_item['narration'] = chunk

        chunk_start = start_time + i * chunk_duration
        chunk_end = chunk_start + chunk_duration
        new_item['timestamp'] = f"{seconds_to_time_str(chunk_start)}-{seconds_to_time_str(chunk_end)}"

        new_chunk_start = new_start_time + i * new_chunk_duration
        new_chunk_end = new_chunk_start + new_chunk_duration
        new_item['new_timestamp'] = f"{seconds_to_time_str(new_chunk_start)}-{seconds_to_time_str(new_chunk_end)}"

        fixed_items.append(new_item)

    return fixed_items


def smart_split(text, target_length=30):
    # 使用正则表达式分割文本，保留标点符号
    segments = re.findall(r'[^，。！？,!?]+[，。！？,!?]?', text)
    result = []
    current_chunk = ""

    for segment in segments:
        if len(current_chunk) + len(segment) <= target_length:
            current_chunk += segment
        else:
            if current_chunk:
                result.append(current_chunk.strip())
            current_chunk = segment

    if current_chunk:
        result.append(current_chunk.strip())

    # 如果有任何chunk超过了目标长度，进行进一步的分割
    final_result = []
    for chunk in result:
        if len(chunk) > target_length:
            sub_chunks = [chunk[i:i + target_length] for i in range(0, len(chunk), target_length)]
            final_result.extend(sub_chunks)
        else:
            final_result.append(chunk)

    return final_result


if __name__ == "__main__":
    file_path = "/Users/apple/Desktop/home/NarratoAI/resource/scripts/2024-0923-085036.json"
    total_duration = 280
    check_script(file_path, total_duration)
