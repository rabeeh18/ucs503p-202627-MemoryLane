# YouTube Videos

A YouTube video page has almost no readable text, so MemoryLane saves the video through its **transcript** (captions) and its description instead.

```text
youtube.com/watch?v=… or youtu.be/…
        ↓
Recognise the video id
        ↓
In your browser: fetch the title, channel, length,
description and captions from YouTube
        ↓
Title + channel + length + description + transcript
        ↓
Same pipeline as any page: chunk → embed → store
```

## Why your browser fetches the transcript

YouTube blocks transcript requests from cloud servers, and the MemoryLane server runs on AWS. Your browser isn't blocked, so when you save a video the extension fetches its captions and details from YouTube and sends them along with the page.

The extension does this from inside the YouTube tab, because YouTube's API refuses requests that come from an extension directly. It talks only to youtube.com, the same site you are already on, and sends no cookies.

The server only fetches a transcript itself when an older version of the extension sent nothing. It builds the video's URL from the video id and never fetches a URL sent by the browser.

## What gets stored

- Video title, channel and length
- The description (its first 2,000 characters)
- The transcript text: English captions if the video has them (uploaded before auto-generated), otherwise its first caption track in the original language

You then find the video by what was said in it, or by what its description says.

## Limits

- A video with no captions is saved from its title and description, if the description has at least 15 words. With neither, it can't be saved.
- MemoryLane's search model is trained on English. A transcript in another language is saved as it is (YouTube doesn't translate captions for this kind of request), so search finds such a video mainly through its title and description.
- Automatic capture skips videos longer than **two hours**, and skips them when their length can't be determined. **Remember this page** saves them anyway.
- YouTube Shorts and YouTube pages that aren't a video (home, channels, search) are never saved.
