# Social Media Reel Transcriber

A tool to transcribe Instagram Reels and optionally upload them to Readwise. Available both as a CLI tool and a Google Cloud Function.

## Features

- Transcribe Instagram Reels using OpenAI's Whisper model
- Extract video metadata (title, author)
- Upload transcripts to Readwise
- Available as both CLI tool and cloud function

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/reel-transcriber.git
cd reel-transcriber
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
# On Windows
.\venv\Scripts\activate
# On Unix
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a .env file with your Readwise token:
```
READWISE_TOKEN=your_token_here
```

## Usage

### Command Line Interface

1. Using Python directly:
```bash
# First, activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Then run the script
python -m src.cli.main https://instagram.com/reel/your-url --no-upload
````

2. Using the batch script (Windows):
```bash
scripts\transcribe.bat
```

Command line options:
- `--no-upload`: Skip uploading to Readwise
- `--temp-dir PATH`: Specify directory for temporary files

### Google Cloud Function

The transcriber is also available as a Google Cloud Function. Deploy using:

1. Create new Cloud Function in Google Cloud Console
2. Set runtime to Python 3.11+
3. Set entry point to "transcribe_reel"
4. Upload the code from src/cloud/main.py
5. Deploy

Call the function with:
```javascript
fetch('FUNCTION_URL', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    url: 'INSTAGRAM_URL',
    upload_to_readwise: true,  // optional
    readwise_token: 'TOKEN'    // required if upload_to_readwise is true
  })
});
```

## Requirements

- Python 3.11+
- Readwise API token (for upload functionality)

## License

MIT