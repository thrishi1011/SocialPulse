/**
 * SocialPulse API Client
 */

const API_BASE = "/api/v1";

async function request(url, options = {}) {
  try {
    const res = await fetch(url, {
      headers: {
        "Accept": "application/json",
        ...options.headers,
      },
      ...options,
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `API error (${res.status})`);
    }
    return await res.json();
  } catch (err) {
    console.error(`API Error on ${url}:`, err);
    throw err;
  }
}

export const api = {
  // Trends
  async getTrends({ source, sourceCategory, recency = "24h", regionScope, category, sort = "recency", page = 1, perPage = 30 } = {}) {
    const params = new URLSearchParams();
    if (source && source !== "all") {
      if (Array.isArray(source)) {
        source.forEach(s => params.append("source", s));
      } else {
        params.append("source", source);
      }
    }
    if (sourceCategory && sourceCategory !== "all") {
      params.append("source_category", sourceCategory);
    }
    if (recency) params.append("recency", recency);
    if (regionScope) params.append("region_scope", regionScope);
    if (category) params.append("category", category);
    if (sort) params.append("sort", sort);
    if (page) params.append("page", String(page));
    if (perPage) params.append("per_page", String(perPage));

    return request(`${API_BASE}/trends?${params.toString()}`);
  },

  async getTrendById(id) {
    return request(`${API_BASE}/trends/${id}`);
  },

  // Sources
  async getSources() {
    return request(`${API_BASE}/sources`);
  },

  async getSourceStatus(slug) {
    return request(`${API_BASE}/sources/${slug}/status`);
  },

  // Categories
  async getCategories() {
    return request(`${API_BASE}/categories`);
  },

  // Pipeline
  async getPipelineStatus() {
    return request(`${API_BASE}/pipeline/status`);
  },

  async triggerPipelineRun(slug = null) {
    const url = slug ? `${API_BASE}/pipeline/run/${slug}` : `${API_BASE}/pipeline/run`;
    return request(url, { method: "POST" });
  },

  async triggerAIProcessing(limit = 50) {
    return request(`${API_BASE}/pipeline/process-ai?limit=${limit}`, { method: "POST" });
  },

  // Health
  async getHealth() {
    return request("/health");
  },

  // Analytics
  async getAnalyticsOverview(recency = "24h") {
    return request(`${API_BASE}/analytics/overview?recency=${recency}`);
  },

  // Source Health Observatory
  async getSourceHealth() {
    return request(`${API_BASE}/sources/health`);
  },

  async getSourceLogs(slug, limit = 20) {
    return request(`${API_BASE}/sources/${slug}/logs?limit=${limit}`);
  },

  // Macro Topics
  async getTopics({ minSources = 2, recency = "24h" } = {}) {
    return request(`${API_BASE}/topics?min_sources=${minSources}&recency=${recency}`);
  },

  async getTopicById(id) {
    return request(`${API_BASE}/topics/${id}`);
  },

  // Trend History & Momentum
  async getTrendHistory(id) {
    return request(`${API_BASE}/trends/${id}/history`);
  },

  // Community Comments & Social Reactions
  async getItemComments(id, limit = 10) {
    return request(`${API_BASE}/trends/${id}/comments?limit=${limit}`);
  },

  async getTopicComments(id, limit = 8) {
    return request(`${API_BASE}/topics/${id}/comments?limit=${limit}`);
  }
};
