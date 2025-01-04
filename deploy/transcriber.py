import whisper
import yt_dlp
import os
from typing import Dict, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load the Whisper model globally
MODEL = whisper.load_model("base")

class InstagramTranscriber:
    def __init__(self):
        self.model = MODEL

    def get_video_info(self, url: str) -> Dict:
        """
        Get video information without downloading the video.
        """
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info

    def download_video(self, url: str, output_path: str) -> None:
        """
        Download the video from Instagram using yt_dlp.
        """
        ydl_opts = {
            'outtmpl': output_path,
            'format': 'mp4',
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    def transcribe(self, url: str, temp_dir: Optional[str] = None) -> Dict:
        """
        Transcribe an Instagram video and return metadata.
        """
        # Get video info
        info = self.get_video_info(url)
        logger.info(f"Video info: {info}")

        # Use /tmp directory for temporary files
        temp_dir = temp_dir or '/tmp'
        temp_file = os.path.join(temp_dir, 'temp_video.mp4')

        try:
            # Download video
            self.download_video(url, temp_file)

            # Transcribe
            try:
                result = self.model.transcribe(temp_file)
                if isinstance(result['text'], bytes):
                    result['text'] = result['text'].decode('utf-8')
            except Exception as e:
                logger.error(f"Transcription error: {e}")
                raise e

            logger.info(f"Transcription result: {result}")

            # Prepare the result
            transcript_text = result['text']
            if isinstance(transcript_text, bytes):
                transcript_text = transcript_text.decode('utf-8')

            return {
                'transcript': f"{transcript_text}\n\nSource: {url}",
                'title': info.get('description', ''),
                'author': f"{info.get('uploader', '')} ({info.get('channel', '')})",
                'source_url': url
            }

        finally:
            # Cleanup temporary file
            if os.path.exists(temp_file):
                os.remove(temp_file)
