from flask import Flask
from main import transcribe_reel

app = Flask(__name__)


class MockRequest:
    def __init__(self, method, json_data):
        self.method = method
        self._json = json_data

    def get_json(self):
        return self._json


request = MockRequest('POST', {
    'url': 'https://www.instagram.com/reels/DDcVZQ_pyL9/',
    'upload_to_readwise': False
})

with app.app_context():
    result = transcribe_reel(request)
    print(result)