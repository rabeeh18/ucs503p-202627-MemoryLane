// API calls with the Bearer token. A 401 refreshes the token once and retries;
// a second 401 clears the session (the popup then shows the signed-out state).
import { API_BASE } from "./config.js";
import { expireSession, getAccessToken } from "./auth.js";

export class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

function send(path, { method = "GET", body, token, bytes = false }) {
    // `bytes`: the body is binary (an encrypted backup), sent as is.
    return fetch(`${API_BASE}${path}`, {
        method,
        headers: {
            Authorization: `Bearer ${token}`,
            ...(body !== undefined ? { "Content-Type": bytes ? "application/octet-stream" : "application/json" } : {}),
        },
        body: body === undefined ? undefined : bytes ? body : JSON.stringify(body),
    });
}

export async function apiFetch(path, opts = {}) {
    let token;
    try {
        token = await getAccessToken();
    } catch (_err) {
        throw new ApiError("Couldn't reach MemoryLane. Check your connection.", 0); // still signed in
    }
    if (!token) throw new ApiError("signed-out", 401);

    let response;
    try {
        response = await send(path, { ...opts, token });
        if (response.status === 401) {
            token = await getAccessToken({ force: true });
            if (token) response = await send(path, { ...opts, token });
            if (!token || response.status === 401) {
                await expireSession();
                throw new ApiError("signed-out", 401);
            }
        }
    } catch (err) {
        if (err instanceof ApiError) throw err;
        throw new ApiError("Couldn't reach MemoryLane. Check your connection.", 0);
    }

    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new ApiError(typeof data.detail === "string" ? data.detail : "Request failed", response.status);
    }
    if (response.status === 204) return null;
    // `binary`: the response is bytes (an encrypted backup).
    return opts.binary ? new Uint8Array(await response.arrayBuffer()) : response.json();
}

/** Public endpoints (no sign-in): the search settings. */
export async function publicFetch(path) {
    const response = await fetch(`${API_BASE}${path}`);
    if (!response.ok) throw new ApiError("Request failed", response.status);
    return response.json();
}
