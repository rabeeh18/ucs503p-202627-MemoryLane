import re
import urllib.parse
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import logging

logger = logging.getLogger(__name__)

def is_youtube_url(url: str) -> bool:
    """Check if a given URL belongs to YouTube."""
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        return netloc in ('youtube.com', 'youtu.be', 'm.youtube.com')
    except Exception:
        return False

def is_youtube_short(url: str) -> bool:
    """Check if a given YouTube URL is a Short."""
    try:
        parsed = urllib.parse.urlparse(url)
        return '/shorts/' in parsed.path.lower()
    except Exception:
        return False

def extract_video_id(url: str) -> str | None:
    """Extract the video ID from a YouTube URL."""
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        
        if netloc == 'youtu.be':
            return parsed.path.lstrip('/')
            
        if netloc in ('youtube.com', 'm.youtube.com'):
            if parsed.path == '/watch':
                query = urllib.parse.parse_qs(parsed.query)
                return query.get('v', [None])[0]
            elif parsed.path.startswith('/embed/'):
                return parsed.path.split('/')[2]
            elif parsed.path.startswith('/v/'):
                return parsed.path.split('/')[2]
                
    except Exception as e:
        logger.warning(f"Error parsing YouTube URL for video ID: {e}")
        
    return None

def get_youtube_transcript(video_id: str) -> str | None:
    """Fetch and format the YouTube transcript as plain text, supporting any language."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to find an English transcript first, fallback to any available language (like Hindi)
        try:
            transcript_obj = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
        except Exception:
            # Get the first available transcript if English is not found
            transcript_obj = next(iter(transcript_list))
            
        transcript_data = transcript_obj.fetch()
        
        # Format the transcript into plain text
        formatter = TextFormatter()
        text_formatted = formatter.format_transcript(transcript_data)
        return text_formatted
    except Exception as e:
        logger.warning(f"Failed to fetch transcript for video {video_id}: {e}")
        return None
