// Cognito sign-in for the extension: authorization code + PKCE through
// chrome.identity.launchWebAuthFlow. Runs in the service worker only.
//
// Stored in chrome.storage.local as `session`:
//   { access_token, expires_at, refresh_token, email }
import { COGNITO_CLIENT_ID, COGNITO_DOMAIN } from "./config.js";

const REFRESH_MARGIN_MS = 60_000;
let refreshing = null;

function base64url(bytes) {
    let binary = "";
    for (const b of bytes) binary += String.fromCharCode(b);
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomString(byteLength) {
    return base64url(crypto.getRandomValues(new Uint8Array(byteLength)));
}

async function challengeFor(verifier) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
    return base64url(new Uint8Array(digest));
}

/** Display only: the email claim of an id token. Never used for authorization. */
function emailFromIdToken(idToken) {
    try {
        const payload = idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
        const json = decodeURIComponent(
            atob(payload).split("").map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0")).join(""),
        );
        return JSON.parse(json).email || "";
    } catch {
        return "";
    }
}

export function redirectUri() {
    return chrome.identity.getRedirectURL(); // https://<extension-id>.chromiumapp.org/
}

export async function getSession() {
    const { session } = await chrome.storage.local.get("session");
    return session && session.refresh_token ? session : null;
}

function broadcastSessionChanged() {
    chrome.runtime.sendMessage({ type: "SESSION_CHANGED" }).catch(() => {});
}

async function clearSession() {
    await chrome.storage.local.remove("session");
    broadcastSessionChanged();
}

async function tokenRequest(body) {
    const response = await fetch(`${COGNITO_DOMAIN}/oauth2/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ client_id: COGNITO_CLIENT_ID, ...body }),
    });
    if (!response.ok) throw new Error(`Token request failed (${response.status})`);
    return response.json();
}

async function storeTokens(tokens, refreshToken, fallbackEmail = "") {
    const session = {
        access_token: tokens.access_token,
        expires_at: Date.now() + tokens.expires_in * 1000,
        refresh_token: refreshToken,
        email: tokens.id_token ? emailFromIdToken(tokens.id_token) : fallbackEmail,
    };
    await chrome.storage.local.set({ session });
    broadcastSessionChanged();
    return session;
}

/** @param {string} [provider] "Google" skips Cognito's managed login page. */
export async function signIn(provider) {
    const verifier = randomString(64);
    const state = randomString(24);
    const params = new URLSearchParams({
        response_type: "code",
        client_id: COGNITO_CLIENT_ID,
        redirect_uri: redirectUri(),
        scope: "openid email profile",
        code_challenge_method: "S256",
        code_challenge: await challengeFor(verifier),
        state,
    });
    if (provider) params.set("identity_provider", provider);

    const responseUrl = await chrome.identity.launchWebAuthFlow({
        url: `${COGNITO_DOMAIN}/oauth2/authorize?${params}`,
        interactive: true,
    });
    const returned = new URL(responseUrl).searchParams;
    if (returned.get("error")) throw new Error(returned.get("error_description") || returned.get("error"));
    if (returned.get("state") !== state || !returned.get("code")) {
        throw new Error("Sign-in response did not match this request");
    }

    const tokens = await tokenRequest({
        grant_type: "authorization_code",
        code: returned.get("code"),
        redirect_uri: redirectUri(),
        code_verifier: verifier,
    });
    return storeTokens(tokens, tokens.refresh_token);
}

async function refresh(session) {
    try {
        const tokens = await tokenRequest({ grant_type: "refresh_token", refresh_token: session.refresh_token });
        return (await storeTokens(tokens, session.refresh_token, session.email)).access_token;
    } catch {
        await clearSession();
        return null;
    }
}

/**
 * A valid access token, refreshed when under 60 s remain. Returns null (and
 * clears the session) when signed out or when the refresh fails.
 */
export async function getAccessToken({ force = false } = {}) {
    const session = await getSession();
    if (!session) return null;
    if (!force && session.access_token && session.expires_at - Date.now() > REFRESH_MARGIN_MS) {
        return session.access_token;
    }
    if (!refreshing) refreshing = refresh(session).finally(() => { refreshing = null; });
    return refreshing;
}

/** Clears the stored session. Cognito's own session cookie is left alone. */
export async function signOut() {
    await clearSession();
}

export { clearSession as expireSession };
