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

function send(path, { method = "GET", body, token }) {
    return fetch(`${API_BASE}${path}`, {
        method,
        headers: {
            Authorization: `Bearer ${token}`,
            ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
    });
}

export async function apiFetch(path, opts = {}) {
    let token = await getAccessToken();
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
    return response.status === 204 ? null : response.json();
}
