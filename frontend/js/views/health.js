/**
 * frontend/js/views/health.js
 * 
 * Source Health Observatory:
 * - Status indicator dots and health states (healthy, stale, degraded, error, disabled, never_run)
 * - 24h telemetry (success rate, average duration, item volume)
 * - On-demand single-source pipeline execution ("Run Now")
 * - Expandable log inspection tray
 * - 30-second reactive auto-refresh polling while active
 */
import { api } from "../api.js";
import { timeAgo, escapeHTML } from "../utils.js";

let healthIntervalId = null;

export function stopHealthAutoRefresh() {
  if (healthIntervalId) {
    clearInterval(healthIntervalId);
    healthIntervalId = null;
  }
}

export function renderHealthView(container) {
  stopHealthAutoRefresh();

  container.innerHTML = `
    <div class="health-view-wrapper">
      <div class="health-header">
        <div>
          <h2 class="view-title">Source Health Observatory</h2>
          <p class="view-subtitle">Live status telemetry, error tracking, and individual ingestion triggers</p>
        </div>
        <div class="health-actions">
          <div class="auto-refresh-badge">
            <span class="live-dot pulse"></span>
            Auto-refresh (30s)
          </div>
          <button class="action-btn" id="refresh-health-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
            Refresh Now
          </button>
        </div>
      </div>

      <div id="health-loading" class="analytics-loading-state">
        <div class="spinner"></div>
        <span>Gathering pipeline telemetry...</span>
      </div>

      <div id="health-content" style="display: none;">
        <!-- Status Summary Stats -->
        <div class="health-summary-tiles" id="health-summary"></div>

        <!-- Sources Table / Grid -->
        <div class="health-table-card">
          <table class="health-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Status</th>
                <th>Category</th>
                <th>Last Fetch</th>
                <th>Duration</th>
                <th>24h Success</th>
                <th>24h Items</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody id="health-sources-body"></tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  const refreshBtn = container.querySelector("#refresh-health-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => loadHealthData(container));
  }

  loadHealthData(container);

  // Set 30s auto-refresh
  healthIntervalId = setInterval(() => {
    // Only refresh if health container is currently visible
    if (container.style.display !== "none" && document.body.contains(container)) {
      loadHealthData(container, true);
    } else {
      stopHealthAutoRefresh();
    }
  }, 30000);
}

function getStatusBadge(state) {
  const map = {
    healthy: { label: "Healthy", color: "var(--positive)", bg: "rgba(52, 211, 153, 0.12)" },
    stale: { label: "Stale", color: "#facc15", bg: "rgba(250, 204, 21, 0.12)" },
    degraded: { label: "Degraded", color: "#f97316", bg: "rgba(249, 115, 22, 0.12)" },
    error: { label: "Failed", color: "var(--negative)", bg: "rgba(251, 113, 133, 0.12)" },
    disabled: { label: "Disabled", color: "#6b7280", bg: "rgba(107, 114, 128, 0.12)" },
    never_run: { label: "Never Run", color: "#94a3b8", bg: "rgba(148, 163, 184, 0.12)" }
  };
  const conf = map[state] || map.never_run;
  return `
    <span class="health-status-pill" style="color: ${conf.color}; background: ${conf.bg}; border: 1px solid ${conf.color}40">
      <span class="status-dot" style="background: ${conf.color}"></span>
      ${conf.label}
    </span>
  `;
}

async function loadHealthData(container, isSilent = false) {
  const loadingEl = container.querySelector("#health-loading");
  const contentEl = container.querySelector("#health-content");
  const summaryEl = container.querySelector("#health-summary");
  const tbodyEl = container.querySelector("#health-sources-body");

  if (!isSilent) {
    loadingEl.style.display = "flex";
    contentEl.style.display = "none";
  }

  try {
    const data = await api.getSourceHealth();
    loadingEl.style.display = "none";
    contentEl.style.display = "block";

    // Summary Cards
    const staleCount = data.sources.filter(s => s.health_state === "stale").length;
    summaryEl.innerHTML = `
      <div class="stat-tile">
        <div class="tile-label">Monitored Platforms</div>
        <div class="tile-value">${data.total_sources}</div>
        <div class="tile-sub">Integrated data pipelines</div>
      </div>
      <div class="stat-tile">
        <div class="tile-label">Healthy Sources</div>
        <div class="tile-value" style="color: var(--positive);">${data.healthy_count}</div>
        <div class="tile-sub">Ingesting within interval</div>
      </div>
      <div class="stat-tile">
        <div class="tile-label">Stale / Degraded</div>
        <div class="tile-value" style="color: #facc15;">${staleCount + data.degraded_count}</div>
        <div class="tile-sub">${staleCount} stale, ${data.degraded_count} degraded</div>
      </div>
      <div class="stat-tile">
        <div class="tile-label">Pipeline Failures</div>
        <div class="tile-value" style="color: var(--negative);">${data.error_count}</div>
        <div class="tile-sub">Requires key or network fix</div>
      </div>
    `;

    // Render Table Rows
    tbodyEl.innerHTML = data.sources.map(src => {
      const lastFetchTime = src.last_fetch?.completed_at || src.last_fetch?.started_at;
      const relativeTime = lastFetchTime ? timeAgo(lastFetchTime) : "Never";
      const durationText = src.last_fetch?.duration_ms ? `${(src.last_fetch.duration_ms / 1000).toFixed(1)}s` : "—";
      const catClass = src.source_category === "A" ? "cat-a-tag" : "cat-b-tag";
      const catLabel = src.source_category === "A" ? "Cat A (API)" : "Cat B (Signal)";

      return `
        <tr class="health-row" id="row-${src.slug}">
          <td>
            <div class="source-cell">
              <strong>${escapeHTML(src.display_name)}</strong>
              <span class="source-slug-text">${escapeHTML(src.slug)}</span>
            </div>
          </td>
          <td>${getStatusBadge(src.health_state)}</td>
          <td><span class="${catClass}">${catLabel}</span></td>
          <td>${relativeTime}</td>
          <td><span class="mono-num">${durationText}</span></td>
          <td>
            <div class="rate-cell">
              <span class="mono-num">${src.success_rate_24h}%</span>
              <div class="rate-bar-bg">
                <div class="rate-bar-fill" style="width: ${src.success_rate_24h}%; background: ${src.success_rate_24h >= 80 ? 'var(--positive)' : 'var(--negative)'}"></div>
              </div>
            </div>
          </td>
          <td><span class="mono-num">${src.items_24h}</span></td>
          <td class="text-right">
            <div class="action-btn-group">
              <button class="inspect-btn" data-slug="${src.slug}" title="Inspect Fetch Logs">Logs</button>
              <button class="run-btn" data-slug="${src.slug}" title="Run Fetch Pipeline">Run Now</button>
            </div>
          </td>
        </tr>
        <tr class="log-tray-row" id="tray-${src.slug}" style="display: none;">
          <td colspan="8">
            <div class="log-tray-content" id="tray-content-${src.slug}">
              <div class="spinner"></div> Loading logs...
            </div>
          </td>
        </tr>
      `;
    }).join("");

    // Attach Action Listeners
    tbodyEl.querySelectorAll(".run-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const slug = btn.getAttribute("data-slug");
        btn.disabled = true;
        btn.innerText = "Running...";
        try {
          await api.triggerPipelineRun(slug);
          await loadHealthData(container, true);
        } catch (err) {
          alert(`Pipeline run failed for ${slug}: ${err.message}`);
          btn.disabled = false;
          btn.innerText = "Run Now";
        }
      });
    });

    tbodyEl.querySelectorAll(".inspect-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const slug = btn.getAttribute("data-slug");
        const tray = container.querySelector(`#tray-${slug}`);
        const trayContent = container.querySelector(`#tray-content-${slug}`);

        if (tray.style.display !== "none") {
          tray.style.display = "none";
          btn.classList.remove("active");
          return;
        }

        tray.style.display = "table-row";
        btn.classList.add("active");
        trayContent.innerHTML = `<div class="spinner"></div> Loading recent logs for ${escapeHTML(slug)}...`;

        try {
          const logData = await api.getSourceLogs(slug, 15);
          if (logData.logs.length === 0) {
            trayContent.innerHTML = `<div class="empty-tray-text">No recorded fetch logs found for this source.</div>`;
            return;
          }

          trayContent.innerHTML = `
            <div class="tray-inner">
              <div class="tray-title">Recent Execution Logs (${logData.logs.length})</div>
              <div class="logs-list">
                ${logData.logs.map(l => `
                  <div class="log-entry ${l.status}">
                    <div class="log-meta">
                      <span class="log-status-tag ${l.status}">${l.status.toUpperCase()}</span>
                      <span class="log-time">${new Date(l.started_at).toLocaleString()}</span>
                      <span class="log-stat">${l.items_fetched} fetched (+${l.items_new} new)</span>
                      <span class="log-stat mono-num">${(l.duration_ms / 1000).toFixed(2)}s</span>
                    </div>
                    ${l.error_message ? `<div class="log-error-detail">⚠️ ${escapeHTML(l.error_message)}</div>` : ''}
                  </div>
                `).join("")}
              </div>
            </div>
          `;
        } catch (err) {
          trayContent.innerHTML = `<div class="error-msg">Failed to load logs: ${err.message}</div>`;
        }
      });
    });

  } catch (err) {
    console.error("Failed to load source health:", err);
    loadingEl.innerHTML = `<div class="error-msg">Failed to load health telemetry: ${err.message}</div>`;
  }
}
