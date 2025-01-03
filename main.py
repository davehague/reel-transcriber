# import subprocess
# from pathlib import Path
# import whisper
# import yt_dlp
#
# from ReadwiseUploader import ReadwiseUploader
# from dotenv import load_dotenv
# import os
#
#
# def transcribe_reel(url):
#     # Download video
#     subprocess.run(['yt-dlp', url, '-o', 'temp_video.mp4'])
#
#     # Load model and transcribe
#     model = whisper.load_model("base")
#     result = model.transcribe("temp_video.mp4")
#
#     # Cleanup
#     Path('temp_video.mp4').unlink()
#     return f"{result['text']}\n\n{url}"
#
#
# if __name__ == '__main__':
#     load_dotenv()
#     url = "https://www.instagram.com/reel/DCsI66XPlaq/?igsh=MTI1YXVnZ2FnMGd0bw%3D%3D"
#
#     with yt_dlp.YoutubeDL() as ydl:
#         info = ydl.extract_info(url, download=False)
#
#     transcript = transcribe_reel(url)
#
#     uploader = ReadwiseUploader(os.getenv('READWISE_TOKEN'))
#     result = uploader.upload_transcript(
#         text=transcript,
#         title=info['description'],
#         author=f"{info['uploader']} (@{info['channel']}) on Instagram reels",
#         source_url=url,
#         # image_url=info['thumbnail']
#     )