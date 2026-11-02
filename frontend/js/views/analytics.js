/**
 * frontend/js/views/analytics.js
 * 
 * Analytics Dashboard view utilizing Chart.js (v4.4.1) for high-performance,
 * dark-theme responsive visualizations of trending social intelligence:
 * - 4 Key Performance Indicator stat tiles
 * - Category Distribution (Donut)
 * - Platform Volume Share (Horizontal Bar)
 * - Provenance Ratio: Cat A vs Cat B (Doughnut)
 * - Top Indian Locations (Bar Chart)
 * - 24-Hour Hourly Ingestion Volume (Line Chart)
 */
import { api } from "../api.js";

let currentRecency = "24h";
const chartInstances = {};

function destroyCharts() {
  Object.keys(chartInstances).forEach((key) => {
    if (chartInstances[key]) {
      chartInstances[key].destroy();
      delete chartInstances[key];
    }
  });
}

// Chart.js Dark Theme Defaults
function getChartOptions(title, isHorizontal = false) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: {
          color: "#94a3c2",
          font: { family: "Inter", size: 12 }
        }
      },
      tooltip: {
        backgroundColor: "#121729",
        titleColor: "#e7ebf5",
        bodyColor: "#94a3c2",
        borderColor: "rgba(148, 163, 184, 0.25)",
        borderWidth: 1,
        padding: 10
      }
    },
    scales: isHorizontal
      ? {
          x: {
            grid: { color: "rgba(148, 163, 184, 0.08)" },
            ticks: { color: "#94a3c2", font: { family: "JetBrains Mono", size: 11 } }
          },
          y: {
            grid: { display: false },
            ticks: { color: "#e7ebf5", font: { family: "Inter", size: 12 } }
          }
        }
      : {
          x: {
            grid: { display: false },
            ticks: { color: "#94a3c2", font: { family: "JetBrains Mono", size: 11 } }
          },
          y: {
            grid: { color: "rgba(148, 163, 184, 0.08)" },
            ticks: { color: "#94a3c2", font: { family: "JetBrains Mono", size: 11 }, precision: 0 }
          }
        }
  };
}

export async function renderAnalyticsView(container) {
  container.innerHTML = `
    <div class="analytics-view-wrapper">
      <div class="analytics-header">
        <div>
          <h2 class="view-title">Intelligence Analytics</h2>
          <p class="view-subtitle">Aggregated distribution, platform volume share, and geographic signals</p>
        </div>
        <div class="analytics-controls">
          <div class="recency-pills analytics-recency-pills" role="radiogroup" aria-label="Analytics Recency">
            <button class="recency-btn ${currentRecency === '6h' ? 'active' : ''}" data-recency="6h">Past 6h</button>
            <button class="recency-btn ${currentRecency === '12h' ? 'active' : ''}" data-recency="12h">Past 12h</button>
            <button class="recency-btn ${currentRecency === '24h' ? 'active' : ''}" data-recency="24h">Past 24h</button>
            <button class="recency-btn ${currentRecency === 'all' ? 'active' : ''}" data-recency="all">All Time</button>
          </div>
        </div>
      </div>

      <div id="analytics-loading" class="analytics-loading-state">
        <div class="spinner"></div>
        <span>Aggregating analytics data...</span>
      </div>

      <div id="analytics-content" style="display: none;">
        <!-- KPI Stat Tiles -->
        <div class="analytics-tiles-grid" id="analytics-tiles"></div>

        <!-- Empty State if 0 items -->
        <div id="analytics-empty-state" class="analytics-empty-card" style="display: none;">
          <div class="empty-icon">📊</div>
          <h3>No Data in Selected Window</h3>
          <p>No trending items match the <strong>${currentRecency}</strong> recency window. Select a broader recency period or wait for upcoming scheduled pipeline fetches.</p>
        </div>

        <!-- Charts Grid -->
        <div class="analytics-charts-grid" id="charts-wrapper">
          
          <!-- Hourly Volume Line Chart -->
          <div class="chart-card full-width">
            <div class="chart-card-header">
              <h3>24-Hour Ingestion Timeline</h3>
              <span class="chart-badge">Volume (Hourly Buckets - Effective Time)</span>
            </div>
            <div class="chart-canvas-container">
              <canvas id="chart-hourly-volume"></canvas>
            </div>
          </div>

          <!-- Category Donut -->
          <div class="chart-card">
            <div class="chart-card-header">
              <h3>Category Distribution</h3>
              <span class="chart-badge">Topic Breakdown</span>
            </div>
            <div class="chart-canvas-container">
              <canvas id="chart-category"></canvas>
            </div>
          </div>

          <!-- Platform Volume Share Horizontal Bar -->
          <div class="chart-card">
            <div class="chart-card-header">
              <h3>Platform Volume Share</h3>
              <span class="chart-badge">Items (Not Raw Engagement)</span>
            </div>
            <div class="chart-canvas-container">
              <canvas id="chart-platform"></canvas>
            </div>
          </div>

          <!-- Category A vs Category B Ratio -->
          <div class="chart-card">
            <div class="chart-card-header">
              <h3>Data Provenance Ratio</h3>
              <span class="chart-badge">Category A vs B</span>
            </div>
            <div class="chart-canvas-container">
              <canvas id="chart-provenance"></canvas>
            </div>
          </div>

          <!-- Top Indian Locations Bar Chart -->
          <div class="chart-card">
            <div class="chart-card-header">
              <h3>Top Detected Locations</h3>
              <span class="chart-badge">Regional Coverage</span>
            </div>
            <div class="chart-canvas-container">
              <canvas id="chart-locations"></canvas>
            </div>
          </div>

        </div>
      </div>
    </div>
  `;

  // Attach recency selector events
  const pillButtons = container.querySelectorAll(".analytics-recency-pills button");
  pillButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      pillButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentRecency = btn.getAttribute("data-recency");
      loadAnalyticsData(container);
    });
  });

  await loadAnalyticsData(container);
}

async function loadAnalyticsData(container) {
  const loadingEl = container.querySelector("#analytics-loading");
  const contentEl = container.querySelector("#analytics-content");
  const emptyEl = container.querySelector("#analytics-empty-state");
  const chartsWrapper = container.querySelector("#charts-wrapper");
  const tilesEl = container.querySelector("#analytics-tiles");

  loadingEl.style.display = "flex";
  contentEl.style.display = "none";
  destroyCharts();

  try {
    const data = await api.getAnalyticsOverview(currentRecency);
    loadingEl.style.display = "none";
    contentEl.style.display = "block";

    // 1. Render KPI Tiles
    const lastRunTime = data.totals.last_pipeline_run_time
      ? new Date(data.totals.last_pipeline_run_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : "Pending";

    tilesEl.innerHTML = `
      <div class="stat-tile">
        <div class="tile-label">Total Trending Items</div>
        <div class="tile-value">${data.totals.total_items.toLocaleString()}</div>
        <div class="tile-sub">Active in window (${currentRecency})</div>
      </div>
      <div class="stat-tile">
        <div class="tile-label">Active Sources</div>
        <div class="tile-value accent-cyan">${data.totals.active_sources}</div>
        <div class="tile-sub">Platforms reporting trends</div>
      </div>
      <div class="stat-tile">
        <div class="tile-label">AI Intelligence Coverage</div>
        <div class="tile-value accent-violet">${data.ai_coverage.percent}%</div>
        <div class="tile-sub">${data.ai_coverage.processed} processed / ${data.ai_coverage.pending} pending</div>
      </div>
      <div class="stat-tile">
        <div class="tile-label">Provenance Ratio</div>
        <div class="tile-value cat-b-amber">${data.source_category_ratio.A || 0}A : ${data.source_category_ratio.B || 0}B</div>
        <div class="tile-sub">Official APIs vs Derived Signals</div>
      </div>
    `;

    // 2. Check empty state
    if (data.totals.total_items === 0) {
      emptyEl.style.display = "flex";
      chartsWrapper.style.display = "none";
      return;
    }

    emptyEl.style.display = "none";
    chartsWrapper.style.display = "grid";

    if (typeof window.Chart === "undefined") {
      console.warn("Chart.js not loaded on page.");
      return;
    }

    // 3. Render Hourly Volume Line Chart
    const hourlyCanvas = container.querySelector("#chart-hourly-volume");
    if (hourlyCanvas && data.hourly_volume.length > 0) {
      chartInstances.hourly = new window.Chart(hourlyCanvas, {
        type: "line",
        data: {
          labels: data.hourly_volume.map((h) => h.hour),
          datasets: [{
            label: "Ingested Items",
            data: data.hourly_volume.map((h) => h.count),
            borderColor: "#2dd4c8",
            backgroundColor: "rgba(45, 212, 200, 0.12)",
            borderWidth: 2,
            tension: 0.35,
            fill: true,
            pointBackgroundColor: "#2dd4c8",
            pointRadius: 3
          }]
        },
        options: getChartOptions("24h Hourly Volume", false)
      });
    }

    // 4. Render Category Donut Chart
    const catCanvas = container.querySelector("#chart-category");
    if (catCanvas && data.category_breakdown.length > 0) {
      chartInstances.category = new window.Chart(catCanvas, {
        type: "doughnut",
        data: {
          labels: data.category_breakdown.map((c) => c.name),
          datasets: [{
            data: data.category_breakdown.map((c) => c.count),
            backgroundColor: data.category_breakdown.map((c) => c.color || "#8B5CF6"),
            borderWidth: 2,
            borderColor: "#0b0f1a"
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: "right",
              labels: { color: "#94a3c2", font: { family: "Inter", size: 11 }, boxWidth: 12 }
            }
          }
        }
      });
    }

    // 5. Render Platform Share (Horizontal Bar)
    const platCanvas = container.querySelector("#chart-platform");
    if (platCanvas && data.platform_share.length > 0) {
      chartInstances.platform = new window.Chart(platCanvas, {
        type: "bar",
        data: {
          labels: data.platform_share.map((p) => p.display_name),
          datasets: [{
            label: "Item Count",
            data: data.platform_share.map((p) => p.item_count),
            backgroundColor: data.platform_share.map((p) =>
              p.source_category === "A" ? "#2dd4c8" : "#f59e0b"
            ),
            borderRadius: 6
          }]
        },
        options: {
          ...getChartOptions("Platform Share", true),
          indexAxis: "y"
        }
      });
    }

    // 6. Render Provenance Doughnut
    const provCanvas = container.querySelector("#chart-provenance");
    if (provCanvas) {
      const countA = data.source_category_ratio.A || 0;
      const countB = data.source_category_ratio.B || 0;
      chartInstances.provenance = new window.Chart(provCanvas, {
        type: "doughnut",
        data: {
          labels: ["Category A (Direct APIs)", "Category B (Derived Signals)"],
          datasets: [{
            data: [countA, countB],
            backgroundColor: ["#2dd4c8", "#f59e0b"],
            borderWidth: 2,
            borderColor: "#0b0f1a"
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: "bottom",
              labels: { color: "#94a3c2", font: { family: "Inter", size: 11 }, boxWidth: 12 }
            }
          }
        }
      });
    }

    // 7. Render Top Locations Bar Chart
    const locCanvas = container.querySelector("#chart-locations");
    if (locCanvas && data.top_locations.length > 0) {
      chartInstances.locations = new window.Chart(locCanvas, {
        type: "bar",
        data: {
          labels: data.top_locations.map((l) => l.location),
          datasets: [{
            label: "Trending Stories",
            data: data.top_locations.map((l) => l.count),
            backgroundColor: "#8b7cf6",
            borderRadius: 6
          }]
        },
        options: getChartOptions("Top Locations", false)
      });
    }

  } catch (err) {
    console.error("Failed to load analytics data:", err);
    loadingEl.innerHTML = `<div class="error-msg">Failed to load analytics: ${err.message}</div>`;
  }
}
