// Settings: the tabs, where pages are kept (storage, size limit, overflow) and
// encrypted backups. The service worker does the work (background.js, local.js).

const $ = (id) => document.getElementById(id);
const send = (message) => chrome.runtime.sendMessage(message);
const mb = (bytes) => `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

let pendingKeyAction = null; // "backup" | "restore": what the recovery-key form is for
let hasBackup = false;

// ---- tabs (the last one opened is remembered) ----------------------------------

function showTab(name) {
    for (const tab of document.querySelectorAll(".nav button")) {
        const selected = tab.dataset.panel === name;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
    }
    for (const panel of document.querySelectorAll(".panel")) panel.hidden = panel.id !== `panel-${name}`;
    try {
        localStorage.setItem("settingsTab", name);
    } catch (_err) {
        // storage unavailable: the first tab next time
    }
}

const tabs = [...document.querySelectorAll(".nav button")];
tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => showTab(tab.dataset.panel));
    tab.addEventListener("keydown", (event) => {
        const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[event.key];
        if (!step) return;
        event.preventDefault();
        const next = tabs[(i + step + tabs.length) % tabs.length];
        showTab(next.dataset.panel);
        next.focus();
    });
});
try {
    const saved = localStorage.getItem("settingsTab");
    if (saved && $(`panel-${saved}`)) showTab(saved);
} catch (_err) {
    // keep the default tab
}

// ---- state -------------------------------------------------------------------------

function say(id, text) {
    $(id).textContent = text;
}

function setSwitch(on) {
    $("auto-backup").setAttribute("aria-checked", String(Boolean(on)));
}

async function load() {
    const state = await send({ type: "GET_STORAGE_STATE" });
    if (!state.signedIn) {
        say("usage", "Signed out");
        say("server-pages", "Sign in from the toolbar button to choose where pages are kept.");
        document.querySelectorAll("#panel-storage button, #panel-storage input, #panel-storage select, #panel-backup button")
            .forEach((el) => { el.disabled = true; });
        return;
    }
    for (const radio of document.querySelectorAll('input[name="mode"]')) radio.checked = radio.value === state.storageMode;
    $("limit").value = state.deviceLimitMb;
    $("overflow").value = state.overflow;
    setSwitch(state.autoBackup);

    if (state.device) {
        const limit = state.deviceLimitMb * 1024 * 1024;
        const share = Math.min(1, state.device.bytes / limit);
        say("usage", `${mb(state.device.bytes)} of ${state.deviceLimitMb} MB · ${state.device.pages} page${state.device.pages === 1 ? "" : "s"}`);
        $("usage-bar").style.width = `${Math.max(share > 0 ? 1 : 0, share * 100)}%`;
        $("usage-bar").classList.toggle("full", share >= 1);
    } else {
        say("usage", "Couldn't open this device's store");
    }
    say("server-pages", state.server
        ? (state.server.pages ? `${state.server.pages} more page${state.server.pages === 1 ? " is" : "s are"} on the server.` : "No pages on the server.")
        : "");

    hasBackup = Boolean(state.backup);
    $("backup-dot").classList.toggle("ok", hasBackup);
    say("backup-status", hasBackup
        ? `Backed up ${new Date(state.backup.updated_at * 1000).toLocaleString()} · ${mb(state.backup.bytes)}`
        : "No backup yet");
    $("delete-backup").hidden = !hasBackup;
    $("restore").disabled = !hasBackup;
}

// ---- storage -----------------------------------------------------------------------

async function setStorage(update) {
    await send({ type: "SET_STORAGE", ...update });
    say("storage-message", "Saved.");
    load();
}

for (const radio of document.querySelectorAll('input[name="mode"]')) {
    radio.addEventListener("change", () => setStorage({ storageMode: radio.value }));
}
$("limit").addEventListener("change", () => setStorage({ deviceLimitMb: Number($("limit").value) }));
$("overflow").addEventListener("change", () => setStorage({ overflow: $("overflow").value }));

async function longAction(button, messageId, busyText, message, done) {
    $(button).disabled = true;
    say(messageId, busyText);
    const result = await send(message);
    $(button).disabled = false;
    say(messageId, result.ok ? done(result) : result.error || "Sign in again from the toolbar button.");
    load();
    return result;
}

$("to-server").addEventListener("click", () => longAction("to-server", "storage-message", "Moving pages to the server…",
    { type: "MOVE_ALL_TO_SERVER" }, (r) => `Moved ${r.moved} page${r.moved === 1 ? "" : "s"} to the server.`));
$("to-device").addEventListener("click", () => longAction("to-device", "storage-message",
    "Bringing pages to this device (each is prepared for local search)…",
    { type: "MOVE_ALL_TO_DEVICE" }, (r) => `Moved ${r.moved} page${r.moved === 1 ? "" : "s"} to this device.`));

// ---- backups -----------------------------------------------------------------------

function askForKey(action, label) {
    pendingKeyAction = action;
    $("key-form").hidden = false;
    $("key-submit").textContent = label;
    $("key-input").focus();
}

function showKey(key) {
    $("recovery-key").textContent = key;
    $("key-box").hidden = false;
}

$("copy-key").addEventListener("click", async () => {
    try {
        await navigator.clipboard.writeText($("recovery-key").textContent);
        say("backup-message", "Recovery key copied.");
    } catch (_err) {
        say("backup-message", "Select the key and copy it.");
    }
});
$("key-saved").addEventListener("click", () => {
    $("key-box").hidden = true;
    $("recovery-key").textContent = "";
});

const backedUp = (r) => `Backed up ${r.pages} page${r.pages === 1 ? "" : "s"}.`;

$("backup-now").addEventListener("click", async () => {
    const { recoveryKey } = await chrome.storage.local.get({ recoveryKey: null });
    if (recoveryKey) {
        longAction("backup-now", "backup-message", "Encrypting and uploading…", { type: "BACKUP_NOW" }, backedUp);
        return;
    }
    if (!hasBackup) {
        // First backup: make a key and show it once.
        const { recoveryKey: fresh } = await send({ type: "NEW_RECOVERY_KEY" });
        showKey(fresh);
        const result = await longAction("backup-now", "backup-message", "Encrypting and uploading…",
            { type: "BACKUP_NOW", recoveryKey: fresh },
            (r) => `${backedUp(r)} Keep the recovery key above: it is needed to restore them.`);
        if (result.ok && $("auto-backup").getAttribute("aria-checked") === "true") {
            send({ type: "SET_AUTO_BACKUP", enabled: true, recoveryKey: fresh });
        }
        return;
    }
    askForKey("backup", "Back up");
});

$("restore").addEventListener("click", () => askForKey("restore", "Restore"));

$("key-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const recoveryKey = $("key-input").value;
    $("key-input").value = "";
    $("key-form").hidden = true;
    if (pendingKeyAction === "restore") {
        longAction("restore", "backup-message", "Downloading and restoring (pages are prepared one by one)…",
            { type: "RESTORE_BACKUP", recoveryKey }, (r) => `Restored ${r.restored} page${r.restored === 1 ? "" : "s"} to this device.`);
    } else if (pendingKeyAction === "auto") {
        send({ type: "SET_AUTO_BACKUP", enabled: true, recoveryKey }).then((r) => {
            setSwitch(r.ok);
            say("backup-message", r.ok ? "Daily backups are on." : r.error);
        });
    } else {
        longAction("backup-now", "backup-message", "Encrypting and uploading…", { type: "BACKUP_NOW", recoveryKey }, backedUp);
    }
});

$("auto-backup").addEventListener("click", async () => {
    if ($("auto-backup").getAttribute("aria-checked") === "true") {
        await send({ type: "SET_AUTO_BACKUP", enabled: false });
        setSwitch(false);
        say("backup-message", "Daily backups are off; the recovery key was removed from this browser.");
        return;
    }
    if (!hasBackup) {
        setSwitch(true);
        say("backup-message", "Press Back up now: the first backup makes your recovery key, and daily backups use it.");
        return;
    }
    say("backup-message", "Enter your recovery key to back up every day.");
    askForKey("auto", "Turn on");
});

$("delete-backup").addEventListener("click", () => longAction("delete-backup", "backup-message", "Deleting…",
    { type: "DELETE_BACKUP" }, () => "The backup was deleted."));

load();
