/**
 * SocialPulse Dashboard Application
 */

import { api } from "./api.js";
import { timeAgo, formatNumber, escapeHTML, truncate, renderCommentCardHTML, renderSentimentBreakdownHTML } from "./utils.js";
import { renderAnalyticsView } from "./views/analytics.js";
import { renderHealthView, stopHealthAutoRefresh } from "./views/health.js";
import { renderTopicsView } from "./views/topics.js";

// ============================================================
// Global State
// ============================================================
const state = {
  activeSource: "all",
  sourceCategory: "all", // "all" | "A" | "B"
  recency: "24h",
  regionScope: "",
  category: "",
  sort: "recency",
  page: 1,
  perPage: 30,

  watchlist: JSON.parse(localStorage.getItem("socialpulse_watchlist") || "[]"),
  bookmarks: JSON.parse(localStorage.getItem("socialpulse_bookmarks") || "[]"),
  filterWatchlistOnly: false,
  filterSavedOnly: false,
  
  sources: [],
  categories: [],
  items: [],
  total: 0,
  totalPages: 1,
  isLoading: false
};

// ============================================================
// Momentum & Sparkline Helpers
// ============================================================
function generateSparklineSVG(points, color = "#2dd4c8") {
  if (!points || points.length < 2) return "";
  const width = 56;
  const height = 16;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = (max - min) || 1;
  const step = width / (points.length - 1);

  const coords = points.map((p, idx) => {
    const x = (idx * step).toFixed(1);
    const y = (height - 2 - ((p - min) / range) * (height - 4)).toFixed(1);
    return `${x},${y}`;
  });

  return `
    <svg class="sparkline-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" aria-hidden="true">
      <polyline fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" points="${coords.join(' ')}" />
    </svg>
  `;
}

function getMomentumBadgeHTML(momentum) {
  if (!momentum) return "";
  const map = {
    surging: { label: "Surging", icon: "🔥", color: "#f97316", bg: "rgba(249, 115, 22, 0.15)" },
    peaking: { label: "Peaking", icon: "⚡", color: "#facc15", bg: "rgba(250, 204, 21, 0.15)" },
    cooling: { label: "Cooling", icon: "📉", color: "#94a3c2", bg: "rgba(148, 163, 184, 0.15)" },
    new: { label: "New", icon: "🆕", color: "#2dd4c8", bg: "rgba(45, 212, 200, 0.15)" },
    steady: { label: "Steady", icon: "➖", color: "#8b7cf6", bg: "rgba(139, 124, 246, 0.15)" },
    tracking: { label: "Tracking…", icon: "", color: "var(--text-muted)", bg: "rgba(255, 255, 255, 0.05)" }
  };
  const conf = map[momentum.state] || map.tracking;
  const sparkline = generateSparklineSVG(momentum.points, conf.color);

  return `
    <div class="momentum-pill" style="color: ${conf.color}; background: ${conf.bg}; border: 1px solid ${conf.color}35" title="${escapeHTML(getMomentumExplanation(momentum))}">
      <span class="momentum-icon">${conf.icon}</span>
      <span class="momentum-label">${conf.label}</span>
      ${sparkline}
    </div>
  `;
}

function getMomentumExplanation(momentum) {
  if (!momentum) return "No velocity data captured yet.";
  if (momentum.state === "new") return "First observed within the last hour. Collecting baseline data.";
  if (momentum.state === "tracking") return "Momentum needs a few fetch cycles to appear.";
  if (momentum.state === "surging") {
    if (momentum.rank_delta && momentum.rank_delta >= 3) return `Climbed ${momentum.rank_delta} positions on the leaderboard.`;
    if (momentum.growth_per_hour) return `Engagement velocity is surging at +${Math.round(momentum.growth_per_hour * 100)}% per hour.`;
    return "Rapidly rising across leaderboard signals.";
  }
  if (momentum.state === "cooling") {
    if (momentum.rank_delta && momentum.rank_delta <= -3) return `Fell ${Math.abs(momentum.rank_delta)} positions on the leaderboard.`;
    if (momentum.growth_per_hour) return `Engagement cooled at ${Math.round(momentum.growth_per_hour * 100)}% per hour.`;
    return "Velocity is cooling off.";
  }
  if (momentum.state === "peaking") return "Sustaining dominant peak position near top of platform.";
  return "Stable activity consistent with previous observation cycles.";
}

// ============================================================
// Regional Scope Chip Helper
// ============================================================
function regionChipHTML(r) {
  if (!r) return "";
  if (r.scope === "global") {
    return `<span class="global-pill" title="${escapeHTML(r.basis)}">🌐 GLOBAL</span>`;
  }
  return `<span class="location-chip" title="${escapeHTML(r.basis)}">📍 ${escapeHTML(r.label)}</span>`;
}

// ============================================================
// Particle Network Background Animation
// ============================================================
function initNetworkCanvas() {
  const canvas = document.getElementById("network-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let width, height;
  let particles = [];

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  window.addEventListener("resize", resize);
  resize();

  const count = Math.min(65, Math.floor(window.innerWidth / 20));
  for (let i = 0; i < count; i++) {
    particles.push({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      radius: Math.random() * 1.5 + 0.8
    });
  }

  function animate() {
    ctx.clearRect(0, 0, width, height);

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > width) p.vx *= -1;
      if (p.y < 0 || p.y > height) p.vy *= -1;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(45, 212, 200, 0.35)";
      ctx.fill();

      for (let j = i + 1; j < particles.length; j++) {
        const p2 = particles[j];
        const dist = Math.hypot(p.x - p2.x, p.y - p2.y);
        if (dist < 130) {
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(p2.x, p2.y);
          ctx.strokeStyle = `rgba(139, 124, 246, ${0.12 * (1 - dist / 130)})`;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(animate);
  }
  animate();
}

// ============================================================
// Render Functions
// ============================================================

function renderSourceTabs() {
  const container = document.getElementById("source-tabs-container");
  if (!container) return;

  const catASources = state.sources.filter(s => s.source_category === "A");
  const catBSources = state.sources.filter(s => s.source_category === "B");
  const totalCount = state.sources.reduce((sum, s) => sum + (s.item_count || 0), 0);

  let html = `
    <button class="source-tab ${state.activeSource === "all" ? "active" : ""}" data-slug="all">
      <span>All Sources <span class="tab-count" style="font-size: 11px; opacity: 0.75; font-family: var(--font-mono, monospace);">(${totalCount})</span></span>
    </button>
  `;

  if (catASources.length > 0) {
    catASources.forEach(s => {
      const isActive = state.activeSource === s.slug ? "active" : "";
      html += `
        <button class="source-tab ${isActive}" data-slug="${escapeHTML(s.slug)}" data-cat="A">
          <img src="/static/assets/icons/${escapeHTML(s.icon_filename || 'youtube.svg')}" alt="" />
          <span>${escapeHTML(s.display_name)} <span class="tab-count" style="font-size: 11px; opacity: 0.75; font-family: var(--font-mono, monospace);">(${s.item_count || 0})</span></span>
          <span class="tab-indicator"></span>
        </button>
      `;
    });
  }

  if (catASources.length > 0 && catBSources.length > 0) {
    html += `<div class="tab-divider"></div>`;
  }

  if (catBSources.length > 0) {
    catBSources.forEach(s => {
      const isActive = state.activeSource === s.slug ? "active" : "";
      html += `
        <button class="source-tab cat-b-tab ${isActive}" data-slug="${escapeHTML(s.slug)}" data-cat="B">
          <img src="/static/assets/icons/${escapeHTML(s.icon_filename || 'google-trends.svg')}" alt="" />
          <span>${escapeHTML(s.display_name)} <span class="tab-count" style="font-size: 11px; opacity: 0.75; font-family: var(--font-mono, monospace);">(${s.item_count || 0})</span></span>
          <span class="tab-indicator" style="background: var(--cat-b-amber);"></span>
        </button>
      `;
    });
  }

  container.innerHTML = html;

  // Add click events
  container.querySelectorAll(".source-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      const slug = tab.getAttribute("data-slug");
      state.activeSource = slug;
      state.page = 1;
      renderSourceTabs();
      fetchAndRenderTrends();
    });
  });
}

function renderCategoryFilter() {
  const select = document.getElementById("category-filter");
  if (!select) return;

  let html = `<option value="">All Categories (${state.categories.length})</option>`;
  state.categories.forEach(c => {
    const selected = state.category === c.name ? "selected" : "";
    html += `<option value="${escapeHTML(c.name)}" ${selected}>${escapeHTML(c.name)}</option>`;
  });
  select.innerHTML = html;
}

function renderSkeletons() {
  const grid = document.getElementById("trends-grid");
  if (!grid) return;

  let html = "";
  for (let i = 0; i < 6; i++) {
    html += `
      <div class="skeleton-card">
        <div style="display:flex; justify-content:space-between;">
          <div class="skeleton-line" style="width:100px; height:20px;"></div>
          <div class="skeleton-line" style="width:60px; height:16px;"></div>
        </div>
        <div>
          <div class="skeleton-line" style="width:90%; height:22px; margin-bottom:8px;"></div>
          <div class="skeleton-line" style="width:70%; height:16px; margin-bottom:14px;"></div>
          <div class="skeleton-line" style="width:40%; height:24px;"></div>
        </div>
        <div class="skeleton-line" style="width:100%; height:45px;"></div>
      </div>
    `;
  }
  grid.innerHTML = html;
}

function renderTrendsGrid() {
  const grid = document.getElementById("trends-grid");
  const counter = document.getElementById("results-counter");
  if (!grid) return;

  let displayItems = [...state.items];

  // Client-side filtering for Bookmarks and Watchlist
  if (state.filterSavedOnly) {
    displayItems = displayItems.filter(item => state.bookmarks.includes(item.id));
  }

  if (state.filterWatchlistOnly) {
    displayItems = displayItems.filter(item => {
      const fullText = (item.title + " " + (item.ai_summary || "") + " " + (item.description || "")).toLowerCase();
      return state.watchlist.some(kw => fullText.includes(kw));
    });
  }

  if (displayItems.length === 0) {
    const emptyMsg = state.filterSavedOnly
      ? "You have not saved any trends yet. Click the star (☆) on any card to save it."
      : state.filterWatchlistOnly
      ? "No items match your active watchlist keywords. Add keywords or toggle off Watchlist filter."
      : `No real-time items match your selected filters (Recency: ${escapeHTML(state.recency)}, Source: ${escapeHTML(state.activeSource)}). Try switching time windows or sources.`;

    grid.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <div class="empty-icon">${state.filterSavedOnly ? "⭐" : state.filterWatchlistOnly ? "★" : "🔍"}</div>
        <h3>No Items Found</h3>
        <p>${emptyMsg}</p>
      </div>
    `;
    if (counter) counter.innerText = `0 items found`;
    return;
  }

  if (counter) {
    if (state.windowWidenedTo) {
      counter.innerHTML = `Showing ${displayItems.length} of ${state.total} items <span class="widened-badge" style="margin-left: 8px; background: rgba(245, 158, 11, 0.15); color: #f59e0b; padding: 2px 8px; border-radius: 9999px; font-size: 11px; border: 1px solid rgba(245, 158, 11, 0.3);">ℹ️ Showing last ${escapeHTML(state.windowWidenedTo)} (only ${state.originalWindowCount ?? 0} in ${escapeHTML(state.recency)})</span>`;
    } else {
      counter.innerText = `Showing ${displayItems.length} of ${state.total} items`;
    }
  }

  let html = "";
  displayItems.forEach(item => {
    const isCatA = item.source_category === "A";
    const cardClass = isCatA ? "card-cat-a" : "card-cat-b";
    const badgeClass = isCatA ? "badge-cat-a" : "badge-cat-b";
    
    // Category B badge copy
    let badgeText = item.source.source_type_label;
    if (item.source.slug === "google_trends") {
      badgeText = "SEARCH INTEREST";
    } else if (item.source.slug.includes("news")) {
      badgeText = "NEWS COVERAGE";
    }

    // CTA Link Copy
    let ctaCopy = `View on ${escapeHTML(item.source.display_name)} →`;
    if (item.source.slug === "google_trends") {
      ctaCopy = "View on Google →";
    } else if (!isCatA) {
      ctaCopy = "Read Article →";
    }

    // Metric display
    let metricHTML = "";
    if (item.engagement && item.engagement.value !== null) {
      metricHTML += `
        <span class="metric-chip">
          <span class="metric-val">${formatNumber(item.engagement.value)}</span>
          <span>${escapeHTML(item.engagement.label || "engagements")}</span>
        </span>
      `;
    }
    if (item.secondary_engagement && item.secondary_engagement.value !== null) {
      metricHTML += `
        <span class="metric-chip">
          <span class="metric-val">${formatNumber(item.secondary_engagement.value)}</span>
          <span>${escapeHTML(item.secondary_engagement.label || "comments")}</span>
        </span>
      `;
    }

    // AI Summary display
    const aiSummaryHTML = item.ai_summary ? `
      <div class="ai-summary-box">
        <div class="ai-summary-header">✨ Why It's Trending</div>
        <div class="ai-summary-text">${escapeHTML(item.ai_summary)}</div>
      </div>
    ` : "";

    let timeHTML = "";
    if (item.source.slug === "youtube" && item.published_at) {
      timeHTML = `
        <div style="text-align: right; line-height: 1.25;">
          <span class="card-time" style="color: var(--accent-cyan); font-weight: 600; font-size: 11px;">Trending ${timeAgo(item.fetched_at)}</span>
          <span class="card-time" style="display: block; font-size: 11px; opacity: 0.85;">Published ${timeAgo(item.published_at)}</span>
        </div>
      `;
    } else {
      timeHTML = `<span class="card-time">${timeAgo(item.published_at || item.fetched_at)}</span>`;
    }

    // Watchlist check
    const fullText = (item.title + " " + (item.ai_summary || "") + " " + (item.description || "")).toLowerCase();
    const isWatchlistMatched = state.watchlist.length > 0 && state.watchlist.some(kw => fullText.includes(kw));
    const isSaved = state.bookmarks.includes(item.id);
    const watchlistCardClass = isWatchlistMatched ? "watchlist-matched" : "";

    html += `
      <article class="trend-card ${cardClass} ${watchlistCardClass}" data-id="${item.id}">
        <div>
          <div class="card-header">
            <div class="source-info">
              <img class="source-icon" src="/static/assets/icons/${escapeHTML(item.source.icon_filename || 'youtube.svg')}" alt="" />
              <span class="source-name">${escapeHTML(item.source.display_name)}</span>
              <span class="${badgeClass}">${escapeHTML(badgeText)}</span>
              ${getMomentumBadgeHTML(item.momentum)}
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              ${timeHTML}
              <button class="card-star-btn ${isSaved ? 'active' : ''}" data-star-id="${item.id}" title="${isSaved ? 'Remove saved bookmark' : 'Save bookmark'}">
                ${isSaved ? '★' : '☆'}
              </button>
            </div>
          </div>

          <div class="card-body">
            <h2 class="card-title" title="${escapeHTML(item.title)}">${escapeHTML(item.title)}</h2>
            ${item.author ? `<div class="card-author">${escapeHTML(item.author)}</div>` : ""}
            ${metricHTML ? `<div class="metric-row">${metricHTML}</div>` : ""}
            ${aiSummaryHTML}
          </div>
        </div>

        <div class="card-footer">
          <div class="card-tags">
            <span class="category-pill">${escapeHTML(item.category ? item.category.name : "Trending")}</span>
            ${regionChipHTML(item.trending_region)}
            ${isWatchlistMatched ? `<span class="watchlist-card-tag">★ Watchlist</span>` : ""}
            ${item.topic_id ? `<a href="#/topics" class="topic-chip" onclick="event.stopPropagation()" title="Part of a cross-platform story">Part of a bigger story →</a>` : ""}
          </div>
          <a class="card-cta-btn" href="${escapeHTML(item.url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">
            ${ctaCopy}
          </a>
        </div>
      </article>
    `;
  });

  grid.innerHTML = html;

  // Add click handler to open drawer on card click
  grid.querySelectorAll(".trend-card").forEach(card => {
    card.addEventListener("click", () => {
      const id = parseInt(card.getAttribute("data-id"));
      openDetailDrawer(id);
    });
  });

  // Attach bookmark toggle handlers on star buttons
  grid.querySelectorAll(".card-star-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = parseInt(btn.getAttribute("data-star-id"));
      toggleBookmark(id);
    });
  });
}

function renderPagination() {
  const container = document.getElementById("pagination-controls");
  if (!container) return;

  if (state.totalPages <= 1) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = `
    <button class="page-btn" id="prev-page-btn" ${state.page <= 1 ? "disabled" : ""}>← Previous</button>
    <span class="page-info">Page ${state.page} of ${state.totalPages}</span>
    <button class="page-btn" id="next-page-btn" ${state.page >= state.totalPages ? "disabled" : ""}>Next →</button>
  `;

  const prevBtn = document.getElementById("prev-page-btn");
  const nextBtn = document.getElementById("next-page-btn");

  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      if (state.page > 1) {
        state.page--;
        fetchAndRenderTrends();
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      if (state.page < state.totalPages) {
        state.page++;
        fetchAndRenderTrends();
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    });
  }
}

// ============================================================
// Detail Drawer
// ============================================================

async function openDetailDrawer(itemId) {
  const overlay = document.getElementById("drawer-overlay");
  const drawer = document.getElementById("detail-drawer");
  const content = document.getElementById("drawer-content");
  if (!drawer || !content) return;

  content.innerHTML = `<div style="text-align:center; padding:40px; color:var(--text-muted);">Loading item details...</div>`;
  overlay.classList.add("open");
  drawer.classList.add("open");

  try {
    const [item, history, commentsData] = await Promise.all([
      api.getTrendById(itemId),
      api.getTrendHistory(itemId).catch(() => ({ snapshots: [] })),
      api.getItemComments(itemId, 10).catch(() => ({ total: 0, comments: [], sentiment_breakdown: {}, is_generated: true }))
    ]);
    const isCatA = item.source_category === "A";

    let provenanceDescription = "";
    let ctaButtonCopy = `View on ${escapeHTML(item.source.display_name)} →`;

    if (['mastodon', 'bluesky'].includes(item.source.slug)) {
      provenanceDescription = `
        <strong>Category A (Direct Official API — Global Signal):</strong> This item was fetched directly from the official ${escapeHTML(item.source.display_name)} API in real-time. Because ${escapeHTML(item.source.display_name)}'s decentralized public API does not provide regional filtering, this reflects global federated discussions rather than India-specific trends.
      `;
    } else if (isCatA) {
      provenanceDescription = `
        <strong>Category A (Direct Official API):</strong> This item was fetched directly from the official ${escapeHTML(item.source.display_name)} API in real-time. Engagement numbers and URLs represent authentic live content on the platform.
      `;
    } else if (item.source.slug === "google_trends") {
      provenanceDescription = `
        <strong>Category B (Search Interest Signal):</strong> This represents algorithmic search interest volume on Google Search. It is not social media post data.
      `;
      ctaButtonCopy = "Explore on Google Trends →";
    } else {
      provenanceDescription = `
        <strong>Category B (Derived News Coverage):</strong> This is a verified journalistic news article reporting ON trends, viral moments, or discussions relating to ${escapeHTML(item.source.display_name.replace("News Coverage: ", ""))}. The link points to the authoritative published news article.
      `;
      ctaButtonCopy = "Read Full News Article →";
    }

    const timeAndAuthorText = item.author
      ? `${escapeHTML(item.author)} · ${(item.source.slug === 'youtube' && item.published_at) ? `Published ${timeAgo(item.published_at)} (Trending ${timeAgo(item.fetched_at)})` : timeAgo(item.published_at || item.fetched_at)}`
      : ((item.source.slug === 'youtube' && item.published_at) ? `Published ${timeAgo(item.published_at)} (Trending ${timeAgo(item.fetched_at)})` : timeAgo(item.published_at || item.fetched_at));

    const hasSnapshots = history.snapshots && history.snapshots.length >= 2;

    content.innerHTML = `
      <div class="drawer-header-bar">
        <div class="drawer-source-info">
          <img class="drawer-source-icon" src="/static/assets/icons/${escapeHTML(item.source.icon_filename || 'youtube.svg')}" alt="" />
          <span class="drawer-source-name">${escapeHTML(item.source.display_name)}</span>
          <span class="${isCatA ? 'badge-cat-a' : 'badge-cat-b'}">${escapeHTML(item.source.source_type_label)}</span>
        </div>
        <button class="card-star-btn ${state.bookmarks.includes(item.id) ? 'active' : ''}" id="drawer-star-btn" title="Save Bookmark" style="font-size: 20px;">
          ${state.bookmarks.includes(item.id) ? '★' : '☆'}
        </button>
      </div>

      <h2 class="drawer-headline">
        ${escapeHTML(item.title)}
      </h2>

      <div class="drawer-meta-strip">
        <div class="drawer-tags-cluster">
          <span class="category-pill">${escapeHTML(item.category ? item.category.name : "Trending")}</span>
          ${regionChipHTML(item.trending_region)}
          ${getMomentumBadgeHTML(item.momentum)}
        </div>
        <div class="drawer-meta-author-time">
          ${timeAndAuthorText}
        </div>
      </div>

      ${item.trending_region ? `
        <div class="region-box">
          <div class="region-title">Trending Region</div>
          <div class="region-value">${item.trending_region.scope === 'global' ? '🌐 ' : '📍 '}${escapeHTML(item.trending_region.label)}</div>
          <div class="region-basis">${escapeHTML(item.trending_region.basis)}</div>
        </div>
      ` : ""}

      ${item.description ? `<p style="font-size:14px; line-height:1.6; color:var(--text-secondary); margin-bottom:20px;">${escapeHTML(item.description)}</p>` : ""}

      <!-- AI Summary -->
      ${item.ai_summary ? `
        <div class="ai-summary-box" style="margin:20px 0;">
          <div class="ai-summary-header" style="font-size:13px;">✨ AI Intelligence Summary (Gemini)</div>
          <p class="ai-summary-text" style="font-size:14px; margin-top:6px;">${escapeHTML(item.ai_summary)}</p>
        </div>
      ` : ""}

      <!-- Trend History & Velocity Section -->
      <div class="drawer-history-section">
        <div class="drawer-history-header">
          <span class="drawer-history-title">📈 Trend Velocity & History</span>
          <span class="chart-badge">${history.snapshots ? history.snapshots.length : 0} observations</span>
        </div>
        ${hasSnapshots ? `
          <div class="drawer-chart-container">
            <canvas id="drawer-history-chart"></canvas>
          </div>
          <div class="history-explanation-text">
            ${escapeHTML(getMomentumExplanation(item.momentum))}
          </div>
        ` : `
          <div class="history-explanation-text" style="border-left-color: #94a3c2;">
            Momentum needs a few fetch cycles to appear. Snapshots are recorded on each scheduled run.
          </div>
        `}
      </div>


      <!-- Sourced Community Reactions & Comments Section (Top 10) -->
      <div class="drawer-comments-section">
        <div class="drawer-comments-header">
          <div class="drawer-comments-title-wrap">
            <span class="drawer-comments-title">💬 Sourced Community Reactions</span>
            <span class="comments-count-pill">${commentsData.total || 0} reactions</span>
            ${commentsData.is_generated !== false ? '<span class="generated-badge">SAMPLE / GENERATED COMMENTS</span>' : ''}
          </div>
          <div class="comments-sentiment-strip">
            ${renderSentimentBreakdownHTML(commentsData.sentiment_breakdown, commentsData.total)}
          </div>
        </div>
        <div class="drawer-comments-list">
          ${commentsData.comments && commentsData.comments.length > 0
            ? commentsData.comments.map(c => renderCommentCardHTML(c)).join("")
            : `<div class="comments-empty-notice">No community comments recorded for this item yet.</div>`
          }
        </div>
      </div>

      <!-- Data Source Provenance Box -->
      <div class="provenance-card" style="margin-top:20px;">
        <div class="provenance-title">Data Source Provenance</div>
        <div class="provenance-desc">${provenanceDescription}</div>
      </div>

      <a class="drawer-cta-btn ${isCatA ? '' : 'signal-cta'}" href="${escapeHTML(item.url)}" target="_blank" rel="noopener noreferrer">
        ${ctaButtonCopy}
      </a>
    `;

    // Attach drawer star button
    const drawerStarBtn = content.querySelector("#drawer-star-btn");
    if (drawerStarBtn) {
      drawerStarBtn.addEventListener("click", () => {
        toggleBookmark(item.id);
        const isNowSaved = state.bookmarks.includes(item.id);
        drawerStarBtn.classList.toggle("active", isNowSaved);
        drawerStarBtn.textContent = isNowSaved ? "★" : "☆";
      });
    }

    // Render Drawer History Line Chart if snapshots available
    if (hasSnapshots && window.Chart) {
      const histCanvas = content.querySelector("#drawer-history-chart");
      if (histCanvas) {
        const hasEng = history.snapshots.some(s => s.engagement_value !== null);
        const chartData = hasEng
          ? history.snapshots.map(s => s.engagement_value || 0)
          : history.snapshots.map(s => s.rank || 0);

        new window.Chart(histCanvas, {
          type: "line",
          data: {
            labels: history.snapshots.map(s => new Date(s.captured_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })),
            datasets: [{
              label: hasEng ? "Engagement" : "Rank",
              data: chartData,
              borderColor: "#2dd4c8",
              backgroundColor: "rgba(45, 212, 200, 0.12)",
              fill: true,
              tension: 0.3,
              pointRadius: 4,
              pointBackgroundColor: "#2dd4c8"
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                backgroundColor: "#121729",
                titleColor: "#e7ebf5",
                bodyColor: "#94a3c2",
                borderColor: "rgba(148, 163, 184, 0.25)",
                borderWidth: 1
              }
            },
            scales: {
              x: {
                grid: { display: false },
                ticks: { color: "#94a3c2", font: { family: "JetBrains Mono", size: 10 } }
              },
              y: {
                reverse: !hasEng,
                grid: { color: "rgba(148, 163, 184, 0.08)" },
                ticks: { color: "#94a3c2", font: { family: "JetBrains Mono", size: 10 }, precision: 0 }
              }
            }
          }
        });
      }
    }
  } catch (err) {
    content.innerHTML = `<div style="color:var(--negative); padding:20px;">Failed to load item: ${escapeHTML(err.message)}</div>`;
  }
}

function closeDetailDrawer() {
  const overlay = document.getElementById("drawer-overlay");
  const drawer = document.getElementById("detail-drawer");
  if (overlay) overlay.classList.remove("open");
  if (drawer) drawer.classList.remove("open");
}

// ============================================================
// Data Fetching & Orchestration
// ============================================================

async function fetchAndRenderTrends() {
  state.isLoading = true;
  renderSkeletons();

  try {
    const data = await api.getTrends({
      source: state.activeSource,
      sourceCategory: state.sourceCategory,
      recency: state.recency,
      regionScope: state.regionScope || undefined,
      category: state.category,
      sort: state.sort,
      page: state.page,
      perPage: state.perPage
    });

    state.items = data.items;
    state.total = data.total;
    state.totalPages = data.total_pages;
    state.windowWidenedTo = data.window_widened_to || data.filters_applied?.window_widened_to;
    state.originalWindowCount = data.original_window_count !== undefined ? data.original_window_count : data.filters_applied?.original_window_count;

    renderTrendsGrid();
    renderPagination();
  } catch (err) {
    const grid = document.getElementById("trends-grid");
    if (grid) {
      grid.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1; border-color: var(--negative);">
          <div class="empty-icon">⚠️</div>
          <h3>Failed to Load Feed</h3>
          <p>${escapeHTML(err.message || "Could not connect to backend.")}</p>
        </div>
      `;
    }
  } finally {
    state.isLoading = false;
  }
}

// ============================================================
// Client Utilities (Watchlist, Bookmarks, CSV Export)
// ============================================================

function toggleBookmark(itemId) {
  const idx = state.bookmarks.indexOf(itemId);
  if (idx >= 0) {
    state.bookmarks.splice(idx, 1);
  } else {
    state.bookmarks.push(itemId);
  }
  localStorage.setItem("socialpulse_bookmarks", JSON.stringify(state.bookmarks));
  updateToolCounters();
  renderTrendsGrid();
}

function addWatchlistKeyword(keyword) {
  const kw = keyword.trim().toLowerCase();
  if (kw && !state.watchlist.includes(kw)) {
    state.watchlist.push(kw);
    localStorage.setItem("socialpulse_watchlist", JSON.stringify(state.watchlist));
    updateWatchlistTags();
    renderTrendsGrid();
  }
}

function removeWatchlistKeyword(keyword) {
  state.watchlist = state.watchlist.filter(k => k !== keyword);
  localStorage.setItem("socialpulse_watchlist", JSON.stringify(state.watchlist));
  updateWatchlistTags();
  renderTrendsGrid();
}

function updateWatchlistTags() {
  const row = document.getElementById("watchlist-tags-row");
  const list = document.getElementById("watchlist-tags-list");
  const countEl = document.getElementById("watchlist-count");
  if (countEl) countEl.textContent = state.watchlist.length;

  if (!row || !list) return;
  if (state.watchlist.length === 0) {
    row.style.display = "none";
    list.innerHTML = "";
    return;
  }

  row.style.display = "flex";
  list.innerHTML = state.watchlist.map(kw => `
    <span class="watchlist-tag-pill">
      ${escapeHTML(kw)}
      <button class="remove-tag-btn" data-kw="${escapeHTML(kw)}" title="Remove keyword">×</button>
    </span>
  `).join("");

  list.querySelectorAll(".remove-tag-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const kw = btn.getAttribute("data-kw");
      removeWatchlistKeyword(kw);
    });
  });
}

function updateToolCounters() {
  const savedCountEl = document.getElementById("saved-count");
  if (savedCountEl) savedCountEl.textContent = state.bookmarks.length;
  const watchCountEl = document.getElementById("watchlist-count");
  if (watchCountEl) watchCountEl.textContent = state.watchlist.length;
}

function handleDownloadCSV() {
  const params = new URLSearchParams();
  if (state.activeSource && state.activeSource !== "all") {
    params.append("source", state.activeSource);
  }
  if (state.sourceCategory && state.sourceCategory !== "all") {
    params.append("source_category", state.sourceCategory);
  }
  if (state.recency) params.append("recency", state.recency);
  if (state.regionScope) params.append("region_scope", state.regionScope);
  if (state.category) params.append("category", state.category);
  if (state.sort) params.append("sort", state.sort);

  window.location.href = `/api/v1/trends/export.csv?${params.toString()}`;
}

async function loadInitialData() {
  try {
    const [sourcesData, categoriesData] = await Promise.all([
      api.getSources(),
      api.getCategories()
    ]);

    state.sources = sourcesData.sources || [];
    state.categories = categoriesData.categories || [];

    renderSourceTabs();
    renderCategoryFilter();
    updateToolCounters();
    updateWatchlistTags();
    await fetchAndRenderTrends();
  } catch (err) {
    console.error("Initial load failed:", err);
  }
}

// ============================================================
// Event Listeners & Bootstrapping
// ============================================================

function initSocialPulse() {
  initNetworkCanvas();

  // Watchlist & Bookmark Filters
  const watchlistToggleBtn = document.getElementById("watchlist-toggle-btn");
  if (watchlistToggleBtn) {
    watchlistToggleBtn.addEventListener("click", () => {
      state.filterWatchlistOnly = !state.filterWatchlistOnly;
      watchlistToggleBtn.classList.toggle("active", state.filterWatchlistOnly);
      renderTrendsGrid();
    });
  }

  const watchlistInput = document.getElementById("watchlist-input");
  if (watchlistInput) {
    watchlistInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && watchlistInput.value.trim()) {
        e.preventDefault();
        addWatchlistKeyword(watchlistInput.value);
        watchlistInput.value = "";
      }
    });
  }

  const savedToggleBtn = document.getElementById("saved-toggle-btn");
  if (savedToggleBtn) {
    savedToggleBtn.addEventListener("click", () => {
      state.filterSavedOnly = !state.filterSavedOnly;
      savedToggleBtn.classList.toggle("active", state.filterSavedOnly);
      renderTrendsGrid();
    });
  }

  // Download CSV
  const downloadCsvBtn = document.getElementById("download-csv-btn");
  if (downloadCsvBtn) {
    downloadCsvBtn.addEventListener("click", handleDownloadCSV);
  }

  // Recency Pills
  const recencyContainer = document.getElementById("recency-pills");
  if (recencyContainer) {
    recencyContainer.querySelectorAll(".recency-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        recencyContainer.querySelectorAll(".recency-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");

        state.recency = btn.getAttribute("data-hours");
        state.page = 1;
        fetchAndRenderTrends();
      });
    });
  }

  // Region Filter Select
  const regionSelect = document.getElementById("region-filter");
  if (regionSelect) {
    regionSelect.addEventListener("change", (e) => {
      state.regionScope = e.target.value;
      state.page = 1;
      fetchAndRenderTrends();
    });
  }

  // Category Filter Select
  const categorySelect = document.getElementById("category-filter");
  if (categorySelect) {
    categorySelect.addEventListener("change", (e) => {
      state.category = e.target.value;
      state.page = 1;
      fetchAndRenderTrends();
    });
  }

  // Sort Filter Select
  const sortSelect = document.getElementById("sort-filter");
  if (sortSelect) {
    sortSelect.addEventListener("change", (e) => {
      state.sort = e.target.value;
      state.page = 1;
      fetchAndRenderTrends();
    });
  }

  // Manual Refresh Button
  const refreshBtn = document.getElementById("manual-refresh-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", async () => {
      refreshBtn.innerText = "Refreshing...";
      await api.triggerPipelineRun();
      await fetchAndRenderTrends();
      refreshBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
        </svg>
        Refresh
      `;
    });
  }

  // Drawer Close Button, Overlay & ESC Key
  const closeBtn = document.getElementById("drawer-close-btn");
  const overlay = document.getElementById("drawer-overlay");
  if (closeBtn) closeBtn.addEventListener("click", closeDetailDrawer);
  if (overlay) overlay.addEventListener("click", closeDetailDrawer);

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeDetailDrawer();
    }
  });

  // Client-Side Hash Router
  function handleRoute() {
    const hash = window.location.hash || "#/feed";
    if (hash.startsWith("#/analytics")) {
      switchView("analytics");
    } else if (hash.startsWith("#/topics")) {
      switchView("topics");
    } else if (hash.startsWith("#/health")) {
      switchView("health");
    } else {
      switchView("feed");
    }
  }

  function switchView(viewName) {
    const views = {
      feed: document.getElementById("feed-view-container"),
      topics: document.getElementById("topics-view-container"),
      analytics: document.getElementById("analytics-view-container"),
      health: document.getElementById("health-view-container")
    };

    const navTabs = document.querySelectorAll(".nav-tab");
    navTabs.forEach((tab) => {
      if (tab.getAttribute("data-view") === viewName) {
        tab.classList.add("active");
      } else {
        tab.classList.remove("active");
      }
    });

    Object.keys(views).forEach((k) => {
      if (views[k]) {
        views[k].style.display = k === viewName ? "block" : "none";
      }
    });

    if (viewName !== "health") {
      stopHealthAutoRefresh();
    }

    if (viewName === "analytics" && views.analytics) {
      renderAnalyticsView(views.analytics);
    } else if (viewName === "health" && views.health) {
      renderHealthView(views.health);
    } else if (viewName === "topics" && views.topics) {
      renderTopicsView(views.topics);
    }
  }

  window.addEventListener("hashchange", handleRoute);

  // Initial Load
  loadInitialData();
  handleRoute();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSocialPulse);
} else {
  initSocialPulse();
}
