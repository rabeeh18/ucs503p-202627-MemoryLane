// Cognito managed login: authorization code + PKCE with a public client.
//
// Storage trade-off (accepted for this project): the access token lives only in
// memory, but the refresh token and the user's email are kept in localStorage
// under `ml.session` so a reload stays signed in. Anything that runs script on
// this origin could read the refresh token, so the app never renders
// user-supplied HTML ({@html} is banned) and Caddy sends a strict CSP.
import { writable } from 'svelte/store';

const DOMAIN = (import.meta.env.VITE_COGNITO_DOMAIN || '').replace(/\/$/, '');
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID || '';
const REDIRECT_URI = import.meta.env.VITE_REDIRECT_URI || `${window.location.origin}/auth/callback`;
const LOGOUT_URI = import.meta.env.VITE_LOGOUT_URI || `${window.location.origin}/`;

const SESSION_KEY = 'ml.session';
const PKCE_KEY = 'ml.pkce';
const REFRESH_MARGIN_MS = 60_000;

/** @type {{ token: string, expiresAt: number } | null} */
let access = null;
/** @type {Promise<string | null> | null} */
let refreshing = null;

function readStored() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    const value = raw ? JSON.parse(raw) : null;
    return value && value.refreshToken ? value : null;
  } catch {
    return null;
  }
}

function writeStored(value) {
  try {
    if (value) localStorage.setItem(SESSION_KEY, JSON.stringify(value));
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    /* storage unavailable: the session lasts for this tab only */
  }
}

/** Signed-in user for display ({ email }), or null. Never used for authorization. */
export const session = writable(readStored() ? { email: readStored().email || '' } : null);

function base64url(bytes) {
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function randomString(byteLength) {
  return base64url(crypto.getRandomValues(new Uint8Array(byteLength)));
}

async function challengeFor(verifier) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

/** Display only: the `email` claim from an id token. */
function emailFromIdToken(idToken) {
  try {
    const payload = idToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const json = decodeURIComponent(
      atob(payload).split('').map((c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0')).join(''),
    );
    return JSON.parse(json).email || '';
  } catch {
    return '';
  }
}

export function isConfigured() {
  return Boolean(DOMAIN && CLIENT_ID);
}

/** @param {{ provider?: string }} [opts] provider 'Google' skips the managed login page. */
export async function signIn({ provider } = {}) {
  const verifier = randomString(64); // 86 characters
  const state = randomString(24);
  sessionStorage.setItem(PKCE_KEY, JSON.stringify({ verifier, state }));

  const params = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: 'openid email profile',
    code_challenge_method: 'S256',
    code_challenge: await challengeFor(verifier),
    state,
  });
  if (provider) params.set('identity_provider', provider);
  window.location.assign(`${DOMAIN}/oauth2/authorize?${params}`);
}

async function tokenRequest(body) {
  const response = await fetch(`${DOMAIN}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: CLIENT_ID, ...body }),
  });
  if (!response.ok) throw new Error(`Token request failed (${response.status})`);
  return response.json();
}

function acceptTokens(tokens, refreshToken) {
  access = { token: tokens.access_token, expiresAt: Date.now() + tokens.expires_in * 1000 };
  const stored = readStored();
  const email = tokens.id_token ? emailFromIdToken(tokens.id_token) : stored?.email || '';
  writeStored({ refreshToken, email });
  session.set({ email });
}

/** Finish sign-in on /auth/callback. Throws if the response doesn't check out. */
export async function handleCallback() {
  const params = new URLSearchParams(window.location.search);
  const saved = JSON.parse(sessionStorage.getItem(PKCE_KEY) || 'null');
  sessionStorage.removeItem(PKCE_KEY);

  if (params.get('error')) throw new Error(params.get('error_description') || params.get('error'));
  const code = params.get('code');
  if (!code || !saved || params.get('state') !== saved.state) {
    throw new Error('Sign-in response did not match this browser session');
  }

  const tokens = await tokenRequest({
    grant_type: 'authorization_code',
    code,
    redirect_uri: REDIRECT_URI,
    code_verifier: saved.verifier,
  });
  acceptTokens(tokens, tokens.refresh_token);
}

function clearSession() {
  access = null;
  writeStored(null);
  session.set(null);
}

async function refresh() {
  const stored = readStored();
  if (!stored) {
    clearSession();
    return null;
  }
  try {
    const tokens = await tokenRequest({ grant_type: 'refresh_token', refresh_token: stored.refreshToken });
    acceptTokens(tokens, stored.refreshToken);
    return access.token;
  } catch {
    clearSession();
    return null;
  }
}

/**
 * A valid access token, refreshing when under 60 s remain. Returns null (and
 * signs out locally) if there's no session or the refresh fails.
 * @param {{ force?: boolean }} [opts]
 */
export async function getAccessToken({ force = false } = {}) {
  if (!force && access && access.expiresAt - Date.now() > REFRESH_MARGIN_MS) return access.token;
  if (!refreshing) refreshing = refresh().finally(() => { refreshing = null; });
  return refreshing;
}

export function signOut() {
  clearSession();
  const params = new URLSearchParams({ client_id: CLIENT_ID, logout_uri: LOGOUT_URI });
  window.location.assign(`${DOMAIN}/logout?${params}`);
}

/** Drop the local session without visiting Cognito (e.g. after a refused token). */
export function expireSession() {
  clearSession();
}
