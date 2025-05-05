import functions_framework
from flask import jsonify
import yt_dlp
import requests
import os
import json
import traceback
from datetime import datetime, timezone
from typing import Dict, Optional
import logging
import sys
from google.cloud import speech_v1
from google.cloud import storage
import uuid
import time
from openai import OpenAI

# Configure structured logging
class StructuredFormatter(logging.Formatter):
    def format(self, record):
        # Create a structured log record
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'lineno': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            # Get formatted exception info as a single string
            exc_text = self.formatException(record.exc_info)
            log_entry['exception'] = exc_text
        
        # Return as a single JSON string
        return json.dumps(log_entry)

# Configure logging
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(StructuredFormatter())
logger = logging.getLogger('reel_transcriber')
logger.setLevel(logging.INFO)
logger.addHandler(handler)
logger.propagate = False  # Prevent duplicate logs


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

        try:
            logger.info("Attempting to get Instagram cookies")
            cookies = self.get_instagram_cookies()
            logger.info(f"Retrieved cookies with keys: {list(cookies.keys())}")

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
            
            logger.info("Starting yt-dlp extraction for video info")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Extracting info for URL: {url}")
                info = ydl.extract_info(url, download=False)
                logger.info("Successfully extracted video info")
                
                # Ensure all string values are properly decoded
                if isinstance(info.get('description'), bytes):
                    info['description'] = info['description'].decode('utf-8')
                if isinstance(info.get('uploader'), bytes):
                    info['uploader'] = info['uploader'].decode('utf-8')
                if isinstance(info.get('channel'), bytes):
                    info['channel'] = info['channel'].decode('utf-8')
                    
                # Log key video attributes for debugging
                logger.info(f"Video info retrieved - title: {info.get('title', 'N/A')[:30]}..., "
                           f"uploader: {info.get('uploader', 'N/A')}, "
                           f"duration: {info.get('duration', 'N/A')}")
                           
            return info
            
        except Exception as e:
            error_msg = f"Error in get_video_info for URL {url}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise

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
        except yt_dlp.utils.DownloadError as e:
            # Log detailed information for DownloadError
            error_msg = f"yt-dlp download error for URL {url}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Add diagnostic information
            logger.error(f"Instagram credentials: Username={self.instagram_username}, Password={'*' * (len(self.instagram_password or '') if self.instagram_password else 0)}")
            raise
        except Exception as e:
            error_msg = f"Error during download: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise

    def get_instagram_cookies(self) -> Dict:
        """Get cookies needed for Instagram authentication."""
        try:
            logger.info("Starting Instagram authentication process")
            session = requests.Session()
            
            # First request to get the csrftoken
            logger.info("Making initial request to Instagram to get csrftoken")
            initial_response = session.get('https://www.instagram.com/accounts/login/')
            logger.info(f"Initial request status code: {initial_response.status_code}")
            
            cookies = session.cookies.get_dict()
            logger.info(f"Got initial cookies: {list(cookies.keys())}")

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
            
            logger.info("Sending login request to Instagram")
            login_response = session.post(
                'https://www.instagram.com/accounts/login/ajax/',
                data=login_data,
                headers=login_headers
            )
            
            logger.info(f"Login response status code: {login_response.status_code}")
            
            # Try to get response JSON for debugging
            try:
                response_json = login_response.json()
                # Don't log the full response as it might contain sensitive info
                logger.info(f"Login response contains fields: {list(response_json.keys()) if isinstance(response_json, dict) else 'Not a dict'}")
                
                # Log authentication success/failure
                if isinstance(response_json, dict):
                    if response_json.get('authenticated', False):
                        logger.info("Instagram authentication successful")
                    else:
                        logger.warning(f"Instagram authentication failed: {response_json.get('message', 'Unknown reason')}")
            except Exception as json_error:
                logger.warning(f"Could not parse login response as JSON: {str(json_error)}")
            
            final_cookies = session.cookies.get_dict()
            logger.info(f"Final cookies: {list(final_cookies.keys())}")
            
            # Check for critical cookies
            if 'sessionid' not in final_cookies:
                logger.warning("Session ID cookie not found in response, authentication may have failed")
                
            return final_cookies
        except Exception as e:
            error_msg = f"Error during Instagram authentication: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Return empty dict as fallback
            return {}

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
            error_msg = f"Error in transcribe: {str(e)}"
            logger.error(error_msg, exc_info=True)
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
        # Log request data without sensitive information
        safe_request = {k: v for k, v in request_json.items() if k not in ['readwise_token']}
        logger.info(f"Received request: {json.dumps(safe_request)}")

        if not request_json or 'url' not in request_json:
            logger.error("No URL provided in request")
            return jsonify({'error': 'No URL provided'}), 400, headers

        url = request_json['url']
        user_id = request_json.get('userId')
        callback_url = request_json.get('callbackUrl')
        upload_to_readwise = request_json.get('upload_to_readwise', False)
        readwise_token = request_json.get('readwise_token')
        use_whisper = request_json.get('use_whisper', True)  # Default to Whisper

        # Verify needed parameters if we're using the callback approach
        if callback_url and not user_id:
            logger.error("userId is required when using callback")
            return jsonify({'error': 'userId is required when using callback'}), 400, headers

        # If callback provided, process asynchronously
        if callback_url:
            logger.info(f"Processing asynchronously with callback URL: {callback_url}")

            # Define the background processing function
            def process_transcription():
                try:
                    logger.info(f"Background processing started for URL: {url}")
                    # Initialize transcriber
                    transcriber = InstagramTranscriber()
                    
                    # Get transcript and metadata
                    result = transcriber.transcribe(url, '/tmp', use_whisper=use_whisper)
                    logger.info("Transcription completed, preparing to send callback")
                    
                    # Upload to Readwise if requested
                    if upload_to_readwise and readwise_token:
                        uploader = ReadwiseUploader(readwise_token)
                        upload_result = uploader.upload_transcript(result)
                        result['readwise_upload'] = upload_result
                    
                    # Call back to the app with results
                    logger.info(f"Sending callback to: {callback_url}")
                    
                    # Log the callback data
                    callback_data = {
                        'userId': user_id,
                        'result': result
                    }
                    # Safely log the callback data without overwhelming the logs
                    try:
                        # Create a sanitized version for logging (just basic info)
                        log_data = {
                            'userId': user_id,
                            'result': {
                                'title': result.get('title', '')[:50],
                                'author': result.get('author', '')[:50],
                                'transcript_length': len(result.get('transcript', '')),
                                'source_url': result.get('source_url', '')
                            }
                        }
                        logger.info(f"Callback data summary: {json.dumps(log_data)}")
                    except Exception as log_error:
                        logger.error(f"Error logging callback data: {log_error}")
                    
                    # Make the callback request
                    try:
                        callback_response = requests.post(
                            callback_url,
                            json=callback_data,
                            headers={'Content-Type': 'application/json'},
                            timeout=30  # Add a timeout
                        )
                        logger.info(f"Callback response status: {callback_response.status_code}")
                        logger.info(f"Callback response headers: {callback_response.headers}")
                        
                        # Log response content
                        try:
                            response_text = callback_response.text
                            logger.info(f"Callback response body: {response_text[:500]}{'...' if len(response_text) > 500 else ''}")
                        except Exception as text_error:
                            logger.error(f"Error reading callback response text: {text_error}")
                        
                        if not callback_response.ok:
                            logger.error(f"Callback failed with status code: {callback_response.status_code}")
                    except Exception as callback_error:
                        logger.error(f"Exception during callback request: {callback_error}", exc_info=True)
                except Exception as e:
                    # Log the full exception with traceback as a single record
                    error_msg = f"Error in background processing: {str(e)}"
                    logger.error(error_msg, exc_info=True)
            
            # Start processing in background
            import threading
            threading.Thread(target=process_transcription).start()
            logger.info("Background processing thread started")
            
            # Return immediate success response
            return jsonify({
                'success': True,
                'message': 'Transcription started successfully'
            }), 200, headers
        
        # Otherwise, process synchronously as before
        else:
            logger.info("Processing synchronously")
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
        error_msg = f"Error in transcribe_reel: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({'error': str(e), 'type': type(e).__name__}), 500, headers