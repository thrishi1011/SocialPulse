/**
 * SocialPulse Frontend Utilities
 */

export function timeAgo(dateString) {
  if (!dateString) return "Live trend";
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);

  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "1 day ago";
  return `${days}d ago`;
}

export function formatNumber(num) {
  if (num === null || num === undefined) return null;
  const n = Number(num);
  if (isNaN(n)) return null;

  if (n >= 1_000_000) {
    const formatted = (n / 1_000_000).toFixed(1);
    return formatted.endsWith(".0") ? formatted.slice(0, -2) + "M" : formatted + "M";
  }
  if (n >= 1_000) {
    const formatted = (n / 1_000).toFixed(1);
    return formatted.endsWith(".0") ? formatted.slice(0, -2) + "K" : formatted + "K";
  }
  return n.toLocaleString();
}

export function escapeHTML(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function truncate(str, maxLength = 140) {
  if (!str) return "";
  if (str.length <= maxLength) return str;
  return str.substring(0, maxLength).trim() + "...";
}

export function getInitials(name) {
  if (!name) return "?";
  const parts = name.trim().replace(/^[@u\/]+/, "").split(/[\s_.]+/);
  if (parts.length >= 2 && parts[0] && parts[1]) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return parts[0] ? parts[0].slice(0, 2).toUpperCase() : "?";
}

export function getPlatformBadge(platform) {
  const p = (platform || "social").toLowerCase();
  const map = {
    youtube: { label: "YouTube", class: "platform-yt" },
    reddit: { label: "Reddit", class: "platform-reddit" },
    bluesky: { label: "Bluesky", class: "platform-bsky" },
    mastodon: { label: "Mastodon", class: "platform-mastodon" },
    twitter: { label: "X (Twitter)", class: "platform-twitter" },
    twitch: { label: "Twitch", class: "platform-twitch" },
  };
  return map[p] || { label: platform, class: "platform-generic" };
}

export function getSentimentBadge(sentiment) {
  const s = (sentiment || "neutral").toLowerCase();
  const map = {
    positive: { label: "Positive", icon: "🟢", class: "sentiment-positive" },
    excited: { label: "Excited", icon: "🔥", class: "sentiment-excited" },
    curious: { label: "Curious", icon: "💡", class: "sentiment-curious" },
    critical: { label: "Critical", icon: "⚠️", class: "sentiment-critical" },
    neutral: { label: "Neutral", icon: "⚪", class: "sentiment-neutral" }
  };
  return map[s] || { label: sentiment, icon: "⚪", class: "sentiment-neutral" };
}

export function renderSentimentBreakdownHTML(breakdown = {}, total = 0) {
  if (!total || total === 0) return "";
  const badges = [];
  const labels = [
    { key: "positive", label: "Positive" },
    { key: "excited", label: "Excited" },
    { key: "curious", label: "Curious" },
    { key: "neutral", label: "Neutral" },
    { key: "critical", label: "Critical" }
  ];
  for (const { key, label } of labels) {
    const count = breakdown[key] || 0;
    if (count > 0) {
      const pct = Math.round((count / total) * 100);
      const badgeInfo = getSentimentBadge(key);
      badges.push(`
        <span class="sentiment-pill ${badgeInfo.class}">
          ${badgeInfo.icon} ${pct}% ${label}
        </span>
      `);
    }
  }
  return badges.join("");
}

export function renderCommentCardHTML(c) {
  const pBadge = getPlatformBadge(c.platform);
  const sBadge = getSentimentBadge(c.sentiment);
  const initials = getInitials(c.author);
  const avatarBg = c.author_avatar_color || "#3b82f6";

  return `
    <div class="comment-card" id="comment-${c.id}">
      <div class="comment-card-top">
        <div class="comment-user-area">
          <div class="comment-avatar" style="background-color: ${escapeHTML(avatarBg)};">
            ${escapeHTML(initials)}
          </div>
          <div class="comment-user-info">
            <span class="comment-author-name">${escapeHTML(c.author)}</span>
            <span class="comment-author-handle">${escapeHTML(c.author_handle)}</span>
          </div>
        </div>
        <div class="comment-meta-badges">
          <span class="comment-platform-badge ${pBadge.class}">${pBadge.label}</span>
          <span class="comment-time">${timeAgo(c.published_at || c.created_at)}</span>
        </div>
      </div>
      <p class="comment-text">${escapeHTML(c.content)}</p>
      <div class="comment-card-footer">
        <div class="comment-engagement">
          <span class="upvote-icon">▲</span>
          <strong>${formatNumber(c.upvotes) || '0'}</strong>
          <span class="engagement-sub">reactions</span>
        </div>
        <span class="comment-sentiment-chip ${sBadge.class}">
          ${sBadge.icon} ${sBadge.label}
        </span>
      </div>
    </div>
  `;
}

