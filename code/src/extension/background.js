const API_BASE = "http://localhost:8000";

chrome.runtime.onInstalled.addListener(() => {
    console.log("MemoryLane extension installed");
});

function extractViaInjection() {
    const clone = document.body.cloneNode(true);
    ["script", "style", "nav", "footer", "aside", "header"].forEach((sel) => {
        clone.querySelectorAll(sel).forEach((el) => el.remove());
    });
    return (clone.innerText || "").trim();
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || message.type !== "SAVE_CURRENT_PAGE") {
        return;
    }

    (async () => {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (!tab || !tab.id || !tab.url || tab.url.startsWith("chrome://") || tab.url.startsWith("chrome-extension://")) {
                throw new Error("Cannot save this type of page");
            }

            let content = "";
            try {
                const extracted = await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT_CONTENT" });
                if (extracted && extracted.ok) {
                    content = extracted.content || "";
                }
            } catch (_err) {
                content = "";
            }

            if (!content.trim()) {
                const [{ result: injected }] = await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    func: extractViaInjection,
                });
                content = injected || "";
            }

            if (!content.trim()) {
                throw new Error("No text content found on page");
            }

            const response = await fetch(`${API_BASE}/memory`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    url: tab.url,
                    title: tab.title || tab.url,
                    content,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || "Failed to save memory");
            }

            const data = await response.json();
            sendResponse({ ok: true, data });
        } catch (error) {
            sendResponse({ ok: false, error: error.message || String(error) });
        }
    })();

    return true;
});
