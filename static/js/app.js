const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const messages = document.getElementById("messages");
const apiStatus = document.getElementById("apiStatus");
const apiStatusText = document.getElementById("apiStatusText");
const traceCanvas = document.getElementById("traceCanvas");
const traceState = document.getElementById("traceState");
const traceStateText = document.getElementById("traceStateText");
const lastEvent = document.getElementById("lastEvent");
const requestId = document.getElementById("requestId");
const requestDuration = document.getElementById("requestDuration");
const quickPrompts = document.querySelectorAll(".quick-prompt");
const stages = [...document.querySelectorAll(".flow-node")];

const mcpServerNode = document.getElementById("mcpServerNode");
const mcpServerBadge = document.getElementById("mcpServerBadge");
const calculatorToolRow = document.getElementById("calculatorToolRow");
const toolDescription = document.getElementById("toolDescription");
const toolState = document.getElementById("toolState");
const toolPayload = document.getElementById("toolPayload");
const toolArguments = document.getElementById("toolArguments");
const toolResult = document.getElementById("toolResult");
const mcpNote = document.getElementById("mcpNote");
const mcpContextChip = document.getElementById("mcpContextChip");

let isSubmitting = false;
let stageTimer = null;

function makeRequestId() {
    return `req_${Date.now().toString(36).slice(-6)}`;
}

function setApiStatus(state, text) {
    apiStatus.classList.remove("online", "offline");
    if (state) apiStatus.classList.add(state);
    apiStatusText.textContent = text;
}

async function checkHealth() {
    try {
        const response = await fetch("/health", { method: "GET" });
        if (!response.ok) throw new Error("Health check failed");
        setApiStatus("online", "API Online");
    } catch (error) {
        setApiStatus("offline", "API Offline");
    }
}

function appendMessage(role, text, options = {}) {
    const article = document.createElement("article");
    article.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;
    if (options.error) article.classList.add("error-message");
    if (options.id) article.id = options.id;

    const avatar = document.createElement("div");
    avatar.className = `message-avatar${role === "user" ? " user-avatar" : ""}`;
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = role === "user" ? "YOU" : "AI";

    const body = document.createElement("div");
    body.className = "message-body";

    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = role === "user" ? "You" : "Assistant";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    if (options.typing) {
        bubble.classList.add("typing-bubble");
        bubble.setAttribute("aria-label", "Assistant is typing");
        for (let i = 0; i < 3; i += 1) {
            bubble.appendChild(document.createElement("span"));
        }
    } else {
        bubble.textContent = text;
    }

    body.append(label, bubble);

    if (role === "user") {
        article.append(body, avatar);
    } else {
        article.append(avatar, body);
    }

    messages.appendChild(article);
    messages.scrollTop = messages.scrollHeight;
    return article;
}

function resetMcpState() {
    mcpServerNode.classList.remove("connecting", "connected", "executed", "error");
    mcpServerBadge.classList.remove("connecting", "connected", "executed", "error");
    calculatorToolRow.classList.remove("executed", "not-used");

    mcpServerBadge.textContent = "Ready";
    toolState.textContent = "Ready";
    toolDescription.textContent = "Waiting for an agent tool call";

    toolPayload.hidden = true;
    toolArguments.textContent = "—";
    toolResult.textContent = "—";
}

function setMcpConnecting() {
    resetMcpState();

    mcpServerNode.classList.add("connecting");
    mcpServerBadge.classList.add("connecting");
    mcpServerBadge.textContent = "Connecting";

    toolState.textContent = "Discovering";
    toolDescription.textContent = "LangChain MCP adapter is loading tools";
}

function applyMcpTrace(trace) {
    const connected = Boolean(trace?.connected);
    const toolUsed = Boolean(trace?.tool_used);
    const availableTools = Array.isArray(trace?.available_tools)
        ? trace.available_tools
        : [];
    const toolCalls = Array.isArray(trace?.tool_calls)
        ? trace.tool_calls
        : [];

    mcpServerNode.classList.remove("connecting", "connected", "executed", "error");
    mcpServerBadge.classList.remove("connecting", "connected", "executed", "error");

    if (!connected) {
        mcpServerNode.classList.add("error");
        mcpServerBadge.classList.add("error");
        mcpServerBadge.textContent = "Failed";
        toolState.textContent = "Unavailable";
        toolDescription.textContent = "Backend did not establish an MCP connection";
        mcpContextChip.textContent = "MCP tools: unavailable";
        lastEvent.textContent = "MCP connection failed";
        return;
    }

    mcpServerNode.classList.add(toolUsed ? "executed" : "connected");
    mcpServerBadge.classList.add(toolUsed ? "executed" : "connected");
    mcpServerBadge.textContent = toolUsed ? "Executed" : "Connected";
    mcpContextChip.textContent = "MCP tools: connected";

    const hasCalculator = availableTools.includes("add_numbers");

    if (!toolUsed) {
        calculatorToolRow.classList.add("not-used");
        toolState.textContent = hasCalculator ? "Available" : "Not found";
        toolDescription.textContent = hasCalculator
            ? "Tool discovered; agent did not need it for this request"
            : "add_numbers was not returned by the MCP server";
        toolPayload.hidden = true;
        mcpNote.innerHTML =
            "<strong>Backend trace:</strong> MCP tool discovery succeeded, but the agent answered without executing a tool.";
        lastEvent.textContent = "Agent completed without an MCP tool call";
        return;
    }

    const call =
        toolCalls.find((item) => item?.name === "add_numbers") ||
        toolCalls[0];

    calculatorToolRow.classList.add("executed");
    toolState.textContent = "Executed";
    toolDescription.textContent = `Real MCP tool call: ${call?.name || "tool"}`;

    toolArguments.textContent = JSON.stringify(call?.arguments || {});
    toolResult.textContent =
        call?.result === null || call?.result === undefined
            ? "No result returned"
            : String(call.result);

    toolPayload.hidden = false;

    mcpNote.innerHTML =
        "<strong>Verified:</strong> the backend returned a real LangChain tool call/result from the MCP server.";
    lastEvent.textContent = `${call?.name || "MCP tool"} executed and result returned to the agent`;
}

function resetTrace() {
    clearInterval(stageTimer);
    stageTimer = null;
    traceCanvas.classList.remove("processing");

    stages.forEach((stage) => {
        stage.classList.remove("active", "complete", "error");
        stage.querySelector(".node-status").textContent = "Ready";
    });

    resetMcpState();
}

function setTraceState(state, text) {
    traceState.classList.remove("idle", "processing", "complete", "error");
    traceState.classList.add(state);
    traceStateText.textContent = text;
}

function startTrace(id) {
    resetTrace();
    traceCanvas.classList.add("processing");
    setTraceState("processing", "Processing");
    requestId.textContent = id;
    requestDuration.textContent = "In progress";
    lastEvent.textContent = "Request sent to POST /chat";

    let index = 0;

    const stageMessages = [
        "Browser sent the chat request",
        "FastAPI is handling the request",
        "System prompt is being loaded",
        "MCP client is discovering tools over stdio",
        "LangChain agent is deciding whether to call a tool",
    ];

    function activateStage(nextIndex) {
        stages.forEach((stage, i) => {
            stage.classList.remove("active");
            if (i < nextIndex) {
                stage.classList.add("complete");
                stage.querySelector(".node-status").textContent = "Passed";
            }
        });

        const current = stages[nextIndex];
        if (!current) return;

        current.classList.add("active");
        current.querySelector(".node-status").textContent = "Active";
        lastEvent.textContent = stageMessages[nextIndex];

        if (current.dataset.stage === "mcp-client") {
            setMcpConnecting();
        }
    }

    activateStage(0);

    stageTimer = setInterval(() => {
        if (index < stages.length - 1) {
            index += 1;
            activateStage(index);
        } else {
            clearInterval(stageTimer);
            stageTimer = null;
        }
    }, 520);
}

function completeTrace(startedAt, mcpTrace) {
    clearInterval(stageTimer);
    stageTimer = null;
    traceCanvas.classList.remove("processing");

    stages.forEach((stage) => {
        stage.classList.remove("active", "error");
        stage.classList.add("complete");
        stage.querySelector(".node-status").textContent = "Done";
    });

    const elapsed = Math.max(1, Date.now() - startedAt);
    requestDuration.textContent = `${elapsed} ms`;

    applyMcpTrace(mcpTrace);
    setTraceState("complete", mcpTrace?.tool_used ? "MCP Executed" : "Complete");
}

function failTrace(startedAt, message) {
    clearInterval(stageTimer);
    stageTimer = null;
    traceCanvas.classList.remove("processing");

    const active = stages.find((stage) => stage.classList.contains("active"));
    if (active) {
        active.classList.remove("active");
        active.classList.add("error");
        active.querySelector(".node-status").textContent = "Error";
    }

    mcpServerNode.classList.remove("connecting", "connected", "executed");
    mcpServerNode.classList.add("error");
    mcpServerBadge.classList.remove("connecting", "connected", "executed");
    mcpServerBadge.classList.add("error");
    mcpServerBadge.textContent = "Error";

    requestDuration.textContent = `${Math.max(1, Date.now() - startedAt)} ms`;
    lastEvent.textContent = message;
    setTraceState("error", "Failed");
}

function resizeTextarea() {
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 140)}px`;
}

async function submitMessage(message) {
    const cleanMessage = message.trim();
    if (!cleanMessage || isSubmitting) return;

    isSubmitting = true;
    sendButton.disabled = true;
    messageInput.disabled = true;

    appendMessage("user", cleanMessage);
    const typing = appendMessage("assistant", "", {
        typing: true,
        id: "typingMessage",
    });

    const id = makeRequestId();
    const startedAt = Date.now();

    startTrace(id);

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                message: cleanMessage,
            }),
        });

        const payload = await response.json().catch(() => ({}));

        if (!response.ok) {
            const detail =
                payload.detail ||
                `Request failed with status ${response.status}`;
            throw new Error(detail);
        }

        const answer = payload?.data?.answer;
        const mcpTrace = payload?.data?.mcp;

        if (!answer) {
            throw new Error("Backend returned an empty chat response.");
        }

        if (!mcpTrace) {
            throw new Error("Backend response is missing the MCP execution trace.");
        }

        typing.remove();
        appendMessage("assistant", answer);

        completeTrace(startedAt, mcpTrace);
        setApiStatus("online", "API Online");
    } catch (error) {
        typing.remove();

        appendMessage(
            "assistant",
            error.message || "Unable to get a response.",
            { error: true },
        );

        failTrace(
            startedAt,
            error.message || "Chat request failed",
        );

        await checkHealth();
    } finally {
        isSubmitting = false;
        sendButton.disabled = false;
        messageInput.disabled = false;
        messageInput.value = "";
        resizeTextarea();
        messageInput.focus();
    }
}

chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitMessage(messageInput.value);
});

messageInput.addEventListener("input", resizeTextarea);

messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submitMessage(messageInput.value);
    }
});

quickPrompts.forEach((button) => {
    button.addEventListener("click", () => {
        messageInput.value = button.dataset.prompt || "";
        resizeTextarea();
        messageInput.focus();
    });
});

checkHealth();
messageInput.focus();