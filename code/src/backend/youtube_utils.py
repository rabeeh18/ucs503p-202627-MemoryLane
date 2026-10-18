import re
import urllib.parse
import logging

import httpx
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

MAX_AUTO_DURATION_SECONDS = 7200
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _host(url: str) -> str:
    netloc = urllib.parse.urlparse(url).hostname or ""
    netloc = netloc.lower()
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    return netloc


def is_youtube_url(url: str) -> bool:
    """Check if a given URL belongs to YouTube (exact host match only)."""
    try:
        return _host(url) in ('youtube.com', 'youtu.be', 'm.youtube.com')
    except Exception:
        return False

def is_youtube_short(url: str) -> bool:
    """Check if a given YouTube URL is a Short."""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.path.lower().startswith('/shorts/')
    except Exception:
        return False

def extract_video_id(url: str) -> str | None:
    """Extract and validate the video ID from a YouTube URL."""
    video_id = None
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = _host(url)

        if netloc == 'youtu.be':
            video_id = parsed.path.strip('/').split('/')[0]
        elif netloc in ('youtube.com', 'm.youtube.com'):
            if parsed.path == '/watch':
                query = urllib.parse.parse_qs(parsed.query)
                video_id = query.get('v', [None])[0]
            elif parsed.path.startswith('/embed/') or parsed.path.startswith('/v/'):
                video_id = parsed.path.split('/')[2]

    except Exception as e:
        logger.warning(f"Error parsing YouTube URL for video ID: {e}")

    if video_id and _VIDEO_ID_RE.match(video_id):
        return video_id
    return None

def get_youtube_transcript(video_id: str) -> str | None:
    """Fetch the transcript as plain text, preferring English, else any language."""
    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        try:
            transcript_obj = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
        except Exception:
            transcript_obj = next(iter(transcript_list))
        snippets = transcript_obj.fetch().to_raw_data()
        text = " ".join(s.get("text", "").strip() for s in snippets if s.get("text"))
        return text or None
    except Exception as e:
        logger.warning(f"Failed to fetch transcript for video {video_id}: {e}")
        return None


def get_youtube_metadata(video_id: str) -> tuple[str | None, str | None, int | None]:
    """Return (title, channel, duration_seconds). Only fixed youtube.com URLs built
    from the validated video id are fetched, never a user-supplied URL."""
    title = channel = None
    duration = None
    watch_url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        oembed = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": watch_url, "format": "json"},
            timeout=5.0,
        ).json()
        title = oembed.get("title")
        channel = oembed.get("author_name")
    except Exception:
        pass

    try:
        html = httpx.get(watch_url, timeout=10.0).text
        match_len = re.search(r'"lengthSeconds":"(\d+)"', html)
        if match_len:
            duration = int(match_len.group(1))
    except Exception:
        pass

    return title, channel, duration


def process_youtube_video(url: str, is_manual: bool) -> tuple[str | None, str | None, str | None]:
    """Returns (content, title, skip_message). If skip_message is set, don't save."""
    if is_youtube_short(url):
        return None, None, "Skipped: YouTube Shorts are intentionally skipped"

    video_id = extract_video_id(url)
    if not video_id:
        return None, None, "Skipped: Invalid YouTube URL"

    transcript = get_youtube_transcript(video_id)
    if not transcript:
        return None, None, "Skipped: Could not fetch transcript"

    title, channel, duration = get_youtube_metadata(video_id)

    if not is_manual:
        if duration is None:
            return None, None, "Skipped: Could not reliably determine video duration"
        if duration > MAX_AUTO_DURATION_SECONDS:
            return None, None, "Skipped: YouTube video is over 2 hours long"

    title = title or "YouTube Video"
    dur_str = f"{duration} seconds" if duration is not None else "Unknown"
    content = (
        f"Title: {title}\nChannel: {channel or 'Unknown'}\nDuration: {dur_str}\n"
        f"Source: YouTube\n\n{transcript}"
    )
    return content, title, None
