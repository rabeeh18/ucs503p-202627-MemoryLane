// Tests for the extension's YouTube fetcher (code/src/extension/youtube.js), run here
// because the extension has no test runner of its own (as for domain.js).
import { describe, expect, it, vi } from 'vitest';
import { fetchYouTubeVideo, youtubeVideoId } from '../../../extension/youtube.js';

const ID = 'nvVoEFG3-As';

describe('youtubeVideoId', () => {
  it('reads watch, youtu.be, embed and mobile URLs', () => {
    expect(youtubeVideoId(`https://www.youtube.com/watch?v=${ID}&t=42`)).toBe(ID);
    expect(youtubeVideoId(`https://youtu.be/${ID}`)).toBe(ID);
    expect(youtubeVideoId(`https://www.youtube.com/embed/${ID}`)).toBe(ID);
    expect(youtubeVideoId(`https://m.youtube.com/watch?v=${ID}`)).toBe(ID);
  });

  it('rejects Shorts, other sites and malformed ids', () => {
    expect(youtubeVideoId(`https://www.youtube.com/shorts/${ID}`)).toBeNull();
    expect(youtubeVideoId(`https://youtube.com.evil.example/watch?v=${ID}`)).toBeNull();
    expect(youtubeVideoId('https://www.youtube.com/watch?v=../../x')).toBeNull();
    expect(youtubeVideoId('not a url')).toBeNull();
  });
});

function fakeYouTube({ tracks, details, status = 'OK', captionsXml = '', playerStatus = 200 } = {}) {
  const calls = [];
  const fetchImpl = vi.fn(async (url, options = {}) => {
    calls.push({ url, options });
    const reply = (body, httpStatus = 200) => ({ ok: httpStatus < 400, status: httpStatus, text: async () => body });
    if (url.includes('/watch?v=')) return reply('<script>ytcfg.set({"INNERTUBE_API_KEY": "KEY123"})</script>');
    if (url.includes('/youtubei/v1/player')) {
      return reply(JSON.stringify({
        playabilityStatus: { status },
        videoDetails: details ?? { title: 'Riding', author: 'Ajay', shortDescription: 'A ride.', lengthSeconds: '1402' },
        captions: tracks ? { playerCaptionsTracklistRenderer: { captionTracks: tracks } } : undefined,
      }), playerStatus);
    }
    return reply(captionsXml);
  });
  return { fetchImpl, calls };
}

const XML = '<?xml version="1.0"?><transcript>'
  + '<text start="0" dur="1">so today we&amp;#39;re riding</text>'
  + '<text start="1" dur="1">through &lt;b&gt;Japan&lt;/b&gt; &amp;amp; its hills</text>'
  + '<text start="2" dur="1"></text></transcript>';

describe('fetchYouTubeVideo', () => {
  it('follows the watch page → player API → captions flow', async () => {
    const { fetchImpl, calls } = fakeYouTube({
      tracks: [{ languageCode: 'en', baseUrl: 'https://www.youtube.com/api/timedtext?v=x&fmt=srv3' }],
      captionsXml: XML,
    });
    const video = await fetchYouTubeVideo(ID, fetchImpl, 'https://www.youtube.com');
    expect(video).toEqual({
      video_id: ID, transcript: "so today we're riding through Japan & its hills", language: 'en',
      title: 'Riding', channel: 'Ajay', description: 'A ride.', duration_seconds: 1402, error: null,
    });
    expect(calls[0].url).toBe(`https://www.youtube.com/watch?v=${ID}`);
    expect(calls[1].url).toBe('https://www.youtube.com/youtubei/v1/player?key=KEY123');
    expect(JSON.parse(calls[1].options.body)).toEqual({
      context: { client: { clientName: 'ANDROID', clientVersion: '20.10.38' } }, videoId: ID,
    });
    expect(calls[2].url).toBe('https://www.youtube.com/api/timedtext?v=x');
    expect(calls.every((c) => c.options.credentials === 'omit')).toBe(true);
  });

  it('prefers English, manual captions before auto-generated', async () => {
    const { fetchImpl, calls } = fakeYouTube({
      tracks: [
        { languageCode: 'hi', kind: 'asr', baseUrl: 'https://y/hi' },
        { languageCode: 'en', kind: 'asr', baseUrl: 'https://y/en-auto' },
        { languageCode: 'en', baseUrl: 'https://y/en-manual' },
      ],
      captionsXml: XML,
    });
    await fetchYouTubeVideo(ID, fetchImpl, 'https://www.youtube.com');
    expect(calls[2].url).toBe('https://y/en-manual');
  });

  it('falls back to the first track when there is no English', async () => {
    const { fetchImpl, calls } = fakeYouTube({ tracks: [{ languageCode: 'hi', kind: 'asr', baseUrl: 'https://y/hi' }], captionsXml: XML });
    const video = await fetchYouTubeVideo(ID, fetchImpl, 'https://www.youtube.com');
    expect(calls[2].url).toBe('https://y/hi');
    expect(video.language).toBe('hi');
  });

  it('returns the details without a transcript when there are no captions', async () => {
    const { fetchImpl } = fakeYouTube({});
    const video = await fetchYouTubeVideo(ID, fetchImpl, 'https://www.youtube.com');
    expect(video.transcript).toBeNull();
    expect(video.title).toBe('Riding');
    expect(video.error).toBe('no captions');
  });

  it('never throws: errors come back in `error`', async () => {
    const blocked = fakeYouTube({ playerStatus: 403 });
    expect((await fetchYouTubeVideo(ID, blocked.fetchImpl, 'https://www.youtube.com')).error).toBe('player API 403');
    const offline = vi.fn(async () => { throw new TypeError('Failed to fetch'); });
    const video = await fetchYouTubeVideo(ID, offline, 'https://www.youtube.com');
    expect(video.error).toBe('Failed to fetch');
    expect(video.transcript).toBeNull();
    expect((await fetchYouTubeVideo('bad', offline, 'https://www.youtube.com')).error).toBe('invalid video id');
  });

  it('does not fetch captions that need a proof-of-origin token', async () => {
    const { fetchImpl, calls } = fakeYouTube({ tracks: [{ languageCode: 'en', baseUrl: 'https://y/en&exp=xpe' }] });
    const video = await fetchYouTubeVideo(ID, fetchImpl, 'https://www.youtube.com');
    expect(calls).toHaveLength(2);
    expect(video.error).toMatch(/proof-of-origin/);
  });

  it('is self-contained, so Chrome can run it inside the YouTube tab', async () => {
    // chrome.scripting.executeScript serialises `func`; rebuild it from its source
    // with only what the tab provides, and it must still work.
    const { fetchImpl } = fakeYouTube({ tracks: [{ languageCode: 'en', baseUrl: 'https://y/en' }], captionsXml: XML });
    const rebuilt = new Function('fetch', 'location', `return (${fetchYouTubeVideo.toString()});`)(
      fetchImpl, { hostname: 'www.youtube.com', origin: 'https://www.youtube.com' },
    );
    const video = await rebuilt(ID);
    expect(video.error).toBeNull();
    expect(video.transcript).toContain('riding through Japan');
  });
});
