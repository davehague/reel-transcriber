import whisper
import yt_dlp
import subprocess
import os
from typing import Dict, Optional


class InstagramTranscriber:
    def __init__(self):
        self.model = whisper.load_model("base")

    def get_video_info(self, url: str) -> Dict:
        with yt_dlp.YoutubeDL() as ydl:
            return ydl.extract_info(url, download=False)

    def transcribe(self, url: str, temp_dir: Optional[str] = None) -> Dict:
        """
        Transcribe an Instagram video and return metadata
        """
        info = self.get_video_info(url)

        # Use system temp dir if none provided
        temp_dir = temp_dir or os.path.dirname(os.path.realpath(__file__))
        temp_file = os.path.join(temp_dir, 'temp_video.mp4')

        try:
            # Download video
            subprocess.run(['yt-dlp', url, '-o', temp_file])

            # Transcribe
            result = self.model.transcribe(temp_file)

            return {
                'transcript': f"{result['text']}\n\nSource: {url}",
                'title': info['description'],
                'author': f"{info['uploader']} ({info['channel']})",
                'source_url': url
            }

        finally:
            # Cleanup
            if os.path.exists(temp_file):
                os.remove(temp_file)
