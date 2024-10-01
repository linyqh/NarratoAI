import json
from loguru import logger
import os
from datetime import timedelta

def time_to_seconds(time_str):
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 2:
        return timedelta(minutes=parts[0], seconds=parts[1]).total_seconds()
    elif len(parts) == 3:
        return timedelta(hours=parts[0], minutes=parts[1], seconds=parts[2]).total_seconds()
    raise ValueError(f"无法解析时间字符串: {time_str}")

def seconds_to_time_str(seconds):
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

def adjust_timestamp(start_time, duration):
    start_seconds = time_to_seconds(start_time)
    end_seconds = start_seconds + duration
    return f"{start_time}-{seconds_to_time_str(end_seconds)}"

def estimate_audio_duration(text):
    # 假设平均每个字符需要 0.2 秒
    return len(text) * 0.2

def check_script(data, total_duration):
    errors = []
    time_ranges = []

    logger.info("开始检查脚本")
    logger.info(f"视频总时长: {total_duration:.2f} 秒")
    logger.info("=" * 50)

    for i, item in enumerate(data, 1):
        logger.info(f"\n检查第 {i} 项:")

        # 检查所有必需字段
        required_fields = ['picture', 'timestamp', 'narration', 'OST']
        for field in required_fields:
            if field not in item:
                errors.append(f"第 {i} 项缺少 {field} 字段")
                logger.info(f"  - 错误: 缺少 {field} 字段")
            else:
                logger.info(f"  - {field}: {item[field]}")

        # 检查 OST 相关规则
        if item.get('OST') == False:
            if not item.get('narration'):
                errors.append(f"第 {i} 项 OST 为 false，但 narration 为空")
                logger.info("  - 错误: OST 为 false，但 narration 为空")
            elif len(item['narration']) > 60:
                errors.append(f"第 {i} 项 OST 为 false，但 narration 超过 60 字")
                logger.info(f"  - 错误: OST 为 false，但 narration 超过 60 字 (当前: {len(item['narration'])} 字)")
            else:
                logger.info("  - OST 为 false，narration 检查通过")
        elif item.get('OST') == True:
            if "原声播放_" not in item.get('narration'):
                errors.append(f"第 {i} 项 OST 为 true，但 narration 不为空")
                logger.info("  - 错误: OST 为 true，但 narration 不为空")
            else:
                logger.info("  - OST 为 true，narration 检查通过")

        # 检查 timestamp
        if 'timestamp' in item:
            start, end = map(time_to_seconds, item['timestamp'].split('-'))
            if any((start < existing_end and end > existing_start) for existing_start, existing_end in time_ranges):
                errors.append(f"第 {i} 项 timestamp '{item['timestamp']}' 与其他时间段重叠")
                logger.info(f"  - 错误: timestamp '{item['timestamp']}' 与其他时间段重叠")
            else:
                logger.info(f"  - timestamp '{item['timestamp']}' 检查通过")
                time_ranges.append((start, end))

            # if end > total_duration:
            #     errors.append(f"第 {i} 项 timestamp '{item['timestamp']}' 超过总时长 {total_duration:.2f} 秒")
            #     logger.info(f"  - 错误: timestamp '{item['timestamp']}' 超过总时长 {total_duration:.2f} 秒")
            # else:
            #     logger.info(f"  - timestamp 在总时长范围内")

        # 处理 narration 字段
        if item.get('OST') == False and item.get('narration'):
            estimated_duration = estimate_audio_duration(item['narration'])
            start_time = item['timestamp'].split('-')[0]
            item['timestamp'] = adjust_timestamp(start_time, estimated_duration)
            logger.info(f"  - 已调整 timestamp 为 {item['timestamp']} (估算音频时长: {estimated_duration:.2f} 秒)")

    if errors:
        logger.info("检查结果：不通过")
        logger.info("发现以下错误：")
        for error in errors:
            logger.info(f"- {error}")
    else:
        logger.info("检查结果：通过")
        logger.info("所有项目均符合规则要求。")

    return errors, data


if __name__ == "__main__":
    file_path = "/Users/apple/Desktop/home/NarratoAI/resource/scripts/test004.json"

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_duration = 280

    # check_script(data, total_duration)

    from app.utils.utils import add_new_timestamps
    res = add_new_timestamps(data)
    print(json.dumps(res, indent=4, ensure_ascii=False))
