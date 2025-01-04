const testFunction = async () => {
  try {
    const response = await fetch('https://us-east4-davehague-site.cloudfunctions.net/transcribe-reel', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        url: 'https://www.instagram.com/reels/DDcVZQ_pyL9/',
        upload_to_readwise: false
      })
    });
    const data = await response.json();
    console.log(data);
  } catch (error) {
    console.error('Error:', error);
  }
};

testFunction();
