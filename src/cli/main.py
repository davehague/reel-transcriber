# src/cli/main.py
import os
import sys
import argparse
from dotenv import load_dotenv
from ..core.transcriber import InstagramTranscriber
from ..core.uploader import ReadwiseUploader
import colorama
from colorama import Fore, Style


def main():
    colorama.init()

    parser = argparse.ArgumentParser(description='Transcribe Instagram Reels and upload to Readwise')
    parser.add_argument('url', help='Instagram Reel URL')
    parser.add_argument('--no-upload', action='store_true', help='Only transcribe, do not upload to Readwise')
    parser.add_argument('--temp-dir', help='Directory for temporary files')
    args = parser.parse_args()

    try:
        transcriber = InstagramTranscriber()

        print(f"\n{Fore.CYAN}Transcribing...{Style.RESET_ALL}")
        result = transcriber.transcribe(args.url, args.temp_dir)

        print(f"\n{Fore.GREEN}=== Transcript ==={Style.RESET_ALL}")
        print(f"{Fore.LIGHTYELLOW_EX}")
        print(result['transcript'])
        print(f"{Style.RESET_ALL}")

        print(f"\n{Fore.GREEN}=== Metadata ==={Style.RESET_ALL}")
        print(f"Title: {result['title']}")
        print(f"Author: {result['author']}")

        print("===============================")

        # Upload if requested
        if not args.no_upload:
            load_dotenv()
            token = os.getenv('READWISE_TOKEN')
            if not token:
                print(f"\n{Fore.RED}Error: READWISE_TOKEN not found in environment variables{Style.RESET_ALL}")
                sys.exit(1)

            print(f"\n{Fore.CYAN}Uploading to Readwise...{Style.RESET_ALL}")
            uploader = ReadwiseUploader(token)
            upload_result = uploader.upload_transcript(result)
            print(f"\n{Fore.GREEN}Successfully uploaded to Readwise!{Style.RESET_ALL}")

    except Exception as e:
        print(f"\n{Fore.RED}Error: {str(e)}{Style.RESET_ALL}")
        sys.exit(1)


if __name__ == "__main__":
    main()