# YouTube Videos

A YouTube video page has almost no readable text, so MemoryLane saves the video through its **transcript** instead.

```text
youtube.com/watch?v=… or youtu.be/…
        ↓
Recognise the video id
        ↓
Fetch title, channel and duration
        ↓
Fetch the transcript
        ↓
Title + channel + duration + transcript
        ↓
Same pipeline as any page: chunk → embed → store
```

The backend builds the video's URL itself from the video id. It never fetches a URL sent by the browser.

## What gets stored

- Video title
- Channel
- Duration
- The transcript text

You then find the video by what was said in it.

## Limits

- The video needs an available transcript (uploaded or auto-generated). Without one it can't be saved.
- Automatic capture skips videos longer than **two hours**, and skips them when their length can't be determined. **Remember this page** saves them anyway.
- YouTube pages that aren't a video (home, channels, search) are never captured automatically.
