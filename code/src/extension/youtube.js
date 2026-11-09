// YouTube transcripts, fetched from the user's browser.
//
// YouTube blocks transcript requests from cloud servers (the MemoryLane server
// runs on AWS), but not from people's browsers. So when a YouTube video is
// saved, the extension fetches its captions, title, description and length and
// sends them with the page. The server only fetches them itself when an older
// extension sent nothing.
//
// YouTube's player API refuses requests from the extension's own origin (403),
// so fetchYouTubeVideo runs inside the YouTube tab (chrome.scripting.executeScript
// with `func`), where its requests come from youtube.com. Chrome serialises the
// function, so it must stay self-contained: no references to anything outside it.
//
// The flow mirrors youtube-transcript-api: read the watch page for the Innertube
// API key, ask the player API (as the Android client, whose caption URLs need no
// proof-of-origin token) for the caption tracks and video details, then download
// one track as timed-text XML. Only fetch and string parsing are used, so the
// same function runs in Node for tests.

/** The video id of a youtube.com/watch, youtu.be or /embed/ URL, or null. Shorts are not videos here. */
export function youtubeVideoId(url) {
    let parsed;
    try {
        parsed = new URL(url);
    } catch {
        return null;
    }
    const host = parsed.hostname.toLowerCase().replace(/^www\./, "");
    let id = null;
    if (host === "youtu.be") {
        id = parsed.pathname.split("/")[1] || null;
    } else if (host === "youtube.com" || host === "m.youtube.com") {
        if (parsed.pathname === "/watch") id = parsed.searchParams.get("v");
        else if (/^\/(embed|v|live)\//.test(parsed.pathname)) id = parsed.pathname.split("/")[2] || null;
    }
    return id && /^[A-Za-z0-9_-]{11}$/.test(id) ? id : null;
}

/**
 * Transcript and details of one video, fetched from YouTube. Self-contained (see above).
 * Never throws: on any failure the missing parts are null and `error` says why.
 * @param {string} videoId
 * @param {typeof fetch} [fetchImpl]
 * @param {string} [origin] where to send YouTube requests; in a YouTube tab, that tab's origin
 * @returns {Promise<{video_id: string, transcript: string|null, language: string|null,
 *   title: string|null, channel: string|null, description: string|null,
 *   duration_seconds: number|null, error: string|null}>}
 */
export async function fetchYouTubeVideo(videoId, fetchImpl, origin) {
    // The API's limits (backend/models.py).
    const MAX_TRANSCRIPT_CHARS = 500000;
    const MAX_DESCRIPTION_CHARS = 10000;
    const TIMEOUT_MS = 15000;
    const ENGLISH = ["en", "en-US", "en-GB"];
    const CLIENT = { client: { clientName: "ANDROID", clientVersion: "20.10.38" } };
    const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };

    const doFetch = fetchImpl || fetch;
    const here = typeof location !== "undefined" && /(^|\.)youtube\.com$/.test(location.hostname) ? location.origin : null;
    const base = origin || here || "https://www.youtube.com";

    function decodeEntities(text) {
        return text.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (match, code) => {
            if (code[0] === "#") {
                const hex = code[1] === "x" || code[1] === "X";
                const n = hex ? parseInt(code.slice(2), 16) : parseInt(code.slice(1), 10);
                return Number.isFinite(n) && n > 0 && n <= 0x10ffff ? String.fromCodePoint(n) : match;
            }
            const named = ENTITIES[code.toLowerCase()];
            return named === undefined ? match : named;
        });
    }

    function parseTimedText(xml) {
        const parts = [];
        for (const match of xml.matchAll(/<text\b[^>]*>([\s\S]*?)<\/text>/g)) {
            // Captions are entity-encoded, sometimes twice (&amp;#39;); tags inside are formatting.
            const text = decodeEntities(decodeEntities(match[1])).replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
            if (text) parts.push(text);
        }
        return parts.join(" ");
    }

    // English (manual before auto-generated), else the first manual track, else the first.
    function pickTrack(tracks) {
        if (!Array.isArray(tracks) || !tracks.length) return null;
        const manual = tracks.filter((t) => t.kind !== "asr");
        const auto = tracks.filter((t) => t.kind === "asr");
        for (const group of [manual, auto]) {
            for (const lang of ENGLISH) {
                const found = group.find((t) => t.languageCode === lang);
                if (found) return found;
            }
        }
        return manual[0] || tracks[0];
    }

    async function get(url, options) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
        try {
            const response = await doFetch(url, { ...(options || {}), signal: controller.signal, credentials: "omit" });
            return { ok: response.ok, status: response.status, body: await response.text() };
        } finally {
            clearTimeout(timer);
        }
    }

    const result = {
        video_id: videoId, transcript: null, language: null, title: null, channel: null,
        description: null, duration_seconds: null, error: null,
    };
    try {
        if (!/^[A-Za-z0-9_-]{11}$/.test(videoId || "")) throw new Error("invalid video id");
        const page = await get(`${base}/watch?v=${videoId}`);
        if (!page.ok) throw new Error(`watch page ${page.status}`);
        const key = /"INNERTUBE_API_KEY":\s*"([A-Za-z0-9_-]+)"/.exec(page.body);
        if (!key) throw new Error(page.body.includes("consent.youtube.com") ? "consent page" : "no API key on the watch page");

        const playerResponse = await get(`${base}/youtubei/v1/player?key=${key[1]}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ context: CLIENT, videoId }),
        });
        if (!playerResponse.ok) throw new Error(`player API ${playerResponse.status}`);
        const player = JSON.parse(playerResponse.body);

        const details = player.videoDetails || {};
        result.title = details.title || null;
        result.channel = details.author || null;
        result.description = details.shortDescription ? details.shortDescription.slice(0, MAX_DESCRIPTION_CHARS) : null;
        const seconds = parseInt(details.lengthSeconds, 10);
        result.duration_seconds = Number.isFinite(seconds) ? seconds : null;

        const status = player.playabilityStatus && player.playabilityStatus.status;
        if (status && status !== "OK") throw new Error(`not playable (${status})`);

        const tracks = player.captions && player.captions.playerCaptionsTracklistRenderer
            && player.captions.playerCaptionsTracklistRenderer.captionTracks;
        const track = pickTrack(tracks);
        if (!track || !track.baseUrl) {
            result.error = "no captions";
            return result;
        }
        if (track.baseUrl.includes("&exp=xpe")) throw new Error("captions need a proof-of-origin token");
        const captions = await get(track.baseUrl.replace("&fmt=srv3", ""));
        if (!captions.ok) throw new Error(`captions ${captions.status}`);
        const transcript = parseTimedText(captions.body);
        if (transcript) {
            result.transcript = transcript.slice(0, MAX_TRANSCRIPT_CHARS);
            result.language = track.languageCode || null;
        } else {
            result.error = "empty captions";
        }
    } catch (err) {
        result.error = err && err.name === "AbortError" ? "timed out" : String((err && err.message) || err).slice(0, 200);
    }
    return result;
}
