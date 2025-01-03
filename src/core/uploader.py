import requests
from datetime import datetime, timezone
from typing import Dict


class ReadwiseUploader:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://readwise.io/api/v2"
        self.headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json"
        }

    def upload_transcript(self, transcript_data: Dict) -> Dict:
        """
        Upload transcript and metadata to Readwise

        Args:
            transcript_data: Dictionary containing:
                - transcript: The transcribed text
                - title: Title for the highlight
                - author: Author name
                - source_url: Original URL

        Returns:
            Dict: Readwise API response

        Raises:
            Exception: If upload fails
        """
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
        """
        Validate the Readwise token

        Returns:
            bool: True if token is valid
        """
        try:
            response = requests.get(
                f"{self.base_url}/auth/",
                headers=self.headers
            )
            return response.status_code == 204
        except:
            return False