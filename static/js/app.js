const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const messages = document.getElementById("messages");

const apiStatus = document.getElementById("apiStatus");
const apiStatusText = document.getElementById("apiStatusText");

const executionState = document.getElementById("executionState");
const addressBar = document.getElementById("addressBar");
const browserPreview = document.getElementById("browserPreview");
const browserPlaceholder = document.getElementById("browserPlaceholder");
const browserWorking = document.getElementById("browserWorking");
const refreshPreview = document.getElementById("refreshPreview");

const traceSummary = document.getElementById("traceSummary");
const duration = document.getElementById("duration");
const toolLog = document.getElementById("toolLog");

let isSending = false;
let previewPoll = null;

function setApiStatus(online) {
    apiStatus.classList.toggle("online", online);
    apiStatus.classList.toggle("offline", !online);
    apiStatusText.textContent = online ? "API Online" : "API Offline";
}

async function healthCheck() {
    try {
        const response = await fetch("/health", { cache: "no-store" });
        setApiStatus(response.ok);
    } catch {
        setApiStatus(false);
    }
}

function resizeInput() {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 120)}px`;
}

function addMessage(role, text, options = {}) {
    const article = document.createElement("article");
    article.className = `message ${role}`;
    if (options.error) article.classList.add("error");

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.textContent = role === "user" ? "YOU" : "AI";

    const body = document.createElement("div");

    const label = document.createElement("small");
    label.textContent = role === "user" ? "You" : "Assistant";

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    if (options.typing) {
        const typing = document.createElement("div");
        typing.className = "typing";

        for (let i = 0; i < 3; i += 1) {
            typing.appendChild(document.createElement("i"));
        }

        bubble.appendChild(typing);
    } else {
        bubble.textContent = text;
    }

    body.append(label, bubble);
    article.append(avatar, body);
    messages.appendChild(article);
    messages.scrollTop = messages.scrollHeight;

    return article;
}


function clearBrowserPreview() {
    browserPreview.removeAttribute("src");
    browserPreview.hidden = true;
    browserPlaceholder.hidden = false;
    addressBar.textContent = "No page open";
}

function refreshBrowserPreview() {
    const probe = new Image();

    probe.onload = () => {
        browserPreview.src = probe.src;
        browserPreview.hidden = false;
        browserPlaceholder.hidden = true;
    };

    probe.onerror = () => {
        // The first browser screenshot may not exist yet.
    };

    probe.src = `/static/browser/latest.png?t=${Date.now()}`;
}

function startPreviewPolling() {
    stopPreviewPolling();
    browserWorking.hidden = false;

    // Polling lets the UI show intermediate Selenium screenshots while one
    // multi-tool MCP request is still running.
    previewPoll = window.setInterval(refreshBrowserPreview, 450);
}

function stopPreviewPolling() {
    if (previewPoll) {
        clearInterval(previewPoll);
        previewPoll = null;
    }

    browserWorking.hidden = true;
}

function parseToolResult(result) {
    if (typeof result !== "string") {
        return result && typeof result === "object" ? result : {};
    }

    try {
        return JSON.parse(result);
    } catch {
        return {};
    }
}

function updateBrowserFromTrace(trace) {
    const calls = Array.isArray(trace?.tool_calls) ? trace.tool_calls : [];

    const closeSessionCall = calls.find(
        (call) => call?.name === "browser_close_session"
    );

    if (closeSessionCall) {
        clearBrowserPreview();
        return;
    }

    const browserCalls = calls.filter((call) =>
        String(call?.name || "").startsWith("browser_")
    );

    if (browserCalls.length === 0) {
        return;
    }

    for (let index = browserCalls.length - 1; index >= 0; index -= 1) {
        const parsed = parseToolResult(browserCalls[index]?.result);

        if (parsed?.url && parsed.url !== "about:blank") {
            addressBar.textContent = parsed.url;
            break;
        }

        if (parsed?.url === "about:blank") {
            addressBar.textContent = "No page open";
        }
    }

    refreshBrowserPreview();
}

function renderToolTrace(trace) {
    const calls = Array.isArray(trace?.tool_calls) ? trace.tool_calls : [];

    toolLog.innerHTML = "";

    if (calls.length === 0) {
        toolLog.innerHTML =
            '<div class="empty-log">MCP connected, but no tool was needed for this request.</div>';
        traceSummary.textContent = "MCP connected · no tool executed";
        return;
    }

    traceSummary.textContent = `${calls.length} real MCP tool call${calls.length === 1 ? "" : "s"} executed`;

    calls.forEach((call, index) => {
        const row = document.createElement("div");
        row.className = "tool-event";

        const number = document.createElement("div");
        number.className = "tool-number";
        number.textContent = String(index + 1).padStart(2, "0");

        const main = document.createElement("div");
        main.className = "tool-main";

        const name = document.createElement("strong");
        name.textContent = call?.name || "unknown_tool";

        const args = document.createElement("code");
        args.textContent = `args: ${JSON.stringify(call?.arguments || {})}`;

        const result = document.createElement("code");
        const resultText =
            call?.result === null || call?.result === undefined
                ? "—"
                : String(call.result);

        result.textContent =
            resultText.length > 450
                ? `result: ${resultText.slice(0, 450)}…`
                : `result: ${resultText}`;

        main.append(name, args, result);

        const badge = document.createElement("span");
        badge.className = "tool-badge";
        badge.textContent = "Executed";

        row.append(number, main, badge);
        toolLog.appendChild(row);
    });
}

function setProcessingState(active) {
    executionState.classList.toggle("active", active);
    executionState.textContent = active ? "MCP Running" : "Complete";
    browserWorking.hidden = !active;
}

async function sendMessage(rawMessage) {
    const message = rawMessage.trim();

    if (!message || isSending) return;

    isSending = true;
    sendButton.disabled = true;
    messageInput.disabled = true;

    addMessage("user", message);
    const typing = addMessage("assistant", "", { typing: true });

    toolLog.innerHTML =
        '<div class="empty-log">Waiting for backend MCP trace…</div>';

    traceSummary.textContent = "Processing request";
    duration.textContent = "Running";
    setProcessingState(true);
    startPreviewPolling();

    const startedAt = performance.now();

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message,
            }),
        });

        const payload = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(
                payload?.detail || `Request failed (${response.status})`
            );
        }

        const answer = payload?.data?.answer;
        const trace = payload?.data?.mcp;

        if (!answer) {
            throw new Error("Backend returned an empty answer.");
        }

        typing.remove();
        addMessage("assistant", answer);

        renderToolTrace(trace);
        updateBrowserFromTrace(trace);

        const elapsed = Math.round(performance.now() - startedAt);
        duration.textContent = `${elapsed} ms`;
        executionState.textContent = trace?.tool_used
            ? "MCP Executed"
            : "Complete";

        setApiStatus(true);
    } catch (error) {
        typing.remove();

        addMessage(
            "assistant",
            error?.message || "The request failed.",
            { error: true }
        );

        traceSummary.textContent = "Request failed";
        duration.textContent = `${Math.round(performance.now() - startedAt)} ms`;
        executionState.textContent = "Error";
        await healthCheck();
    } finally {
        stopPreviewPolling();

        isSending = false;
        sendButton.disabled = false;
        messageInput.disabled = false;
        messageInput.value = "";
        resizeInput();
        messageInput.focus();
    }
}

chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(messageInput.value);
});

messageInput.addEventListener("input", resizeInput);

messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage(messageInput.value);
    }
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
        messageInput.value = button.dataset.prompt || "";
        resizeInput();
        messageInput.focus();
    });
});

refreshPreview.addEventListener("click", refreshBrowserPreview);

healthCheck();
refreshBrowserPreview();
messageInput.focus();
