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
import time
from openai import OpenAI

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
        # Google Speech-to-Text clients
        self.speech_client = speech_v1.SpeechClient()
        self.storage_client = storage.Client()
        self.bucket_name = os.environ.get('GCP_STORAGE_BUCKET')

        # OpenAI client (initialize only if API key is present)
        self.openai_client = OpenAI() if os.environ.get('OPENAI_API_KEY') else None

        # Instagram credentials
        self.instagram_username = os.environ.get('INSTAGRAM_USERNAME')
        self.instagram_password = os.environ.get('INSTAGRAM_PASSWORD')

    def normalize_instagram_url(self, url: str) -> str:
        """Convert various Instagram URL formats to the standard format."""
        if 'instagram.com/reels/' in url:
            # Convert from /reels/ID/ to /reel/ID/
            return url.replace('/reels/', '/reel/')
        return url

    def get_video_info(self, url: str) -> Dict:
        url = self.normalize_instagram_url(url)
        logger.info(f"Normalized URL: {url}")

        cookies = self.get_instagram_cookies()

        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'encoding': None,
            'logger': YDLLogger(),
            'cookiefile': None,
            'cookiesfrombrowser': None,
            'cookies': cookies  # Use the cookies directly
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

        cookies = self.get_instagram_cookies()
        logger.info("Got Instagram cookies")

        ydl_opts = {
            'outtmpl': output_path,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'encoding': None,
            'logger': YDLLogger(),
            'progress_hooks': [
                lambda d: logger.info(f"Download progress: {d.get('status')} - {d.get('filename', 'unknown file')}")],
            'cookies': cookies
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info("Starting yt-dlp download")
                ydl.download([url])
                logger.info("yt-dlp download completed")

                # List directory contents after download
                dir_path = os.path.dirname(output_path)
                logger.info(f"Directory contents after download: {os.listdir(dir_path)}")
        except Exception as e:
            logger.error(f"Error during download: {str(e)}", exc_info=True)
            raise

    def get_instagram_cookies(self) -> Dict:
        """Get cookies needed for Instagram authentication."""
        session = requests.Session()
        # First request to get the csrftoken
        session.get('https://www.instagram.com/accounts/login/')
        cookies = session.cookies.get_dict()

        # Login request
        login_data = {
            'username': self.instagram_username,
            'enc_password': f'#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{self.instagram_password}',
            'queryParams': {},
            'optIntoOneTap': 'false'
        }

        login_headers = {
            'X-CSRFToken': cookies.get('csrftoken', ''),
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://www.instagram.com/accounts/login/'
        }

        session.post(
            'https://www.instagram.com/accounts/login/ajax/',
            data=login_data,
            headers=login_headers
        )

        return session.cookies.get_dict()

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

    def transcribe_with_whisper(self, actual_file: str) -> str:
        """Transcribe audio using OpenAI's Whisper API."""
        if not self.openai_client:
            raise ValueError("OpenAI API key not set in environment variables")

        logger.info("Starting Whisper transcription")
        with open(actual_file, "rb") as audio_file:
            transcript = self.openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        logger.info("Whisper transcription completed")
        return transcript

    def transcribe_with_google(self, actual_file: str) -> str:
        """Transcribe audio using Google Speech-to-Text."""
        if not self.bucket_name:
            raise ValueError("GCP_STORAGE_BUCKET environment variable not set")

        logger.info("Uploading to GCS")
        gcs_uri = self.upload_to_gcs(actual_file)
        logger.info(f"Uploaded to GCS: {gcs_uri}")

        try:
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
            logger.info("Waiting for transcription to complete...")
            response = operation.result()
            logger.info("Transcription completed")

            # Combine all transcriptions
            return " ".join(
                result.alternatives[0].transcript
                for result in response.results
            )
        finally:
            # Clean up GCS
            logger.info("Cleaning up GCS bucket")
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_uri.replace(f"gs://{self.bucket_name}/", ""))
            blob.delete()
            logger.info("GCS cleanup completed")

    def transcribe(self, url: str, temp_dir: Optional[str] = None, use_whisper: bool = True) -> Dict:
        """
        Transcribe an Instagram video/reel using either OpenAI's Whisper or Google Speech-to-Text.

        Args:
            url (str): The Instagram video/reel URL to transcribe
            temp_dir (Optional[str]): Directory for temporary files. Defaults to /tmp
            use_whisper (bool): If True, use OpenAI's Whisper API; if False, use Google Speech-to-Text

        Returns:
            Dict: Contains transcript text, title, author, and source URL
        """
        logger.info(f"Starting transcription for URL: {url}")

        info = self.get_video_info(url)
        logger.info(f"Video info: {info}")

        temp_dir = temp_dir or '/tmp'
        base_temp_file = os.path.join(temp_dir, 'temp_audio')

        try:
            logger.info(f"Attempting to download video from {url}")
            self.download_video(url, base_temp_file)
            logger.info(f"Video downloaded to {base_temp_file}")

            # Look for the actual file with extension
            actual_file = None
            for ext in ['.mp3', '.m4a', '.wav']:
                potential_file = base_temp_file + ext
                if os.path.exists(potential_file):
                    actual_file = potential_file
                    logger.info(f"Found audio file: {potential_file}")
                    break

            if not actual_file:
                logger.error(f"No audio file found in {temp_dir}")
                logger.info(f"Directory contents: {os.listdir(temp_dir)}")
                raise FileNotFoundError(f"No audio file found with base name {base_temp_file}")

            # Choose transcription method
            transcript_text = (
                self.transcribe_with_whisper(actual_file)
                if use_whisper else
                self.transcribe_with_google(actual_file)
            )

            return {
                'transcript': f"{str(transcript_text)}\n\nSource: {url}",
                'title': str(info.get('description', '')),
                'author': f"{str(info.get('uploader', ''))} ({str(info.get('channel', ''))})",
                'source_url': url
            }

        except Exception as e:
            logger.error(f"Error in transcribe: {str(e)}", exc_info=True)
            raise

        finally:
            # Clean up temporary files
            logger.info("Cleaning up temporary files")
            for ext in ['.mp3', '.m4a', '.wav', '']:
                file_path = base_temp_file + ext
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.info(f"Cleaned up {file_path}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up {file_path}: {str(e)}")


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
        use_whisper = request_json.get('use_whisper', True)  # Default to Whisper

        transcriber = InstagramTranscriber()
        result = transcriber.transcribe(url, '/tmp', use_whisper=use_whisper)

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