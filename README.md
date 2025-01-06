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
The transcriber is also available as a Google Cloud Function.  Make sure the gcloud CLI is installed, then follow these steps:

#### Set up your environment yaml
```commandline
GCP_STORAGE_BUCKET: "your-bucket"
INSTAGRAM_USERNAME: "your-username"
INSTAGRAM_PASSWORD: "your-password"
```

#### List available projects
```commandline
gcloud projects list
```

#### Configure google cloud bucket
```commandline
gcloud storage buckets create gs://<your-project-id>-transcribe-reels
```
   
Deploy using gcloud CLI:

```bash
cd deploy
gcloud functions deploy transcribe-reel \
    --gen2 \
    --runtime python311 \
    --source . \
    --entry-point=transcribe_reel \
    --trigger-http \
    --allow-unauthenticated \
    --memory 1024mb \
    --timeout=180
``` 

#### Test the function
Use the script in `scripts/test.js`

```bash
node scripts/test.js
```


## Requirements

- Python 3.11+
- Readwise API token (for upload functionality)

## License

MIT