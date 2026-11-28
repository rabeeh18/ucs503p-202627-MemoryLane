// Options: where pages are kept, the size limit and overflow, encrypted backups.
// The service worker does the work (background.js, local.js).

const $ = (id) => document.getElementById(id);
const send = (message) => chrome.runtime.sendMessage(message);
const mb = (bytes) => `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

let pendingKeyAction = null; // "backup" | "restore": what the recovery-key form is for

function say(el, text) {
    $(el).textContent = text;
}

async function load() {
    const state = await send({ type: "GET_STORAGE_STATE" });
    if (!state.signedIn) {
        say("usage", "Sign in from the toolbar button to choose where pages are kept.");
        document.querySelectorAll("section button, section input, section select").forEach((el) => { el.disabled = true; });
        return;
    }
    for (const radio of document.querySelectorAll('input[name="mode"]')) radio.checked = radio.value === state.storageMode;
    $("limit").value = state.deviceLimitMb;
    $("overflow").value = state.overflow;
    $("auto-backup").checked = state.autoBackup;
    const device = state.device ? `${state.device.pages} pages, ${mb(state.device.bytes)} on this device` : "This device's store couldn't open";
    const server = state.server ? `${state.server.pages} on the server` : "";
    say("usage", [device, server].filter(Boolean).join(" · "));
    say("backup-status", state.backup
        ? `Last backup ${new Date(state.backup.updated_at * 1000).toLocaleString()}, ${mb(state.backup.bytes)} encrypted`
        : "No backup yet.");
}

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
}

$("to-server").addEventListener("click", () => longAction("to-server", "storage-message", "Moving pages to the server…",
    { type: "MOVE_ALL_TO_SERVER" }, (r) => `Moved ${r.moved} pages to the server.`));
$("to-device").addEventListener("click", () => longAction("to-device", "storage-message",
    "Bringing pages to this device (each is prepared for local search)…",
    { type: "MOVE_ALL_TO_DEVICE" }, (r) => `Moved ${r.moved} pages to this device.`));

// ---- backups -------------------------------------------------------------------

function askForKey(action, label) {
    pendingKeyAction = action;
    $("key-form").hidden = false;
    $("key-submit").textContent = label;
    $("key-input").focus();
}

$("backup-now").addEventListener("click", async () => {
    const { recoveryKey } = await chrome.storage.local.get({ recoveryKey: null });
    if (recoveryKey) {
        longAction("backup-now", "backup-message", "Encrypting and uploading…", { type: "BACKUP_NOW" },
            (r) => `Backed up ${r.pages} pages.`);
        return;
    }
    const status = $("backup-status").textContent;
    if (status.startsWith("No backup")) {
        // First backup: make a key and show it once.
        const { recoveryKey: fresh } = await send({ type: "NEW_RECOVERY_KEY" });
        $("recovery-key").textContent = fresh;
        $("key-box").hidden = false;
        longAction("backup-now", "backup-message", "Encrypting and uploading…", { type: "BACKUP_NOW", recoveryKey: fresh },
            (r) => `Backed up ${r.pages} pages. Keep the recovery key above: it is needed to restore them.`);
        if ($("auto-backup").checked) send({ type: "SET_AUTO_BACKUP", enabled: true, recoveryKey: fresh });
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
            { type: "RESTORE_BACKUP", recoveryKey }, (r) => `Restored ${r.restored} pages to this device.`);
    } else {
        longAction("backup-now", "backup-message", "Encrypting and uploading…", { type: "BACKUP_NOW", recoveryKey },
            (r) => `Backed up ${r.pages} pages.`);
        if ($("auto-backup").checked) send({ type: "SET_AUTO_BACKUP", enabled: true, recoveryKey });
    }
});

$("auto-backup").addEventListener("change", async () => {
    if (!$("auto-backup").checked) {
        await send({ type: "SET_AUTO_BACKUP", enabled: false });
        say("backup-message", "Automatic backups are off; the recovery key was removed from this browser.");
        return;
    }
    say("backup-message", "Enter your recovery key (or press Back up now for your first backup).");
    askForKey("backup", "Turn on");
});

$("delete-backup").addEventListener("click", () => longAction("delete-backup", "backup-message", "Deleting…",
    { type: "DELETE_BACKUP" }, () => "The backup was deleted."));

load();
