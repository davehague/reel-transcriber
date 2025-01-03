import functions_framework
from flask import jsonify
from ..core.transcriber import InstagramTranscriber
from ..core.uploader import ReadwiseUploader


@functions_framework.http
def transcribe_reel(request):
    # Set CORS headers for the preflight request
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    # Set CORS headers for the main request
    headers = {'Access-Control-Allow-Origin': '*'}

    try:
        request_json = request.get_json()

        if not request_json or 'url' not in request_json:
            return jsonify({'error': 'No URL provided'}), 400, headers

        url = request_json['url']
        upload_to_readwise = request_json.get('upload_to_readwise', False)
        readwise_token = request_json.get('readwise_token')

        # Initialize transcriber
        transcriber = InstagramTranscriber()

        # Get transcript and metadata
        result = transcriber.transcribe(url, '/tmp')

        # Upload to Readwise if requested
        if upload_to_readwise:
            if not readwise_token:
                return jsonify({'error': 'Readwise token required for upload'}), 400, headers

            uploader = ReadwiseUploader(readwise_token)
            upload_result = uploader.upload_transcript(result)
            result['readwise_upload'] = upload_result

        return jsonify(result), 200, headers

    except Exception as e:
        return jsonify({'error': str(e)}), 500, headers