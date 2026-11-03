/**
 * frontend/js/views/topics.js
 * 
 * Macro Stories (Cross-Platform Topic Convergence) View:
 * Groups stories corroborated across 2+ distinct platforms (e.g. YouTube, Bluesky, Mastodon, News).
 * Includes AI story synthesis, convergence badges, source provenance, and expandable member items.
 */
import { api } from "../api.js";
import { timeAgo, formatNumber, escapeHTML, renderCommentCardHTML, renderSentimentBreakdownHTML } from "../utils.js";

let currentTopicRecency = "24h";

export async function renderTopicsView(container) {
  container.innerHTML = `
    <div class="topics-view-wrapper">
      <div class="topics-header">
        <div>
          <h2 class="view-title">Macro Stories</h2>
          <p class="view-subtitle">High-signal stories confirmed and trending across multiple distinct platforms</p>
        </div>
        <div class="topics-controls">
          <div class="recency-pills topic-recency-pills" role="radiogroup" aria-label="Topics Recency">
            <button class="recency-btn ${currentTopicRecency === '6h' ? 'active' : ''}" data-recency="6h">Past 6h</button>
            <button class="recency-btn ${currentTopicRecency === '12h' ? 'active' : ''}" data-recency="12h">Past 12h</button>
            <button class="recency-btn ${currentTopicRecency === '24h' ? 'active' : ''}" data-recency="24h">Past 24h</button>
            <button class="recency-btn ${currentTopicRecency === 'all' ? 'active' : ''}" data-recency="all">All Time</button>
          </div>
        </div>
      </div>

      <div id="topics-loading" class="analytics-loading-state">
        <div class="spinner"></div>
        <span>Clustering cross-platform stories...</span>
      </div>

      <div id="topics-content" style="display: none;">
        <!-- Honest Empty State -->
        <div id="topics-empty-state" class="analytics-empty-card" style="display: none;">
          <div class="empty-icon">🌐</div>
          <h3>No cross-platform stories detected yet</h3>
          <p>No multi-source clusters currently meet the 2+ distinct source convergence threshold in this recency window. Single-outlet stories remain in the Live Feed.</p>
        </div>

        <!-- Topics Grid -->
        <div class="topics-cards-list" id="topics-list"></div>
      </div>
    </div>
  `;

  // Attach recency selector events
  const pillButtons = container.querySelectorAll(".topic-recency-pills button");
  pillButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      pillButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentTopicRecency = btn.getAttribute("data-recency");
      loadTopicsData(container);
    });
  });

  await loadTopicsData(container);
}

async function loadTopicsData(container) {
  const loadingEl = container.querySelector("#topics-loading");
  const contentEl = container.querySelector("#topics-content");
  const emptyEl = container.querySelector("#topics-empty-state");
  const listEl = container.querySelector("#topics-list");

  loadingEl.style.display = "flex";
  contentEl.style.display = "none";

  try {
    const data = await api.getTopics({ minSources: 2, recency: currentTopicRecency });
    loadingEl.style.display = "none";
    contentEl.style.display = "block";

    if (!data.topics || data.topics.length === 0) {
      emptyEl.style.display = "flex";
      listEl.innerHTML = "";
      return;
    }

    emptyEl.style.display = "none";

    listEl.innerHTML = data.topics.map((t) => {
      const sourcesBadges = (t.sources || []).map((s) => `
        <span class="topic-source-pill">${escapeHTML(s)}</span>
      `).join("");

      return `
        <article class="topic-card" id="topic-card-${t.id}">
          <div class="topic-card-top">
            <div class="topic-convergence-badge">
              <span class="fire-icon">🔥</span>
              <strong>Trending across ${t.source_count} sources</strong>
              <span class="topic-count-pill">${t.item_count} posts</span>
            </div>
            <div class="topic-time-ago">${timeAgo(t.updated_at)}</div>
          </div>

          <h3 class="topic-title">${escapeHTML(t.title)}</h3>

          ${t.summary ? `
            <div class="topic-ai-summary">
              <div class="summary-label">
                <span class="sparkle-icon">✨</span>
                AI STORY SYNTHESIS
              </div>
              <p>${escapeHTML(t.summary)}</p>
            </div>
          ` : `
            <div class="topic-no-summary">
              Corroborated across ${t.source_count} independent platforms (${t.item_count} items).
            </div>
          `}

          <div class="topic-sources-bar">
            <span class="sources-label">Reporting Sources:</span>
            <div class="sources-pill-group">
              ${sourcesBadges}
            </div>
          </div>

          <div class="topic-footer">
            <div class="topic-footer-buttons">
              <button class="expand-topic-btn" data-topic-id="${t.id}">
                <span>View ${t.item_count} Member Stories</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
              </button>
              <button class="expand-topic-comments-btn" data-topic-id="${t.id}">
                <span>💬 Community Discussions</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
              </button>
            </div>
          </div>

          <!-- Collapsible Member Items Container -->
          <div class="topic-members-drawer" id="members-${t.id}" style="display: none;">
            <div class="members-inner" id="members-list-${t.id}">
              <div class="spinner"></div> Loading member stories...
            </div>
          </div>

          <!-- Collapsible Community Discussions Container -->
          <div class="topic-comments-drawer" id="topic-comments-${t.id}" style="display: none;">
            <div class="topic-comments-inner" id="topic-comments-list-${t.id}">
              <div class="spinner"></div> Loading cross-platform discussions...
            </div>
          </div>
        </article>
      `;
    }).join("");

    // Attach member stories expand toggle events
    listEl.querySelectorAll(".expand-topic-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const topicId = btn.getAttribute("data-topic-id");
        const drawer = listEl.querySelector(`#members-${topicId}`);
        const membersList = listEl.querySelector(`#members-list-${topicId}`);

        if (drawer.style.display !== "none") {
          drawer.style.display = "none";
          btn.classList.remove("active");
          btn.querySelector("span").textContent = `View Member Stories`;
          return;
        }

        drawer.style.display = "block";
        btn.classList.add("active");
        btn.querySelector("span").textContent = `Hide Member Stories`;

        try {
          const detail = await api.getTopicById(topicId);
          membersList.innerHTML = `
            <div class="topic-members-grid">
              ${detail.items.map((m) => `
                <div class="topic-member-card">
                  <div class="member-source-meta">
                    <span class="member-source-name ${m.source_category === 'A' ? 'cat-a' : 'cat-b'}">
                      ${escapeHTML(m.source.display_name)}
                    </span>
                    <span class="member-time">${timeAgo(m.published_at || m.fetched_at)}</span>
                  </div>
                  <h4 class="member-headline">
                    <a href="${escapeHTML(m.url)}" target="_blank" rel="noopener noreferrer">
                      ${escapeHTML(m.title)}
                    </a>
                  </h4>
                  ${m.author ? `<div class="member-author">By ${escapeHTML(m.author)}</div>` : ''}
                  <div class="member-engagement">
                    ${m.engagement?.value ? `<span>${m.engagement.label || 'Engagement'}: <strong>${formatNumber(m.engagement.value)}</strong></span>` : ''}
                    <a href="${escapeHTML(m.url)}" target="_blank" rel="noopener noreferrer" class="member-link-arrow">Read Original ↗</a>
                  </div>
                </div>
              `).join("")}
            </div>
          `;
        } catch (err) {
          membersList.innerHTML = `<div class="error-msg">Failed to load member stories: ${err.message}</div>`;
        }
      });
    });

    // Attach community discussions expand toggle events
    listEl.querySelectorAll(".expand-topic-comments-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const topicId = btn.getAttribute("data-topic-id");
        const drawer = listEl.querySelector(`#topic-comments-${topicId}`);
        const commentsList = listEl.querySelector(`#topic-comments-list-${topicId}`);

        if (drawer.style.display !== "none") {
          drawer.style.display = "none";
          btn.classList.remove("active");
          btn.querySelector("span").textContent = `💬 Community Discussions`;
          return;
        }

        drawer.style.display = "block";
        btn.classList.add("active");
        btn.querySelector("span").textContent = `Hide Discussions`;

        try {
          const data = await api.getTopicComments(topicId, 8);
          if (!data.comments || data.comments.length === 0) {
            commentsList.innerHTML = `<div class="comments-empty-notice">No cross-platform reactions detected for this topic yet.</div>`;
            return;
          }

          commentsList.innerHTML = `
            <div class="topic-comments-wrapper">
              <div class="topic-comments-meta-bar">
                <span class="topic-comments-heading">Cross-Platform Reactions (${data.total})</span>
                ${data.is_generated !== false ? '<span class="generated-badge">SAMPLE / GENERATED COMMENTS</span>' : ''}
                <div class="comments-sentiment-strip">
                  ${renderSentimentBreakdownHTML(data.sentiment_breakdown, data.total)}
                </div>
              </div>
              <div class="topic-comments-grid">
                ${data.comments.map(c => renderCommentCardHTML(c)).join("")}
              </div>
            </div>
          `;
        } catch (err) {
          commentsList.innerHTML = `<div class="error-msg">Failed to load topic discussions: ${err.message}</div>`;
        }
      });
    });

  } catch (err) {
    console.error("Failed to load topics:", err);
    loadingEl.innerHTML = `<div class="error-msg">Failed to load macro topics: ${err.message}</div>`;
  }
}

