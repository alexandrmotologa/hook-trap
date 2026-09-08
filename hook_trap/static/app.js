// hook-trap Inspector Frontend Client
(function () {
  "use strict";

  // State
  let channelId = "";
  let socket = null;
  let socketReconnectTimer = null;
  let requests = [];
  let selectedRequestId = null;
  let currentDetail = null;
  let activeMethodFilter = "ALL";
  let activeSearchTerm = "";
  let activePayloadView = "formatted"; // "formatted" | "raw"
  let publicTunnelUrl = null;
  let isViewingPublicUrl = false;

  // Sample templates for quick mock webhook sending
  const SAMPLE_TEMPLATES = {
    "stripe-payment": {
      subpath: "v1/events",
      headers: {
        "Content-Type": "application/json",
        "Stripe-Signature": "t=1690000000,v1=52571829f704d4ef01354a35f3ff5e0cffd6a2",
        "User-Agent": "Stripe/1.0 (+https://stripe.com/docs/webhooks)",
      },
      body: {
        id: "evt_3Njh4b2eZvKYlo2C0zXp0001",
        object: "event",
        api_version: "2024-06-20",
        created: 1690000000,
        type: "payment_intent.succeeded",
        data: {
          object: {
            id: "pi_3Njh4b2eZvKYlo2C0zXp0001",
            object: "payment_intent",
            amount: 4900,
            amount_received: 4900,
            currency: "usd",
            customer: "cus_ON8K3P01",
            status: "succeeded",
          },
        },
      },
    },
    "stripe-checkout": {
      subpath: "v1/events",
      headers: {
        "Content-Type": "application/json",
        "Stripe-Signature": "t=1690000000,v1=abc99887766554433221100ff",
      },
      body: {
        id: "evt_12345checkout",
        type: "checkout.session.completed",
        data: {
          object: {
            id: "cs_test_a1b2c3",
            payment_status: "paid",
            customer_email: "jane.doe@example.com",
            amount_total: 12500,
            currency: "usd",
          },
        },
      },
    },
    "github-push": {
      subpath: "github",
      headers: {
        "Content-Type": "application/json",
        "X-GitHub-Event": "push",
        "X-Hub-Signature-256": "sha256=d8e8fca2dc0f896fd7cb4cb0031ba249",
        "User-Agent": "GitHub-Hookshot/1.0",
      },
      body: {
        ref: "refs/heads/main",
        before: "6113728f27ae82c7b1a12fce9384f8f43f3b8212",
        after: "0000000000000000000000000000000000000000",
        repository: {
          id: 1296269,
          name: "Hello-World",
          full_name: "octocat/Hello-World",
          private: false,
          owner: { name: "octocat", email: "octocat@github.com" },
        },
        pusher: { name: "octocat", email: "octocat@github.com" },
      },
    },
    "github-pr": {
      subpath: "github",
      headers: {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": "sha256=ef90812347bcfae89012456",
      },
      body: {
        action: "opened",
        number: 42,
        pull_request: {
          title: "Improve webhook replay engine latency",
          user: { login: "alexandrmotologa" },
          state: "open",
        },
      },
    },
    "shopify-order": {
      subpath: "shopify",
      headers: {
        "Content-Type": "application/json",
        "X-Shopify-Topic": "orders/create",
        "X-Shopify-Hmac-Sha256": "WlhqU0Z1aFhOWHlK...",
      },
      body: {
        id: 8209829119461,
        email: "buyer@example.com",
        total_price: "189.50",
        currency: "USD",
        financial_status: "paid",
      },
    },
    custom: {
      subpath: "custom",
      headers: { "Content-Type": "application/json" },
      body: { event: "custom.notification", timestamp: new Date().toISOString() },
    },
  };

  // DOM Elements
  const els = {
    wsStatus: document.getElementById("ws-status"),
    wsStatusText: document.getElementById("ws-status-text"),
    tunnelBadge: document.getElementById("tunnel-badge"),
    tunnelUrlText: document.getElementById("tunnel-url-text"),
    urlTypeToggle: document.getElementById("url-type-toggle"),
    btnNewChannel: document.getElementById("btn-new-channel"),
    channelBadge: document.getElementById("channel-badge"),
    ingestUrlInput: document.getElementById("ingest-url-input"),
    btnCopyUrl: document.getElementById("btn-copy-url"),
    autoforwardToggle: document.getElementById("autoforward-toggle"),
    autoforwardUrl: document.getElementById("autoforward-url"),
    btnSaveAutoforward: document.getElementById("btn-save-autoforward"),
    retentionMaxInput: document.getElementById("retention-max-input"),
    searchInput: document.getElementById("search-input"),
    filterPills: document.querySelectorAll(".filter-pill"),
    requestCount: document.getElementById("request-count"),
    btnClearHistory: document.getElementById("btn-clear-history"),
    requestList: document.getElementById("request-list"),

    detailEmpty: document.getElementById("detail-empty"),
    detailContent: document.getElementById("detail-content"),
    replayTargetInput: document.getElementById("replay-target-input"),
    btnReplay: document.getElementById("btn-replay"),
    replayBtnText: document.getElementById("replay-btn-text"),
    replayFeedback: document.getElementById("replay-feedback"),
    btnCodeExport: document.getElementById("btn-code-export"),
    btnOpenDiff: document.getElementById("btn-open-diff"),

    detailMethod: document.getElementById("detail-method"),
    detailPath: document.getElementById("detail-path"),
    detailIp: document.getElementById("detail-ip"),
    detailTimestamp: document.getElementById("detail-timestamp"),
    detailSize: document.getElementById("detail-size"),
    btnCopyId: document.getElementById("btn-copy-id"),

    tabBtns: document.querySelectorAll(".tab-btn"),
    tabPanes: document.querySelectorAll(".tab-pane"),
    headersCount: document.getElementById("headers-count"),
    replaysCount: document.getElementById("replays-count"),

    btnViewFormatted: document.getElementById("btn-view-formatted"),
    btnViewRaw: document.getElementById("btn-view-raw"),
    btnCopyPayload: document.getElementById("btn-copy-payload"),
    payloadDisplay: document.getElementById("payload-display"),

    headersTbody: document.getElementById("headers-tbody"),
    btnCopyHeaders: document.getElementById("btn-copy-headers"),

    queryTbody: document.getElementById("query-tbody"),
    metaKeyValues: document.getElementById("meta-key-values"),

    replaysContainer: document.getElementById("replays-container"),

    sigProvider: document.getElementById("sig-provider"),
    sigHeaderValue: document.getElementById("sig-header-value"),
    sigSecret: document.getElementById("sig-secret"),
    btnVerifySig: document.getElementById("btn-verify-sig"),
    sigResult: document.getElementById("sig-result"),

    // Modals
    exportModal: document.getElementById("export-modal"),
    exportCodeBlock: document.getElementById("export-code-block"),
    btnCopyExport: document.getElementById("btn-copy-export"),
    exportTabBtns: document.querySelectorAll(".export-tab-btn"),

    sampleModal: document.getElementById("sample-modal"),
    btnOpenSampleModal: document.getElementById("btn-open-sample-modal"),
    btnEmptySample: document.getElementById("btn-empty-sample"),
    samplePresetSelect: document.getElementById("sample-preset-select"),
    sampleSubpathInput: document.getElementById("sample-subpath-input"),
    sampleBodyEditor: document.getElementById("sample-body-editor"),
    btnSendSample: document.getElementById("btn-send-sample"),

    diffModal: document.getElementById("diff-modal"),
    diffBaseInfo: document.getElementById("diff-base-info"),
    diffCompareSelect: document.getElementById("diff-compare-select"),
    diffOutputContainer: document.getElementById("diff-output-container"),

    collectionModal: document.getElementById("collection-modal"),
    btnOpenCollectionModal: document.getElementById("btn-open-collection-modal"),
    btnDownloadPostman: document.getElementById("btn-download-postman"),
    btnDownloadBruno: document.getElementById("btn-download-bruno"),
    btnDownloadJson: document.getElementById("btn-download-json"),

    shortcutsModal: document.getElementById("shortcuts-modal"),
    btnShortcutsModal: document.getElementById("btn-shortcuts-modal"),
  };

  // Initialize Channel & Check System Status
  async function initChannel() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    if (parts.length >= 2 && parts[0] === "c") {
      channelId = parts[1];
    } else {
      channelId = "default";
    }

    els.channelBadge.textContent = channelId;
    updateIngestUrlDisplay();

    // Check system info for public tunnel
    try {
      const res = await fetch("/api/system/status");
      if (res.ok) {
        const data = await res.json();
        if (data.public_tunnel_url) {
          publicTunnelUrl = data.public_tunnel_url;
          els.tunnelBadge.classList.remove("hidden");
          els.tunnelUrlText.textContent = "Public Tunnel Active";
          els.urlTypeToggle.classList.remove("hidden");
        }
      }
    } catch {
      // Ignored if offline
    }

    // Restore last used replay target from localStorage
    const savedReplayUrl = localStorage.getItem("hook_trap_replay_target");
    if (savedReplayUrl) {
      els.replayTargetInput.value = savedReplayUrl;
    }
  }

  function updateIngestUrlDisplay() {
    if (isViewingPublicUrl && publicTunnelUrl) {
      els.ingestUrlInput.value = `${publicTunnelUrl}/catch/${channelId}`;
      els.urlTypeToggle.textContent = "Switch to Local URL";
    } else {
      const origin = window.location.origin;
      els.ingestUrlInput.value = `${origin}/catch/${channelId}`;
      if (publicTunnelUrl) {
        els.urlTypeToggle.textContent = "Switch to Public Tunnel";
      }
    }
  }

  // Load Channel Config
  async function loadChannelConfig() {
    try {
      const res = await fetch(`/api/channels/${channelId}/config`);
      if (res.ok) {
        const data = await res.json();
        if (data.auto_forward_url) {
          els.autoforwardUrl.value = data.auto_forward_url;
          els.autoforwardToggle.checked = true;
          if (!els.replayTargetInput.value) {
            els.replayTargetInput.value = data.auto_forward_url;
          }
        }
        if (data.max_requests) {
          els.retentionMaxInput.value = data.max_requests;
        }
      }
    } catch (err) {
      console.warn("Could not fetch channel config", err);
    }
  }

  // Save Channel Config (Auto-forward & Retention)
  async function saveChannelConfig() {
    const isEnabled = els.autoforwardToggle.checked;
    const url = isEnabled ? els.autoforwardUrl.value.trim() : null;
    const maxReqs = parseInt(els.retentionMaxInput.value) || 500;

    try {
      const res = await fetch(`/api/channels/${channelId}/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auto_forward_url: url, max_requests: maxReqs }),
      });
      if (res.ok) {
        showFeedback("Channel settings saved", "success");
      }
    } catch {
      showFeedback("Failed to save settings", "error");
    }
  }

  // WebSocket lifecycle
  function connectWebSocket() {
    if (socketReconnectTimer) {
      clearTimeout(socketReconnectTimer);
      socketReconnectTimer = null;
    }

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${proto}//${window.location.host}/ws/${channelId}`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      els.wsStatus.className = "status-indicator connected";
      els.wsStatusText.textContent = "Live connected";
    };

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === "new_request") {
          handleIncomingRequest(msg.data);
        } else if (msg.event === "replay_executed") {
          handleIncomingReplay(msg.data);
        } else if (msg.event === "ping") {
          socket.send("pong");
        }
      } catch (err) {
        console.warn("WebSocket parse error", err);
      }
    };

    socket.onclose = () => {
      els.wsStatus.className = "status-indicator disconnected";
      els.wsStatusText.textContent = "Reconnecting...";
      socketReconnectTimer = setTimeout(connectWebSocket, 3000);
    };

    socket.onerror = () => {
      socket.close();
    };
  }

  // Load existing requests via REST
  async function fetchRequests() {
    try {
      let url = `/api/channels/${channelId}/requests?limit=100`;
      if (activeMethodFilter !== "ALL") {
        url += `&method=${encodeURIComponent(activeMethodFilter)}`;
      }
      if (activeSearchTerm) {
        url += `&search=${encodeURIComponent(activeSearchTerm)}`;
      }

      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        requests = data.items || [];
        renderRequestList();

        if (!selectedRequestId && requests.length > 0) {
          selectRequest(requests[0].id);
        }
      }
    } catch (err) {
      console.error("Failed to fetch requests", err);
    }
  }

  function handleIncomingRequest(summary) {
    const matchesFilter =
      activeMethodFilter === "ALL" ||
      summary.method.toUpperCase() === activeMethodFilter.toUpperCase();

    const matchesSearch =
      !activeSearchTerm ||
      summary.path.toLowerCase().includes(activeSearchTerm.toLowerCase()) ||
      JSON.stringify(summary.headers || {}).toLowerCase().includes(activeSearchTerm.toLowerCase());

    requests.unshift(summary);

    if (matchesFilter && matchesSearch) {
      renderRequestList();
    } else {
      updateRequestCount();
    }

    if (!selectedRequestId) {
      selectRequest(summary.id);
    }
  }

  function handleIncomingReplay(replayData) {
    const target = requests.find((r) => r.id === replayData.request_id);
    if (target) {
      target.replay_count = (target.replay_count || 0) + 1;
      renderRequestList();
    }

    if (selectedRequestId === replayData.request_id) {
      loadRequestDetail(selectedRequestId);
    }
  }

  function renderRequestList() {
    updateRequestCount();

    if (requests.length === 0) {
      els.requestList.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📡</div>
          <div class="empty-title">Waiting for webhooks...</div>
          <div class="empty-desc">Send an HTTP request or click "⚡ Send Sample" above.</div>
        </div>
      `;
      return;
    }

    const html = requests
      .map((req) => {
        const method = (req.method || "POST").toUpperCase();
        const methodClass = `method-${method.toLowerCase()}`;
        const isSelected = req.id === selectedRequestId ? "selected" : "";
        const formattedTime = formatTimestamp(req.timestamp);
        const sizeText = formatBytes(req.body_size || 0);

        let replayBadge = "";
        if (req.replay_count > 0) {
          replayBadge = `<span class="item-replay-badge" title="Replayed ${req.replay_count} times">⚡ ${req.replay_count}</span>`;
        }

        return `
          <div class="request-item ${isSelected}" data-id="${escapeHtml(req.id)}">
            <span class="method-tag ${methodClass}">${escapeHtml(method)}</span>
            <div class="item-info">
              <div class="item-path">${escapeHtml(req.path)}</div>
              <div class="item-meta">
                <span>${formattedTime}</span>
                <span>${sizeText}</span>
                ${replayBadge}
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    els.requestList.innerHTML = html;

    els.requestList.querySelectorAll(".request-item").forEach((item) => {
      item.addEventListener("click", () => {
        const id = item.getAttribute("data-id");
        selectRequest(id);
      });
    });
  }

  function updateRequestCount() {
    els.requestCount.textContent = `${requests.length} captured`;
  }

  async function selectRequest(id) {
    selectedRequestId = id;

    els.requestList.querySelectorAll(".request-item").forEach((item) => {
      if (item.getAttribute("data-id") === id) {
        item.classList.add("selected");
      } else {
        item.classList.remove("selected");
      }
    });

    await loadRequestDetail(id);
  }

  async function loadRequestDetail(id) {
    try {
      const res = await fetch(`/api/channels/${channelId}/requests/${id}`);
      if (!res.ok) return;

      currentDetail = await res.json();
      renderRequestDetail(currentDetail);
    } catch (err) {
      console.error("Error loading detail", err);
    }
  }

  function renderRequestDetail(detail) {
    els.detailEmpty.classList.add("hidden");
    els.detailContent.classList.remove("hidden");

    const method = (detail.method || "POST").toUpperCase();
    els.detailMethod.textContent = method;
    els.detailMethod.className = `method-tag method-${method.toLowerCase()}`;
    els.detailPath.textContent = detail.path;
    els.detailIp.textContent = detail.client_ip || "127.0.0.1";
    els.detailTimestamp.textContent = formatTimestamp(detail.timestamp);
    els.detailSize.textContent = formatBytes(
      detail.body_raw ? new Blob([detail.body_raw]).size : 0
    );

    renderPayload(detail);
    renderHeaders(detail.headers || {});
    renderQueryAndMeta(detail);
    renderReplays(detail.replays || []);
    inspectSignatures(detail.headers || {});
  }

  function renderPayload(detail) {
    const raw = detail.body_raw || "";
    if (activePayloadView === "formatted" && detail.body_json !== null && detail.body_json !== undefined) {
      els.payloadDisplay.innerHTML = syntaxHighlightJson(detail.body_json);
    } else {
      els.payloadDisplay.textContent = raw || "(Empty Body)";
    }
  }

  function renderHeaders(headers) {
    const entries = Object.entries(headers);
    els.headersCount.textContent = entries.length;

    if (entries.length === 0) {
      els.headersTbody.innerHTML = `<tr><td colspan="2" style="color: var(--text-muted); text-align: center;">No headers recorded</td></tr>`;
      return;
    }

    const html = entries
      .map(([k, v]) => {
        const lower = k.toLowerCase();
        let sigBadge = "";
        if (lower.includes("signature") || lower.includes("hmac") || lower.includes("svix")) {
          sigBadge = `<span class="sig-badge">Signature</span>`;
        }
        return `
          <tr>
            <td><strong>${escapeHtml(k)}</strong>${sigBadge}</td>
            <td>${escapeHtml(v)}</td>
          </tr>
        `;
      })
      .join("");

    els.headersTbody.innerHTML = html;
  }

  function renderQueryAndMeta(detail) {
    const queryParams = Object.entries(detail.query_params || {});
    if (queryParams.length === 0) {
      els.queryTbody.innerHTML = `<tr><td colspan="2" style="color: var(--text-muted); text-align: center;">No query parameters</td></tr>`;
    } else {
      els.queryTbody.innerHTML = queryParams
        .map(
          ([k, v]) => `
          <tr>
            <td><strong>${escapeHtml(k)}</strong></td>
            <td>${escapeHtml(String(v))}</td>
          </tr>
        `
        )
        .join("");
    }

    els.metaKeyValues.innerHTML = `
      <div style="font-size: 0.8rem; display: flex; flex-direction: column; gap: 6px;">
        <div><strong style="color: var(--text-secondary);">Request UUID:</strong> <code>${escapeHtml(detail.id)}</code></div>
        <div><strong style="color: var(--text-secondary);">Content-Type:</strong> <code>${escapeHtml(detail.content_type || "None")}</code></div>
        <div><strong style="color: var(--text-secondary);">Client IP:</strong> <code>${escapeHtml(detail.client_ip || "Unknown")}</code></div>
        <div><strong style="color: var(--text-secondary);">Total Replays:</strong> ${detail.replay_count || 0}</div>
      </div>
    `;
  }

  function renderReplays(replays) {
    els.replaysCount.textContent = replays.length;

    if (replays.length === 0) {
      els.replaysContainer.innerHTML = `
        <div class="empty-state" style="padding: 24px;">
          <div class="empty-title">No replays recorded yet</div>
          <div class="empty-desc">Click the "⚡ Replay" button above to forward this webhook to your local server.</div>
        </div>
      `;
      return;
    }

    const html = replays
      .map((log) => {
        const isSuccess = log.status_code && log.status_code >= 200 && log.status_code < 300;
        const statusClass = isSuccess
          ? "replay-status-2xx"
          : log.status_code
          ? "replay-status-4xx"
          : "replay-status-err";
        const statusText = log.status_code ? `${log.status_code} OK` : "FAILED";

        return `
          <div class="replay-card">
            <div class="replay-header">
              <div>
                <span class="replay-status-pill ${statusClass}">${statusText}</span>
                <strong style="font-family: var(--font-mono); margin-left: 8px;">${escapeHtml(log.target_url)}</strong>
              </div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">
                ${log.latency_ms} ms &bull; ${formatTimestamp(log.created_at)}
              </div>
            </div>
            ${
              log.error
                ? `<div style="color: var(--color-danger); font-size: 0.8rem; margin-top: 6px;">${escapeHtml(log.error)}</div>`
                : ""
            }
            ${
              log.response_body
                ? `<div style="margin-top: 8px;">
                     <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px;">Target Response Body:</div>
                     <pre class="code-block" style="max-height: 120px; font-size: 0.75rem;">${escapeHtml(log.response_body)}</pre>
                   </div>`
                : ""
            }
          </div>
        `;
      })
      .join("");

    els.replaysContainer.innerHTML = html;
  }

  function inspectSignatures(headers) {
    let foundSig = "";
    let detectedProvider = "generic";

    for (const [k, v] of Object.entries(headers)) {
      const lk = k.toLowerCase();
      if (lk === "stripe-signature") {
        foundSig = v;
        detectedProvider = "stripe";
        break;
      } else if (lk === "x-hub-signature-256" || lk === "x-hub-signature") {
        foundSig = v;
        detectedProvider = "github";
        break;
      } else if (lk === "x-shopify-hmac-sha256") {
        foundSig = v;
        detectedProvider = "shopify";
        break;
      }
    }

    if (foundSig) {
      els.sigHeaderValue.value = foundSig;
      els.sigProvider.value = detectedProvider;
    }
  }

  // Trigger Replay
  async function triggerReplay() {
    if (!currentDetail) return;
    const targetUrl = els.replayTargetInput.value.trim();
    if (!targetUrl) {
      alert("Please enter a valid target URL to forward/replay this request to.");
      return;
    }

    localStorage.setItem("hook_trap_replay_target", targetUrl);

    els.btnReplay.disabled = true;
    els.replayBtnText.textContent = "Forwarding...";
    els.replayFeedback.className = "replay-feedback hidden";

    try {
      const res = await fetch(
        `/api/channels/${channelId}/requests/${currentDetail.id}/replay`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_url: targetUrl }),
        }
      );

      const result = await res.json();
      if (res.ok) {
        const isOk = result.status_code && result.status_code >= 200 && result.status_code < 400;
        els.replayFeedback.className = `replay-feedback ${isOk ? "success" : "error"}`;
        els.replayFeedback.textContent = isOk
          ? `✓ ${result.status_code} Response received in ${result.latency_ms} ms`
          : `✗ Error: ${result.error || `Status ${result.status_code}`} (${result.latency_ms} ms)`;
        els.replayFeedback.classList.remove("hidden");
      } else {
        els.replayFeedback.className = "replay-feedback error";
        els.replayFeedback.textContent = `✗ Replay failed: ${result.detail || "Server error"}`;
        els.replayFeedback.classList.remove("hidden");
      }
    } catch (err) {
      els.replayFeedback.className = "replay-feedback error";
      els.replayFeedback.textContent = `✗ Network error: ${err.message}`;
      els.replayFeedback.classList.remove("hidden");
    } finally {
      els.btnReplay.disabled = false;
      els.replayBtnText.textContent = "⚡ Replay";
      loadRequestDetail(currentDetail.id);
    }
  }

  // Trigger Signature Verification
  async function verifySignature() {
    if (!currentDetail) return;
    const provider = els.sigProvider.value;
    const sigHeader = els.sigHeaderValue.value.trim();
    const secret = els.sigSecret.value.trim();

    if (!sigHeader) {
      alert("Please enter or verify the signature header value.");
      return;
    }
    if (!secret) {
      alert("Please enter your webhook signing secret.");
      return;
    }

    try {
      const res = await fetch("/api/verify-signature", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: provider,
          secret: secret,
          signature_header: sigHeader,
          raw_payload: currentDetail.body_raw || "",
        }),
      });

      const result = await res.json();
      els.sigResult.classList.remove("hidden");
      if (result.valid) {
        els.sigResult.className = "sig-result-box valid";
        els.sigResult.innerHTML = `<strong>✓ VALID SIGNATURE:</strong> ${escapeHtml(
          result.message
        )}<br><small>Computed: ${escapeHtml(result.details.computed || "")}</small>`;
      } else {
        els.sigResult.className = "sig-result-box invalid";
        els.sigResult.innerHTML = `<strong>✗ INVALID SIGNATURE:</strong> ${escapeHtml(
          result.message
        )}<br><small>Expected: ${escapeHtml(result.details.computed || "")}</small>`;
      }
    } catch (err) {
      alert("Signature verification request failed: " + err.message);
    }
  }

  // Sample Webhook Generator
  function openSampleModal() {
    const key = els.samplePresetSelect.value;
    loadSamplePreset(key);
    els.sampleModal.classList.remove("hidden");
  }

  function loadSamplePreset(key) {
    const preset = SAMPLE_TEMPLATES[key] || SAMPLE_TEMPLATES["stripe-payment"];
    els.sampleSubpathInput.value = preset.subpath || "";
    els.sampleBodyEditor.value = JSON.stringify(preset.body, null, 2);
  }

  async function sendSampleWebhook() {
    const key = els.samplePresetSelect.value;
    const preset = SAMPLE_TEMPLATES[key] || {};
    const subpath = els.sampleSubpathInput.value.trim();
    const bodyStr = els.sampleBodyEditor.value.trim();

    let targetUrl = `/catch/${channelId}`;
    if (subpath) {
      targetUrl += `/${subpath.replace(/^\/+/, "")}`;
    }

    const headers = {
      "Content-Type": "application/json",
      ...(preset.headers || {}),
    };

    els.btnSendSample.disabled = true;
    els.btnSendSample.textContent = "Sending...";

    try {
      const res = await fetch(targetUrl, {
        method: "POST",
        headers: headers,
        body: bodyStr,
      });
      if (res.ok) {
        showFeedback("Sample webhook sent successfully", "success");
        els.sampleModal.classList.add("hidden");
      } else {
        showFeedback("Failed sending sample webhook", "error");
      }
    } catch (err) {
      showFeedback("Error sending sample: " + err.message, "error");
    } finally {
      els.btnSendSample.disabled = false;
      els.btnSendSample.textContent = "Send to Channel";
    }
  }

  // Payload Diff Viewer
  async function openDiffModal() {
    if (!currentDetail) return;

    els.diffBaseInfo.textContent = `${currentDetail.method} ${currentDetail.path} (${currentDetail.id.slice(0, 8)})`;

    // Populate compare dropdown with other requests
    const otherRequests = requests.filter((r) => r.id !== currentDetail.id);
    if (otherRequests.length === 0) {
      alert("At least two captured requests are needed to perform a comparison.");
      return;
    }

    els.diffCompareSelect.innerHTML = otherRequests
      .map(
        (r) =>
          `<option value="${escapeHtml(r.id)}">${r.method} ${escapeHtml(r.path)} - ${formatTimestamp(
            r.timestamp
          )} (${r.id.slice(0, 8)})</option>`
      )
      .join("");

    els.diffModal.classList.remove("hidden");
    await renderDiffComparison(otherRequests[0].id);
  }

  async function renderDiffComparison(compareId) {
    els.diffOutputContainer.innerHTML = `<div style="color: var(--text-muted); text-align: center;">Computing diff...</div>`;

    try {
      const res = await fetch(`/api/channels/${channelId}/requests/${compareId}`);
      if (!res.ok) return;
      const compareDetail = await res.json();

      const baseText = JSON.stringify(currentDetail.body_json || currentDetail.body_raw || {}, null, 2);
      const compareText = JSON.stringify(compareDetail.body_json || compareDetail.body_raw || {}, null, 2);

      const diffHtml = computeSimpleDiff(baseText, compareText);
      els.diffOutputContainer.innerHTML = diffHtml;
    } catch (err) {
      els.diffOutputContainer.innerHTML = `<div style="color: var(--color-danger);">Diff failed: ${escapeHtml(
        err.message
      )}</div>`;
    }
  }

  function computeSimpleDiff(text1, text2) {
    const lines1 = text1.split("\n");
    const lines2 = text2.split("\n");

    let html = "";
    const maxLen = Math.max(lines1.length, lines2.length);

    for (let i = 0; i < maxLen; i++) {
      const l1 = lines1[i];
      const l2 = lines2[i];

      if (l1 === undefined) {
        html += `<div class="diff-row diff-add"><span class="diff-sign">+</span>${escapeHtml(l2)}</div>`;
      } else if (l2 === undefined) {
        html += `<div class="diff-row diff-del"><span class="diff-sign">-</span>${escapeHtml(l1)}</div>`;
      } else if (l1 === l2) {
        html += `<div class="diff-row diff-same"><span class="diff-sign">&nbsp;</span>${escapeHtml(l1)}</div>`;
      } else {
        html += `<div class="diff-row diff-del"><span class="diff-sign">-</span>${escapeHtml(l1)}</div>`;
        html += `<div class="diff-row diff-add"><span class="diff-sign">+</span>${escapeHtml(l2)}</div>`;
      }
    }

    return html || `<div style="color: var(--text-muted);">Payloads are identical.</div>`;
  }

  // Clear Channel History
  async function clearHistory() {
    if (!confirm("Are you sure you want to clear all captured requests for this channel?")) {
      return;
    }

    try {
      const res = await fetch(`/api/channels/${channelId}/requests`, {
        method: "DELETE",
      });
      if (res.ok) {
        requests = [];
        selectedRequestId = null;
        currentDetail = null;
        renderRequestList();
        els.detailEmpty.classList.remove("hidden");
        els.detailContent.classList.add("hidden");
      }
    } catch (err) {
      alert("Failed to clear history: " + err.message);
    }
  }

  // Code Export Generators
  let currentExportLang = "curl";

  function openExportModal() {
    if (!currentDetail) return;
    updateExportCode(currentExportLang);
    els.exportModal.classList.remove("hidden");
  }

  function updateExportCode(lang) {
    currentExportLang = lang;
    els.exportTabBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-lang") === lang);
    });

    const targetUrl = els.replayTargetInput.value.trim() || `http://localhost:3000/api/webhook`;
    const method = (currentDetail.method || "POST").toUpperCase();
    const headers = currentDetail.headers || {};
    const body = currentDetail.body_raw || "";

    let code = "";

    if (lang === "curl") {
      code = `curl -X ${method} "${targetUrl}"`;
      for (const [k, v] of Object.entries(headers)) {
        if (!["host", "content-length"].includes(k.toLowerCase())) {
          code += ` \\\n  -H "${k}: ${v.replace(/"/g, '\\"')}"`;
        }
      }
      if (body && !["GET", "HEAD"].includes(method)) {
        code += ` \\\n  --data '${body.replace(/'/g, "'\\''")}'`;
      }
    } else if (lang === "python") {
      const headerDict = {};
      for (const [k, v] of Object.entries(headers)) {
        if (!["host", "content-length"].includes(k.toLowerCase())) {
          headerDict[k] = v;
        }
      }
      code = `import httpx

url = "${targetUrl}"
headers = ${JSON.stringify(headerDict, null, 4)}
data = """${body.replace(/"""/g, '\\"\\"\\"')}"""

response = httpx.${method.toLowerCase()}(url, headers=headers, content=data)
print(f"Status: {response.status_code}")
print(response.text)
`;
    } else if (lang === "javascript") {
      const headerDict = {};
      for (const [k, v] of Object.entries(headers)) {
        if (!["host", "content-length"].includes(k.toLowerCase())) {
          headerDict[k] = v;
        }
      }
      code = `fetch("${targetUrl}", {
  method: "${method}",
  headers: ${JSON.stringify(headerDict, null, 4)},
  body: ${["GET", "HEAD"].includes(method) ? "undefined" : JSON.stringify(body)}
})
  .then(res => res.text())
  .then(text => console.log(text))
  .catch(err => console.error(err));
`;
    }

    els.exportCodeBlock.textContent = code;
  }

  // Keyboard navigation & shortcuts
  function setupKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
      // If typing inside an input, textarea, or select, ignore shortcut unless Escape
      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
      const isInputActive = ["input", "textarea", "select"].includes(activeTag);

      if (e.key === "Escape") {
        closeAllModals();
        return;
      }

      if (isInputActive) {
        return;
      }

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        selectNextRequest();
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        selectPrevRequest();
      } else if (e.key === "r") {
        e.preventDefault();
        triggerReplay();
      } else if (e.key === "c") {
        e.preventDefault();
        els.btnCopyUrl.click();
      } else if (e.key === "s") {
        e.preventDefault();
        openSampleModal();
      } else if (e.key === "d") {
        e.preventDefault();
        openDiffModal();
      } else if (e.key === "e") {
        e.preventDefault();
        openExportModal();
      } else if (e.key === "/") {
        e.preventDefault();
        els.searchInput.focus();
      } else if (e.key === "?") {
        e.preventDefault();
        els.shortcutsModal.classList.remove("hidden");
      }
    });
  }

  function selectNextRequest() {
    if (requests.length === 0) return;
    const currentIndex = requests.findIndex((r) => r.id === selectedRequestId);
    if (currentIndex < requests.length - 1) {
      selectRequest(requests[currentIndex + 1].id);
    }
  }

  function selectPrevRequest() {
    if (requests.length === 0) return;
    const currentIndex = requests.findIndex((r) => r.id === selectedRequestId);
    if (currentIndex > 0) {
      selectRequest(requests[currentIndex - 1].id);
    }
  }

  function closeAllModals() {
    document.querySelectorAll(".modal-backdrop").forEach((m) => m.classList.add("hidden"));
  }

  // Utilities
  function formatTimestamp(isoStr) {
    if (!isoStr) return "-";
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch {
      return isoStr;
    }
  }

  function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function syntaxHighlightJson(json) {
    if (typeof json !== "string") {
      json = JSON.stringify(json, null, 2);
    }
    json = escapeHtml(json);
    return json.replace(
      /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
      function (match) {
        let cls = "json-number";
        if (/^"/.test(match)) {
          if (/:$/.test(match)) {
            cls = "json-key";
          } else {
            cls = "json-string";
          }
        } else if (/true|false/.test(match)) {
          cls = "json-boolean";
        } else if (/null/.test(match)) {
          cls = "json-null";
        }
        return '<span class="' + cls + '">' + match + "</span>";
      }
    );
  }

  function showFeedback(msg, type) {
    const feedback = document.createElement("div");
    feedback.className = `replay-feedback ${type}`;
    feedback.style.position = "fixed";
    feedback.style.bottom = "20px";
    feedback.style.right = "20px";
    feedback.style.zIndex = "9999";
    feedback.textContent = msg;
    document.body.appendChild(feedback);
    setTimeout(() => feedback.remove(), 2500);
  }

  // Event Listeners Setup
  function setupEvents() {
    // Copy Ingest URL
    els.btnCopyUrl.addEventListener("click", () => {
      navigator.clipboard.writeText(els.ingestUrlInput.value).then(() => {
        const originalText = els.btnCopyUrl.textContent;
        els.btnCopyUrl.textContent = "Copied!";
        setTimeout(() => (els.btnCopyUrl.textContent = originalText), 1500);
      });
    });

    // Public / Local URL Toggle
    els.urlTypeToggle.addEventListener("click", () => {
      isViewingPublicUrl = !isViewingPublicUrl;
      updateIngestUrlDisplay();
    });

    // New Channel
    els.btnNewChannel.addEventListener("click", () => {
      const randHex = Math.random().toString(16).substring(2, 10);
      window.location.href = `/c/${randHex}`;
    });

    // Auto-forward & retention save
    els.btnSaveAutoforward.addEventListener("click", saveChannelConfig);
    els.autoforwardToggle.addEventListener("change", saveChannelConfig);
    els.retentionMaxInput.addEventListener("change", saveChannelConfig);

    // Search and filters
    els.searchInput.addEventListener("input", (e) => {
      activeSearchTerm = e.target.value;
      fetchRequests();
    });

    els.filterPills.forEach((pill) => {
      pill.addEventListener("click", () => {
        els.filterPills.forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        activeMethodFilter = pill.getAttribute("data-method");
        fetchRequests();
      });
    });

    // Clear History
    els.btnClearHistory.addEventListener("click", clearHistory);

    // Replay
    els.btnReplay.addEventListener("click", triggerReplay);

    // Code Export
    els.btnCodeExport.addEventListener("click", openExportModal);
    els.exportTabBtns.forEach((btn) => {
      btn.addEventListener("click", () => updateExportCode(btn.getAttribute("data-lang")));
    });
    els.btnCopyExport.addEventListener("click", () => {
      navigator.clipboard.writeText(els.exportCodeBlock.textContent).then(() => {
        els.btnCopyExport.textContent = "Copied!";
        setTimeout(() => (els.btnCopyExport.textContent = "Copy Code"), 1500);
      });
    });

    // Sample Webhook Generator
    els.btnOpenSampleModal.addEventListener("click", openSampleModal);
    els.btnEmptySample.addEventListener("click", openSampleModal);
    els.samplePresetSelect.addEventListener("change", (e) => loadSamplePreset(e.target.value));
    els.btnSendSample.addEventListener("click", sendSampleWebhook);

    // Diff Comparison
    els.btnOpenDiff.addEventListener("click", openDiffModal);
    els.diffCompareSelect.addEventListener("change", (e) => renderDiffComparison(e.target.value));

    // Collection Export Modal
    els.btnOpenCollectionModal.addEventListener("click", () => els.collectionModal.classList.remove("hidden"));
    els.btnDownloadPostman.addEventListener("click", () => {
      window.location.href = `/api/channels/${channelId}/export?format=postman`;
    });
    els.btnDownloadBruno.addEventListener("click", () => {
      window.location.href = `/api/channels/${channelId}/export?format=bruno`;
    });
    els.btnDownloadJson.addEventListener("click", () => {
      window.location.href = `/api/channels/${channelId}/export?format=json`;
    });

    // Shortcuts Modal
    els.btnShortcutsModal.addEventListener("click", () => els.shortcutsModal.classList.remove("hidden"));

    // Generic Modal Close Buttons
    document.querySelectorAll("[data-close]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const modalId = btn.getAttribute("data-close");
        const modal = document.getElementById(modalId);
        if (modal) modal.classList.add("hidden");
      });
    });

    // Close modal on backdrop click
    document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) {
          backdrop.classList.add("hidden");
        }
      });
    });

    // Copy Request ID
    els.btnCopyId.addEventListener("click", () => {
      if (currentDetail) {
        navigator.clipboard.writeText(currentDetail.id).then(() => {
          els.btnCopyId.textContent = "Copied!";
          setTimeout(() => (els.btnCopyId.textContent = "Copy ID"), 1500);
        });
      }
    });

    // Tabs switching
    els.tabBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        els.tabBtns.forEach((b) => b.classList.remove("active"));
        els.tabPanes.forEach((p) => p.classList.remove("active"));

        btn.classList.add("active");
        const targetId = btn.getAttribute("data-tab");
        const targetPane = document.getElementById(targetId);
        if (targetPane) targetPane.classList.add("active");
      });
    });

    // Payload view toggle
    els.btnViewFormatted.addEventListener("click", () => {
      activePayloadView = "formatted";
      els.btnViewFormatted.classList.add("active");
      els.btnViewRaw.classList.remove("active");
      if (currentDetail) renderPayload(currentDetail);
    });

    els.btnViewRaw.addEventListener("click", () => {
      activePayloadView = "raw";
      els.btnViewRaw.classList.add("active");
      els.btnViewFormatted.classList.remove("active");
      if (currentDetail) renderPayload(currentDetail);
    });

    // Copy Payload
    els.btnCopyPayload.addEventListener("click", () => {
      if (currentDetail) {
        const textToCopy = currentDetail.body_raw || "";
        navigator.clipboard.writeText(textToCopy).then(() => {
          els.btnCopyPayload.textContent = "Copied!";
          setTimeout(() => (els.btnCopyPayload.textContent = "Copy Payload"), 1500);
        });
      }
    });

    // Copy All Headers as JSON
    els.btnCopyHeaders.addEventListener("click", () => {
      if (currentDetail) {
        navigator.clipboard.writeText(JSON.stringify(currentDetail.headers || {}, null, 2)).then(() => {
          els.btnCopyHeaders.textContent = "Copied!";
          setTimeout(() => (els.btnCopyHeaders.textContent = "Copy All as JSON"), 1500);
        });
      }
    });

    // Signature Inspector button
    els.btnVerifySig.addEventListener("click", verifySignature);

    // Keyboard shortcuts
    setupKeyboardShortcuts();
  }

  // Initialization
  document.addEventListener("DOMContentLoaded", () => {
    initChannel();
    setupEvents();
    loadChannelConfig();
    fetchRequests();
    connectWebSocket();
  });
})();
