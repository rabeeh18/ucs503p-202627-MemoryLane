import { normalizeHost } from "./page_filter.js";

const form = document.getElementById("add-form");
const input = document.getElementById("site-input");
const list = document.getElementById("sites");
const empty = document.getElementById("empty");
const message = document.getElementById("message");

function render(sites) {
    list.replaceChildren(...sites.map((site) => {
        const li = document.createElement("li");
        const host = document.createElement("span");
        host.className = "host";
        host.textContent = site;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "link-button";
        remove.textContent = "Remove";
        remove.setAttribute("aria-label", `Remove ${site}`);
        remove.addEventListener("click", () => update(site, false));
        li.append(host, remove);
        return li;
    }));
    empty.hidden = sites.length > 0;
}

async function update(host, excluded) {
    const result = await chrome.runtime.sendMessage({ type: "SET_SITE_EXCLUDED", host, excluded });
    render(result?.excludedSites || []);
    message.textContent = excluded ? `${host} excluded.` : `${host} removed.`;
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const host = normalizeHost(input.value);
    if (!host) {
        message.textContent = "Enter a site like example.com.";
        input.focus();
        return;
    }
    input.value = "";
    await update(host, true);
    input.focus();
});

chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && changes.excludedSites) render(changes.excludedSites.newValue || []);
});

chrome.storage.local.get({ excludedSites: [] }).then(({ excludedSites }) => render(excludedSites));
