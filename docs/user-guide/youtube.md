# YouTube Memories

MemoryLane can store supported YouTube videos by using their available transcripts as the textual representation of the video.

## How it works

```text
YouTube URL
    ↓
Detect video
    ↓
Retrieve transcript
    ↓
Create textual content
    ↓
Chunk
    ↓
Generate embeddings
    ↓
Store in Solr
```

For a recognized YouTube video URL, the backend attempts to retrieve the video's transcript instead of treating the video-player page itself as ordinary webpage text.

The transcript is then processed through the same general pipeline used for other memories.

## Video metadata

The stored textual representation can include information such as:

- Video title
- Channel
- Duration when available
- YouTube as the source
- Transcript text

## Transcript availability

Transcript retrieval depends on the video having an accessible transcript. If a transcript cannot be retrieved, the video cannot be converted into a searchable textual memory through this path.

## Automatic capture

Automatic capture applies additional YouTube checks. For example, very long videos may be skipped during automatic capture, while manually requested capture can use the manual path.
