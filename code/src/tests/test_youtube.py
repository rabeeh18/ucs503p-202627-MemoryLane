from unittest.mock import MagicMock, patch

from backend import youtube_utils
from backend.youtube_utils import (
    extract_video_id, is_youtube_short, is_youtube_url, process_youtube_video,
)

VIDEO_ID = "dQw4w9WgXcQ"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


def test_is_youtube_url_exact_host_only():
    assert is_youtube_url(WATCH_URL)
    assert is_youtube_url(f"https://youtu.be/{VIDEO_ID}")
    assert is_youtube_url(f"https://m.youtube.com/watch?v={VIDEO_ID}")
    assert not is_youtube_url(f"https://youtube.com.evil.example/watch?v={VIDEO_ID}")
    assert not is_youtube_url(f"https://notyoutube.com/watch?v={VIDEO_ID}")
    assert not is_youtube_url("https://evil.example/?u=youtube.com")


def test_extract_video_id_validates_format():
    assert extract_video_id(WATCH_URL) == VIDEO_ID
    assert extract_video_id(f"https://youtu.be/{VIDEO_ID}") == VIDEO_ID
    assert extract_video_id(f"https://www.youtube.com/embed/{VIDEO_ID}") == VIDEO_ID
    assert extract_video_id("https://www.youtube.com/watch?v=../../etc") is None
    assert extract_video_id("https://www.youtube.com/watch?v=short") is None


def test_shorts_are_skipped():
    assert is_youtube_short(f"https://www.youtube.com/shorts/{VIDEO_ID}")
    content, title, skip = process_youtube_video(f"https://www.youtube.com/shorts/{VIDEO_ID}", True)
    assert content is None and "Shorts" in skip


def _fake_transcript_api(texts):
    transcript = MagicMock()
    transcript.fetch.return_value.to_raw_data.return_value = [{"text": t} for t in texts]
    transcript_list = MagicMock()
    transcript_list.find_transcript.return_value = transcript
    api = MagicMock()
    api.return_value.list.return_value = transcript_list
    return api


def _fake_get(duration):
    def fake_get(url, **kwargs):
        resp = MagicMock()
        if url == "https://www.youtube.com/oembed":
            resp.json.return_value = {"title": "YT Video", "author_name": "Channel"}
        else:
            resp.text = f'"lengthSeconds":"{duration}"' if duration is not None else ""
        return resp
    return fake_get


def test_transcript_uses_instance_api_and_formats_content():
    api = _fake_transcript_api(["hello", "world"])
    with patch.object(youtube_utils, "YouTubeTranscriptApi", api), \
         patch.object(youtube_utils.httpx, "get", side_effect=_fake_get(300)) as mock_get:
        content, title, skip = process_youtube_video(WATCH_URL, False)
    assert skip is None
    assert title == "YT Video"
    assert "Source: YouTube" in content and "hello world" in content
    api.return_value.list.assert_called_once_with(VIDEO_ID)
    # Metadata only ever comes from fixed youtube.com URLs
    fetched = {c.args[0] for c in mock_get.call_args_list}
    assert fetched == {"https://www.youtube.com/oembed", f"https://www.youtube.com/watch?v={VIDEO_ID}"}


def test_metadata_never_fetches_user_supplied_url():
    api = _fake_transcript_api(["hi"])
    user_url = f"https://m.youtube.com/watch?v={VIDEO_ID}&x=attacker"
    with patch.object(youtube_utils, "YouTubeTranscriptApi", api), \
         patch.object(youtube_utils.httpx, "get", side_effect=_fake_get(60)) as mock_get:
        process_youtube_video(user_url, False)
    assert all(c.args[0] != user_url for c in mock_get.call_args_list)


def test_long_video_skipped_unless_manual():
    api = _fake_transcript_api(["hello"])
    with patch.object(youtube_utils, "YouTubeTranscriptApi", api), \
         patch.object(youtube_utils.httpx, "get", side_effect=_fake_get(7201)):
        _, _, skip = process_youtube_video(WATCH_URL, False)
        assert skip == "Skipped: YouTube video is over 2 hours long"
        content, _, skip = process_youtube_video(WATCH_URL, True)
        assert skip is None and content


def test_unknown_duration_skipped_unless_manual():
    api = _fake_transcript_api(["hello"])
    with patch.object(youtube_utils, "YouTubeTranscriptApi", api), \
         patch.object(youtube_utils.httpx, "get", side_effect=_fake_get(None)):
        _, _, skip = process_youtube_video(WATCH_URL, False)
        assert "duration" in skip
        _, _, skip = process_youtube_video(WATCH_URL, True)
        assert skip is None


def test_missing_transcript_is_skipped():
    api = MagicMock()
    api.return_value.list.side_effect = Exception("No transcript")
    with patch.object(youtube_utils, "YouTubeTranscriptApi", api):
        _, _, skip = process_youtube_video(WATCH_URL, True)
    assert skip == youtube_utils.NO_TRANSCRIPT


# ---- details fetched by the extension (YouTube blocks the server) --------------------

PROVIDED = {
    "transcript": "so today we ride through the countryside",
    "language": "en",
    "title": "Riding Through Japan",
    "channel": "Ajay",
    "description": "A weekend motorcycle ride through the hills and rice fields of rural Japan, "
                   "with a stop at a mountain shrine and a small roadside cafe.",
    "duration_seconds": 1402,
}


def _no_network():
    api = MagicMock()
    api.return_value.list.side_effect = AssertionError("server must not fetch the transcript")
    get = MagicMock(side_effect=AssertionError("server must not fetch metadata"))
    return patch.object(youtube_utils, "YouTubeTranscriptApi", api), patch.object(youtube_utils.httpx, "get", get)


def test_provided_transcript_is_used_without_fetching():
    no_api, no_get = _no_network()
    with no_api, no_get:
        content, title, skip = process_youtube_video(WATCH_URL, False, provided=PROVIDED)
    assert skip is None and title == "Riding Through Japan"
    assert "Channel: Ajay" in content and "Duration: 1402 seconds" in content
    assert "Description:\nA weekend motorcycle ride" in content
    assert content.endswith("Transcript:\nso today we ride through the countryside")


def test_video_without_captions_is_saved_from_its_description():
    no_api, no_get = _no_network()
    with no_api, no_get:
        content, _, skip = process_youtube_video(WATCH_URL, True, provided={**PROVIDED, "transcript": None})
    assert skip is None
    assert "rice fields of rural Japan" in content and "Transcript:" not in content


def test_short_description_without_captions_is_skipped():
    no_api, no_get = _no_network()
    with no_api, no_get:
        _, _, skip = process_youtube_video(
            WATCH_URL, True, provided={**PROVIDED, "transcript": None, "description": "subscribe!"})
    assert skip == youtube_utils.NO_TRANSCRIPT


def test_provided_duration_drives_the_auto_capture_rules():
    no_api, no_get = _no_network()
    with no_api, no_get:
        _, _, skip = process_youtube_video(WATCH_URL, False, provided={**PROVIDED, "duration_seconds": 7201})
        assert skip == "Skipped: YouTube video is over 2 hours long"
        _, _, skip = process_youtube_video(WATCH_URL, False, provided={**PROVIDED, "duration_seconds": None})
        assert "duration" in skip
        _, _, skip = process_youtube_video(WATCH_URL, True, provided={**PROVIDED, "duration_seconds": 7201})
        assert skip is None


def test_metadata_is_fetched_when_the_extension_sent_only_a_transcript():
    with patch.object(youtube_utils.httpx, "get", side_effect=_fake_get(90)):
        content, title, skip = process_youtube_video(WATCH_URL, False, provided={"transcript": "hello there"})
    assert skip is None and title == "YT Video" and "Duration: 90 seconds" in content


def test_shorts_are_skipped_even_with_provided_details():
    _, _, skip = process_youtube_video(f"https://www.youtube.com/shorts/{VIDEO_ID}", True, provided=PROVIDED)
    assert "Shorts" in skip
