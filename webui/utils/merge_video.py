"""
合并视频和字幕文件
"""
from moviepy.editor import VideoFileClip, concatenate_videoclips
import pysrt
import os


def get_video_duration(video_path):
    """获取视频时长（秒）"""
    video = VideoFileClip(video_path)
    duration = video.duration
    video.close()
    return duration


def adjust_subtitle_timing(subtitle_path, time_offset):
    """调整字幕时间戳"""
    subs = pysrt.open(subtitle_path)

    # 为每个字幕项添加时间偏移
    for sub in subs:
        sub.start.hours += int(time_offset / 3600)
        sub.start.minutes += int((time_offset % 3600) / 60)
        sub.start.seconds += int(time_offset % 60)
        sub.start.milliseconds += int((time_offset * 1000) % 1000)

        sub.end.hours += int(time_offset / 3600)
        sub.end.minutes += int((time_offset % 3600) / 60)
        sub.end.seconds += int(time_offset % 60)
        sub.end.milliseconds += int((time_offset * 1000) % 1000)

    return subs


def merge_videos_and_subtitles(video_paths, subtitle_paths, output_video_path, output_subtitle_path):
    """合并视频和字幕文件"""
    if len(video_paths) != len(subtitle_paths):
        raise ValueError("视频文件数量与字幕文件数量不匹配")

    # 1. 合并视频
    video_clips = []
    accumulated_duration = 0
    merged_subs = pysrt.SubRipFile()

    try:
        # 处理所有视频和字幕
        for i, (video_path, subtitle_path) in enumerate(zip(video_paths, subtitle_paths)):
            # 添加视频
            print(f"处理视频 {i + 1}/{len(video_paths)}: {video_path}")
            video_clip = VideoFileClip(video_path)
            video_clips.append(video_clip)

            # 处理字幕
            print(f"处理字幕 {i + 1}/{len(subtitle_paths)}: {subtitle_path}")
            if i == 0:
                # 第一个字幕文件直接读取
                current_subs = pysrt.open(subtitle_path)
            else:
                # 后续字幕文件需要调整时间戳
                current_subs = adjust_subtitle_timing(subtitle_path, accumulated_duration)

            # 合并字幕
            merged_subs.extend(current_subs)

            # 更新累计时长
            accumulated_duration += video_clip.duration

        # 判断视频是否存在，若已经存在不重复合并
        if not os.path.exists(output_video_path):
            print("合并视频中...")
            final_video = concatenate_videoclips(video_clips)

            # 保存合并后的视频
            print("保存合并后的视频...")
            final_video.write_videofile(output_video_path, audio_codec='aac')

        # 保存合并后的字幕
        print("保存合并后的字幕...")
        merged_subs.save(output_subtitle_path, encoding='utf-8')

        print("合并完成")

    finally:
        # 清理资源
        for clip in video_clips:
            clip.close()


def main():
    # 示例用法
    video_paths = [
        "temp/1.mp4",
        "temp/2.mp4",
        "temp/3.mp4",
        "temp/4.mp4",
        "temp/5.mp4",
    ]

    subtitle_paths = [
        "temp/1.srt",
        "temp/2.srt",
        "temp/3.srt",
        "temp/4.srt",
        "temp/5.srt",
    ]

    output_video_path = "temp/merged_video.mp4"
    output_subtitle_path = "temp/merged_subtitle.srt"

    merge_videos_and_subtitles(video_paths, subtitle_paths, output_video_path, output_subtitle_path)


if __name__ == "__main__":
    main()
