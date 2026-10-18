// Capture-only popup. Searching happens on the website.
// All page text is inserted with textContent; nothing is parsed as HTML.
import { WEB_APP_URL } from "./config.js";
import { domainLetter } from "./domain.js";
import { installScrollPill } from "./scroll_pill.js";

const body = document.getElementById("body");
const footer = document.getElementById("footer");
const account = document.getElementById("account");
const accountButton = document.getElementById("account-button");
const accountMenu = document.getElementById("account-menu");
const menuEmail = document.getElementById("menu-email");
const signOutButton = document.getElementById("sign-out");

/** State from the service worker (see popupState in background.js). */
let state = null;
/** Local, transient view: null | {kind: "saving"} | {kind: "saved", page} | {kind: "error", message, retry} | {kind: "confirm-auto"} | {kind: "signing-in"} */
let view = null;
let signInError = "";

function send(message) {
    return chrome.runtime.sendMessage(message);
}

// ---- tiny DOM helpers ------------------------------------------------------------

function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (value === false || value === null || value === undefined) continue;
        if (key === "class") el.className = value;
        else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
        else el.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        el.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return el;
}

/** replaceChildren, skipping null/false entries. */
function fill(el, ...children) {
    el.replaceChildren(...children.flat().filter((c) => c !== null && c !== undefined && c !== false));
}

function checkIcon() {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    for (const [k, v] of Object.entries({
        width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
        "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", class: "check",
    })) svg.setAttribute(k, v);
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", "M5 12.5l4.5 4.5L19 7.5");
    svg.append(path);
    return svg;
}

function ago(timestamp) {
    const then = typeof timestamp === "number" ? timestamp : Date.parse(timestamp);
    if (!then) return "";
    const minutes = Math.floor((Date.now() - then) / 60000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
    const days = Math.floor(hours / 24);
    if (days === 1) return "yesterday";
    if (days < 30) return `${days} days ago`;
    const months = Math.floor(days / 30);
    if (months < 12) return `${months} month${months === 1 ? "" : "s"} ago`;
    const years = Math.floor(days / 365);
    return `${years} year${years === 1 ? "" : "s"} ago`;
}

function openTab(url) {
    chrome.tabs.create({ url });
    window.close();
}

// ---- rendering -------------------------------------------------------------------

function renderSignedOut() {
    account.hidden = true;
    const signingIn = view?.kind === "signing-in";
    fill(body,
        h("div", {},
            h("h1", { class: "intro-title" }, "Sign in to start remembering"),
            h("p", { class: "intro-text" },
                "Save pages as you browse, then find them later by meaning. Your saved pages are visible only to you."),
        ),
        h("div", { class: "stack" },
            h("button", { type: "button", class: "btn btn-primary", disabled: signingIn, onclick: () => startSignIn("Google") },
                "Continue with Google"),
            h("button", { type: "button", class: "btn btn-outline", disabled: signingIn, onclick: () => startSignIn("") },
                "Continue with email"),
        ),
        signInError ? h("p", { class: "error-line", role: "alert" }, signInError) : null,
    );
    fill(footer,
        h("a", { href: `${WEB_APP_URL}/privacy`, onclick: (e) => { e.preventDefault(); openTab(`${WEB_APP_URL}/privacy`); } }, "Privacy"),
    );
}

function renderConfirmAuto() {
    fill(body,
        h("div", {},
            h("h1", { class: "intro-title" }, "Turn on auto-capture?"),
            h("p", { class: "intro-text" },
                "MemoryLane will save pages you visit so you can search them later. Banking, email, social and login pages are skipped, and you can exclude any site."),
        ),
        h("button", { type: "button", class: "btn btn-primary", onclick: () => setAutoCapture(true) }, "Turn on"),
        h("div", { class: "center" },
            h("button", { type: "button", class: "link-button", onclick: () => { view = null; render(); } }, "Cancel"),
        ),
    );
}

function pageCard(statusChildren, trailing = null) {
    const tab = state.tab || { title: "", url: "", domain: "" };
    const domain = tab.domain || "";
    return h("div", { class: "card" },
        h("div", { class: "card-top" },
            h("span", { class: "tile", "aria-hidden": "true" }, domainLetter(tab.url || domain)),
            h("div", { class: "card-text" },
                h("div", { class: "card-title" }, tab.title || tab.url || "This page"),
                domain ? h("div", { class: "card-domain" }, domain) : null,
            ),
        ),
        h("div", { class: "card-status" },
            h("span", { class: "status-text" }, ...statusChildren),
            trailing,
        ),
    );
}

const dot = (on = false) => h("span", { class: on ? "dot on" : "dot", "aria-hidden": "true" });

function mainView() {
    const primary = (label, onclick, disabled = false) =>
        h("button", { type: "button", class: "btn btn-primary", onclick, disabled }, label);
    const outline = (label, onclick, disabled = false, check = false) =>
        h("button", { type: "button", class: "btn btn-outline", onclick, disabled }, check ? checkIcon() : null, label);

    if (!state.saveable) {
        return [pageCard([dot(), "This page can't be saved"]), primary("Remember this page", null, true)];
    }
    if (view?.kind === "saving") {
        return [pageCard([dot(), "Saving…"]), primary("Saving…", null, true)];
    }
    if (view?.kind === "error") {
        return [pageCard([dot(), view.message]), primary("Try again", view.retry)];
    }
    if (state.statusError) {
        return [pageCard([dot(), state.statusError]), primary("Try again", load)];
    }
    if (view?.kind === "saved") {
        const undo = h("button", { type: "button", class: "link-button", onclick: () => undoSave(view.page.id) }, "Undo");
        return [pageCard([checkIcon(), "Saved just now"], undo), outline("Saved", null, true, true)];
    }
    if (state.autoCapture && state.excluded) {
        return [pageCard([dot(), "This site is excluded"]), outline("Allow this site", () => setExcluded(false))];
    }
    if (state.autoCapture) {
        const last = state.lastAutoSave ? `last saved ${ago(state.lastAutoSave.at)}` : "nothing saved yet";
        return [pageCard([dot(true), `Saving automatically · ${last}`]), outline("Skip this site", () => setExcluded(true))];
    }
    if (state.status?.saved) {
        const when = ago(state.status.page?.timestamp);
        const pageId = state.status.page?.id;
        const remove = pageId
            ? h("button", { type: "button", class: "link-button", onclick: () => undoSave(pageId) }, "Remove")
            : null;
        return [pageCard([checkIcon(), when ? `Saved ${when}` : "Saved"], remove), outline("Saved", null, true, true)];
    }
    return [pageCard([dot(), "Not saved yet"]), primary("Remember this page", savePage)];
}

function renderSignedIn() {
    account.hidden = false;
    const email = state.email || "";
    accountButton.textContent = (email.charAt(0) || "?").toUpperCase();
    accountButton.setAttribute("aria-label", email ? `Account: ${email}` : "Account");
    menuEmail.textContent = email;

    if (view?.kind === "confirm-auto") {
        renderConfirmAuto();
    } else {
        fill(body,
            ...mainView(),
            h("div", { class: "search-link" },
                h("a", { href: WEB_APP_URL, onclick: (e) => { e.preventDefault(); openTab(WEB_APP_URL); } },
                    "Search your saved pages ↗"),
            ),
        );
    }

    const toggle = h("button", {
        type: "button", role: "switch", class: "switch", "aria-checked": String(Boolean(state.autoCapture)),
        "aria-label": "Auto-capture", onclick: () => toggleAutoCapture(),
    });
    fill(footer,
        h("div", { class: "toggle" }, h("span", { "aria-hidden": "true" }, "Auto-capture"), toggle),
        h("a", { href: "options.html", onclick: (e) => { e.preventDefault(); chrome.runtime.openOptionsPage(); window.close(); } },
            "Excluded sites"),
    );
}

function render() {
    if (!state) return;
    if (state.signedIn) renderSignedIn();
    else renderSignedOut();
}

// ---- actions ---------------------------------------------------------------------

async function load() {
    view = view?.kind === "confirm-auto" ? view : null;
    try {
        state = await send({ type: "GET_POPUP_STATE" });
    } catch {
        state = { signedIn: false };
    }
    render();
}

async function startSignIn(provider) {
    signInError = "";
    view = { kind: "signing-in" };
    render();
    // The popup usually closes while the sign-in window is open; the service
    // worker finishes the sign-in and the next popup shows the signed-in state.
    const result = await send({ type: "SIGN_IN", provider });
    view = null;
    signInError = result?.ok ? "" : result?.error || "";
    await load();
}

async function savePage() {
    view = { kind: "saving" };
    render();
    const result = await send({ type: "SAVE_CURRENT_PAGE" });
    if (result?.ok) {
        view = result.status === "unchanged"
            ? null
            : { kind: "saved", page: result.page };
        if (result.status === "unchanged") state.status = { saved: true, page: result.page };
    } else if (result?.reason === "signed-out") {
        view = null;
        state.signedIn = false;
    } else if (result?.reason === "unsaveable") {
        view = null;
        state.saveable = false;
    } else {
        view = { kind: "error", message: result?.error || "Couldn't save this page. Try again.", retry: savePage };
    }
    render();
}

async function undoSave(id) {
    const result = await send({ type: "UNDO_SAVE", id });
    if (result?.ok) {
        view = null;
        state.status = { saved: false, page: null };
    } else if (result?.reason === "signed-out") {
        view = null;
        state.signedIn = false;
    } else {
        view = { kind: "error", message: result?.error || "Couldn't remove the page. Try again.", retry: () => undoSave(id) };
    }
    render();
}

async function toggleAutoCapture() {
    if (state.autoCapture) {
        await setAutoCapture(false);
    } else if (!state.autoCaptureConfirmed) {
        view = { kind: "confirm-auto" };
        render();
    } else {
        await setAutoCapture(true);
    }
}

async function setAutoCapture(enabled) {
    await send({ type: "SET_AUTO_CAPTURE", enabled });
    view = null;
    await load();
}

async function setExcluded(excluded) {
    await send({ type: "SET_SITE_EXCLUDED", host: state.host, excluded });
    state.excluded = excluded;
    render();
}

// ---- account menu ----------------------------------------------------------------

function setMenu(open, { focus = true } = {}) {
    accountMenu.hidden = !open;
    accountButton.setAttribute("aria-expanded", String(open));
    if (open && focus) signOutButton.focus();
    if (!open && focus) accountButton.focus();
}

accountButton.addEventListener("click", () => setMenu(accountMenu.hidden));
accountMenu.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        setMenu(false);
    }
});
document.addEventListener("click", (event) => {
    if (!accountMenu.hidden && !account.contains(event.target)) setMenu(false, { focus: false });
});
signOutButton.addEventListener("click", async () => {
    setMenu(false, { focus: false });
    await send({ type: "SIGN_OUT" });
    view = null;
    await load();
});

chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === "SESSION_CHANGED" && view?.kind !== "signing-in") load();
});

installScrollPill();
load();
