"""
使用 moviepy 合并视频、音频、字幕和背景音乐
"""

from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    TextClip,
    CompositeVideoClip,
    concatenate_videoclips
)
# from moviepy.config import change_settings
import os

# 设置字体文件路径（用于中文字幕显示）
FONT_PATH = "../../resource/fonts/STHeitiMedium.ttc"  # 请确保此路径下有对应字体文件
# change_settings(
#     {"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16\magick.exe"})  # Windows系统需要设置 ImageMagick 路径


class VideoMerger:
    """视频合并处理类"""

    def __init__(self, output_path: str = "../../resource/videos/merged_video.mp4"):
        """
        初始化视频合并器
        参数:
            output_path: 输出文件路径
        """
        self.output_path = output_path
        self.video_clips = []
        self.background_music = None
        self.subtitles = []

    def add_video(self, video_path: str, start_time: str = None, end_time: str = None) -> None:
        """
        添加视频片段
        参数:
            video_path: 视频文件路径
            start_time: 开始时间 (格式: "MM:SS")
            end_time: 结束时间 (格式: "MM:SS")
        """
        video = VideoFileClip(video_path)
        if start_time and end_time:
            video = video.subclip(self._time_to_seconds(start_time),
                                  self._time_to_seconds(end_time))
        self.video_clips.append(video)

    def add_audio(self, audio_path: str, volume: float = 1.0) -> None:
        """
        添加背景音乐
        参数:
            audio_path: 音频文件路径
            volume: 音量大小 (0.0-1.0)
        """
        self.background_music = AudioFileClip(audio_path).volumex(volume)

    def add_subtitle(self, text: str, start_time: str, end_time: str,
                     position: tuple = ('center', 'bottom'), fontsize: int = 24) -> None:
        """
        添加字幕
        参数:
            text: 字幕文本
            start_time: 开始时间 (格式: "MM:SS")
            end_time: 结束时间 (格式: "MM:SS")
            position: 字幕位置
            fontsize: 字体大小
        """
        subtitle = TextClip(
            text,
            font=FONT_PATH,
            fontsize=fontsize,
            color='white',
            stroke_color='black',
            stroke_width=2
        )

        subtitle = subtitle.set_position(position).set_duration(
            self._time_to_seconds(end_time) - self._time_to_seconds(start_time)
        ).set_start(self._time_to_seconds(start_time))

        self.subtitles.append(subtitle)

    def merge(self) -> None:
        """合并所有媒体元素并导出视频"""
        if not self.video_clips:
            raise ValueError("至少需要添加一个视频片段")

        # 合并视频片段
        final_video = concatenate_videoclips(self.video_clips)

        # 如果有背景音乐，设置其持续时间与视频相同
        if self.background_music:
            self.background_music = self.background_music.set_duration(final_video.duration)
            final_video = final_video.set_audio(self.background_music)

        # 添加字幕
        if self.subtitles:
            final_video = CompositeVideoClip([final_video] + self.subtitles)

        # 导出最终视频
        final_video.write_videofile(
            self.output_path,
            fps=24,
            codec='libx264',
            audio_codec='aac'
        )

        # 释放资源
        final_video.close()
        for clip in self.video_clips:
            clip.close()
        if self.background_music:
            self.background_music.close()

    @staticmethod
    def _time_to_seconds(time_str: str) -> float:
        """将时间字符串转换为秒数"""
        minutes, seconds = map(int, time_str.split(':'))
        return minutes * 60 + seconds


def test_merge_video():
    """测试视频合并功能"""
    merger = VideoMerger()

    # 添加两个视频片段
    merger.add_video("../../resource/videos/cut_video.mp4", "00:00", "01:00")
    merger.add_video("../../resource/videos/demo.mp4", "00:00", "00:30")

    # 添加背景音乐
    merger.add_audio("../../resource/songs/output000.mp3", volume=0.3)

    # 添加字幕
    merger.add_subtitle("第一个精彩片段", "00:00", "00:05")
    merger.add_subtitle("第二个精彩片段", "01:00", "01:05")

    # 合并并导出
    merger.merge()


if __name__ == "__main__":
    test_merge_video()
