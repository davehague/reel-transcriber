import functions_framework
from flask import jsonify
import yt_dlp
import requests
import os
from datetime import datetime, timezone
from typing import Dict, Optional
import logging
from google.cloud import speech_v1
from google.cloud import storage
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class YDLLogger:
    def debug(self, msg):
        if isinstance(msg, bytes):
            msg = msg.decode('utf-8', 'ignore')
        logger.debug(msg)

    def warning(self, msg):
        if isinstance(msg, bytes):
            msg = msg.decode('utf-8', 'ignore')
        logger.warning(msg)

    def error(self, msg):
        if isinstance(msg, bytes):
            msg = msg.decode('utf-8', 'ignore')
        logger.error(msg)


class InstagramTranscriber:
    def __init__(self):
        self.speech_client = speech_v1.SpeechClient()
        self.storage_client = storage.Client()
        self.bucket_name = os.environ.get('GCP_STORAGE_BUCKET')  # You'll need to set this

    def normalize_instagram_url(self, url: str) -> str:
        """Convert various Instagram URL formats to the standard format."""
        if 'instagram.com/reels/' in url:
            # Convert from /reels/ID/ to /reel/ID/
            return url.replace('/reels/', '/reel/')
        return url

    def get_video_info(self, url: str) -> Dict:
        url = self.normalize_instagram_url(url)
        logger.info(f"Normalized URL: {url}")

        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'encoding': None,
            'logger': YDLLogger()
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # Ensure all string values are properly decoded
            if isinstance(info.get('description'), bytes):
                info['description'] = info['description'].decode('utf-8')
            if isinstance(info.get('uploader'), bytes):
                info['uploader'] = info['uploader'].decode('utf-8')
            if isinstance(info.get('channel'), bytes):
                info['channel'] = info['channel'].decode('utf-8')
        return info

    def download_video(self, url: str, output_path: str) -> None:
        url = self.normalize_instagram_url(url)
        logger.info(f"Starting download with output path: {output_path} for URL: {url}")
        ydl_opts = {
            'outtmpl': output_path,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'encoding': None,  # Let yt-dlp handle encoding
            'logger': YDLLogger(),
            'progress_hooks': []
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info("Starting yt-dlp download")
                ydl.download([url])
                logger.info("yt-dlp download completed")
        except Exception as e:
            logger.error(f"Error during download: {str(e)}", exc_info=True)
            raise
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    def upload_to_gcs(self, local_path: str) -> str:
        logger.info(f"Preparing to upload file from {local_path}")
        if not os.path.exists(local_path):
            logger.error(f"Local file not found at {local_path}")
            logger.info(f"Directory contents: {os.listdir(os.path.dirname(local_path))}")
            raise FileNotFoundError(f"Local file not found at {local_path}")

        bucket = self.storage_client.bucket(self.bucket_name)
        blob_name = f"audio/{uuid.uuid4()}.mp3"
        blob = bucket.blob(blob_name)

        logger.info(f"Starting upload to gs://{self.bucket_name}/{blob_name}")
        blob.upload_from_filename(local_path)
        logger.info("Upload completed")

        return f"gs://{self.bucket_name}/{blob_name}"

    def transcribe(self, url: str, temp_dir: Optional[str] = None) -> Dict:
        logger.info(f"Starting transcription for URL: {url}")

        if not self.bucket_name:
            raise ValueError("GCP_STORAGE_BUCKET environment variable not set")

        info = self.get_video_info(url)
        logger.info(f"Video info: {info}")

        temp_dir = temp_dir or '/tmp'
        temp_file = os.path.join(temp_dir, 'temp_audio')  # yt-dlp will add the extension

        try:
            logger.info(f"Attempting to download video from {url}")
            self.download_video(url, temp_file)
            logger.info(f"Video downloaded to {temp_file}")
            logger.info("Uploading to GCS")
            gcs_uri = self.upload_to_gcs(temp_file)
            logger.info(f"Uploaded to GCS: {gcs_uri}")

            # Configure the transcription request
            audio = speech_v1.RecognitionAudio(uri=gcs_uri)
            config = speech_v1.RecognitionConfig(
                encoding=speech_v1.RecognitionConfig.AudioEncoding.MP3,
                sample_rate_hertz=44100,
                language_code="en-US",
                enable_automatic_punctuation=True,
                audio_channel_count=2,
                enable_word_time_offsets=True,
            )

            # Start long-running transcription
            operation = self.speech_client.long_running_recognize(config=config, audio=audio)
            response = operation.result()

            # Combine all transcriptions
            transcript_text = " ".join(
                result.alternatives[0].transcript
                for result in response.results
            )

            # Clean up GCS
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_uri.replace(f"gs://{self.bucket_name}/", ""))
            blob.delete()

            return {
                'transcript': f"{str(transcript_text)}\n\nSource: {url}",
                'title': str(info.get('description', '')),
                'author': f"{str(info.get('uploader', ''))} ({str(info.get('channel', ''))})",
                'source_url': url
            }
        finally:
            # Clean up both potential files
            for ext in ['.mp3', '.mp4', '']:
                file_path = temp_file + ext
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Cleaned up {file_path}")


# ReadwiseUploader class remains unchanged
class ReadwiseUploader:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://readwise.io/api/v2"
        self.headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json"
        }

    def upload_transcript(self, transcript_data: Dict) -> Dict:
        endpoint = f"{self.base_url}/highlights/"

        text = transcript_data['transcript'][:8191]
        title = transcript_data['title'][:511]
        author = transcript_data['author'][:1024]

        data = {
            "highlights": [{
                "text": text,
                "title": title,
                "author": author,
                "source_url": transcript_data['source_url'],
                "category": "podcasts",
                "source_type": "instagram_reel",
                "highlighted_at": datetime.now(timezone.utc).isoformat()
            }]
        }

        response = requests.post(endpoint, headers=self.headers, json=data)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Upload failed: {response.status_code} - {response.text}")

    def validate_token(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/auth/", headers=self.headers)
            return response.status_code == 204
        except:
            return False


@functions_framework.http
def transcribe_reel(request):
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return '', 204, headers

    headers = {'Access-Control-Allow-Origin': '*'}

    try:
        logger.info("Starting transcribe_reel function")
        request_json = request.get_json()
        logger.info(f"Received request: {request_json}")

        if not request_json or 'url' not in request_json:
            logger.error("No URL provided in request")
            return jsonify({'error': 'No URL provided'}), 400, headers

        url = request_json['url']
        upload_to_readwise = request_json.get('upload_to_readwise', False)
        readwise_token = request_json.get('readwise_token')

        transcriber = InstagramTranscriber()
        result = transcriber.transcribe(url, '/tmp')

        if upload_to_readwise:
            if not readwise_token:
                return jsonify({'error': 'Readwise token required for upload'}), 400, headers

            uploader = ReadwiseUploader(readwise_token)
            upload_result = uploader.upload_transcript(result)
            result['readwise_upload'] = upload_result

        return jsonify(result), 200, headers

    except Exception as e:
        logger.error(f"Error in transcribe_reel: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500, headers