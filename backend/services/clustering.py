"""
backend/services/clustering.py

Cross-Platform Topic Clustering ("Macro Stories") Engine:
Identifies, groups, and tracks trending real-world stories that emerge across multiple
disparate platforms (e.g. an event appearing simultaneously on YouTube, Bluesky, Mastodon,
and News Coverage).

Algorithm Architecture:
1. Candidate Selection: Items fetched within the last 24 hours.
2. Title Token Normalization: Lowercase, punctuation removal, stopword filtering.
3. Offline Heuristic Pre-Pass (Jaccard + Union-Find):
   - Computes pairwise Jaccard token similarity.
   - Links items with similarity >= 0.5 using Disjoint Set Union (DSU).
   - Guarantees 100% offline, zero-cost, fail-safe clustering when LLM is unavailable.
4. LLM Refinement Pass (Gemini):
   - If Gemini is enabled and key is present, sends compact batches (max 60 items/call, max 2 calls).
   - Enforces strict story-level grouping (same event, not just broad theme).
   - Rigorous structural validation (id existence, single-group membership, >=2 items).
5. Incremental Topic Tracking:
   - Matches incoming trends to currently active topics first before creating new ones.
   - Deactivates stale topics older than 48 hours.
6. Cross-Platform Convergence:
   - Counts distinct reporting sources. Only topics with source_count >= 2 are cross-platform.
7. Batched Story Summarization:
   - Summarizes up to 5 new converged topics in a single batched Gemini call.
"""
import re
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.config import settings
from backend.models import TrendingItem, Topic, Source
from backend.utils.rate_limiter import gemini_rate_limiter

logger = logging.getLogger("socialpulse.clustering")

clustering_lock = asyncio.Lock()

def _generate_with_gemini(prompt: str) -> str:
    """Generate content trying preferred Gemini models in order."""
    import google.generativeai as genai
    models_to_try = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest", "gemini-3.6-flash", "gemini-2.5-flash"]
    last_err = None
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("No Gemini model available")

STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "by", "for", "with", "about",
    "against", "between", "into", "through", "during", "before", "after",
    "above", "below", "to", "from", "up", "down", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "and", "but", "if", "or", "because", "as", "until", "while",
    "of", "it", "its", "news", "live", "updates", "watch", "video", "report",
    "today", "latest", "new", "vs", "over", "what", "which", "who", "whom",
    "this", "that", "these", "those", "am", "will", "would", "shall", "should",
    "can", "could", "may", "might", "must"
}


# ============================================================
# Heuristic & Token Normalization Helpers
# ============================================================

def normalize_title(title: str) -> set[str]:
    """
    Extract meaningful normalized keywords from a headline or title.
    Strips punctuation, digits-only noise, and standard stopwords.
    """
    if not title:
        return set()
    clean = re.sub(r"[^\w\s]", " ", title.lower())
    tokens = clean.split()
    return {
        t for t in tokens
        if len(t) > 2 and t not in STOPWORDS and not t.isdigit()
    }


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """
    Compute token-set Jaccard similarity: |A ∩ B| / |A ∪ B|.
    Returns 0.0 if either set is empty.
    """
    if not set_a or not set_b:
        return 0.0
    intersection = set_a.intersection(set_b)
    union = set_a.union(set_b)
    if not union:
        return 0.0
    return len(intersection) / len(union)


class UnionFind:
    """
    Disjoint Set Union (DSU) data structure with path compression
    and union-by-rank for efficient transitive group clustering.
    """
    def __init__(self, elements):
        self.parent = {el: el for el in elements}
        self.rank = {el: 0 for el in elements}

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            self.parent[rx] = ry
        elif self.rank[rx] > self.rank[ry]:
            self.parent[ry] = rx
        else:
            self.parent[ry] = rx
            self.rank[rx] += 1


def cluster_by_jaccard_heuristic(items: list[TrendingItem], threshold: float = 0.25) -> list[dict[str, Any]]:
    """
    Compute pairwise Jaccard similarities on candidate items and build groups via Union-Find.
    Pure, deterministic fallback when Gemini is unavailable.
    """
    if len(items) < 2:
        return []

    item_map = {item.id: item for item in items}
    tokens_map = {item.id: normalize_title(item.title) for item in items}
    uf = UnionFind([item.id for item in items])

    item_ids = list(item_map.keys())
    for i in range(len(item_ids)):
        id_a = item_ids[i]
        tokens_a = tokens_map[id_a]
        if not tokens_a:
            continue
        for j in range(i + 1, len(item_ids)):
            id_b = item_ids[j]
            tokens_b = tokens_map[id_b]
            if not tokens_b:
                continue
            sim = jaccard_similarity(tokens_a, tokens_b)
            if sim >= threshold:
                uf.union(id_a, id_b)

    # Group by root parent
    components: dict[int, list[int]] = {}
    for item_id in item_ids:
        root = uf.find(item_id)
        components.setdefault(root, []).append(item_id)

    # Filter to groups with 2+ items
    groups = []
    for member_ids in components.values():
        if len(member_ids) >= 2:
            # Pick highest engagement title as group title
            sorted_members = sorted(
                [item_map[mid] for mid in member_ids],
                key=lambda m: (m.engagement_value or 0),
                reverse=True
            )
            groups.append({
                "title": sorted_members[0].title,
                "item_ids": member_ids
            })

    return groups


# ============================================================
# Gemini LLM Grouping & Validation
# ============================================================

def validate_llm_groups(
    raw_groups: Any,
    valid_ids: set[int]
) -> list[dict[str, Any]]:
    """
    Strict validation for LLM clustering response:
    - Must be a list of dicts with 'title' and 'item_ids'
    - Every ID in item_ids must exist in the input request batch
    - No ID may be repeated across groups (one item in at most one group)
    - Groups must contain >= 2 items
    """
    if not isinstance(raw_groups, list):
        return []

    validated_groups = []
    assigned_ids = set()

    for g in raw_groups:
        if not isinstance(g, dict):
            continue
        title = g.get("title")
        item_ids = g.get("item_ids")
        if not title or not isinstance(title, str) or not isinstance(item_ids, list):
            continue

        # Filter and validate item_ids
        clean_ids = []
        for x in item_ids:
            try:
                iid = int(x)
                if iid in valid_ids and iid not in assigned_ids:
                    clean_ids.append(iid)
            except (ValueError, TypeError):
                continue

        if len(clean_ids) >= 2:
            validated_groups.append({
                "title": title.strip(),
                "item_ids": clean_ids
            })
            for cid in clean_ids:
                assigned_ids.add(cid)

    return validated_groups


async def group_items_with_gemini(items: list[TrendingItem]) -> list[dict[str, Any]]:
    """
    Send compact items to Gemini in up to 2 batches (max 60 items per batch).
    Returns validated groups of [{title, item_ids}].
    """
    if settings.MOCK_AI_MODE or not settings.GEMINI_KEY:
        return cluster_by_jaccard_heuristic(items)

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_KEY)
    except Exception as e:
        logger.warning(f"Could not configure Gemini for clustering: {e}. Using Jaccard fallback.")
        return cluster_by_jaccard_heuristic(items)

    all_groups = []
    # Send up to 2 batches of max 60 items (120 items max)
    batch_size = 60
    max_batches = 2

    for b_idx in range(min(max_batches, (len(items) + batch_size - 1) // batch_size)):
        batch = items[b_idx * batch_size : (b_idx + 1) * batch_size]
        if len(batch) < 2:
            continue

        valid_ids = {item.id for item in batch}
        compact_payload = [
            {
                "id": item.id,
                "title": item.title,
                "source": item.source.display_name if item.source else f"Source {item.source_id}"
            }
            for item in batch
        ]

        prompt = f"""You are SocialPulse's Editorial Intelligence Director.
Your task is to analyze these trending social media posts and group items that report on the EXACT SAME real-world event or story.

Rules:
1. ONLY group items that are about the EXACT SAME specific news story or event (e.g. Chandrayaan-4 mission milestone, India vs Australia final match, a specific cabinet decision).
2. DO NOT group items merely sharing a broad category or domain (e.g. do not put all cricket matches into one group, do not put unrelated Bollywood gossip together).
3. Return ONLY groups that have 2 or more item IDs.
4. NEVER invent item IDs. Every ID must be an integer from the provided list.
5. Each item ID must appear in at most one group.
6. If an item does not share a story with any other item in this batch, do NOT include it.

Input Items:
{json.dumps(compact_payload, indent=2)}

Return ONLY a valid JSON array matching this format (no markdown code blocks, no other text):
[
  {{"title": "Crisp headline of the shared real-world event", "item_ids": [id1, id2]}}
]
"""
        raw_text = ""
        for attempt in range(2):  # Retry once on JSON failure
            try:
                gemini_rate_limiter.acquire()
                raw_text = _generate_with_gemini(prompt)
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                elif raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                raw_text = raw_text.strip()

                parsed = json.loads(raw_text)
                validated = validate_llm_groups(parsed, valid_ids)
                all_groups.extend(validated)
                break
            except Exception as parse_err:
                logger.warning(f"Gemini clustering batch {b_idx} attempt {attempt+1} failed: {parse_err}")
                if attempt == 1:
                    # Fallback to Jaccard on this batch
                    jaccard_groups = cluster_by_jaccard_heuristic(batch)
                    all_groups.extend(jaccard_groups)

    return all_groups


async def summarize_topics_with_gemini(topics: list[Topic], db: Session):
    """
    Generate crisp, factual summaries for up to 5 new cross-platform topics in ONE Gemini call.
    Preserves journalistic hedging for unverified claims.
    """
    if not topics or settings.MOCK_AI_MODE or not settings.GEMINI_KEY:
        return

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_KEY)
    except Exception:
        return

    payload = []
    for t in topics[:5]:
        sample_titles = [m.title for m in t.items[:4]]
        payload.append({
            "topic_id": t.id,
            "topic_title": t.title,
            "sample_headlines": sample_titles
        })

    prompt = f"""You are an unbiased news analyst. Summarize each of the following multi-platform trending stories into 1 to 2 concise, factual sentences.
Explain what is happening and why it is generating discussion across multiple platforms.
Preserve hedging language (e.g. 'reportedly', 'alleged', 'claims') if details are unconfirmed.

Stories:
{json.dumps(payload, indent=2)}

Return ONLY a valid JSON array:
[
  {{"topic_id": 123, "summary": "1-2 factual sentences summarizing the story."}}
]
"""
    try:
        gemini_rate_limiter.acquire()
        text = _generate_with_gemini(prompt)
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        summaries = json.loads(text.strip())
        summary_map = {s.get("topic_id"): s.get("summary") for s in summaries if isinstance(s, dict)}

        for t in topics[:5]:
            if t.id in summary_map and summary_map[t.id]:
                t.summary = summary_map[t.id].strip()
        db.commit()
    except Exception as e:
        logger.warning(f"Batched topic summary call failed: {e}")


# ============================================================
# Main Clustering Orchestration
# ============================================================

async def _execute_clustering(db: Session) -> dict[str, Any]:
    """
    Internal execution of the topic clustering pipeline.
    """
    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)

    # 1. Fetch candidate items from last 24h
    candidates = (
        db.query(TrendingItem)
        .filter(TrendingItem.fetched_at >= cutoff_24h)
        .order_by(TrendingItem.fetched_at.desc())
        .all()
    )

    if not candidates:
        logger.info("No candidate trending items found in the last 24h for clustering.")
        return {"status": "success", "new_topics": 0, "active_topics": 0}

    # 2. Existing active topics
    active_topics = db.query(Topic).filter(Topic.is_active == True).all()

    # Precompute token sets for active topics
    topic_tokens = {}
    for t in active_topics:
        combined_text = t.title + " " + " ".join([m.title for m in t.items[:5]])
        topic_tokens[t.id] = normalize_title(combined_text)

    # 3. Match unassigned items to existing active topics first
    unassigned_items: list[TrendingItem] = []
    for item in candidates:
        if item.topic_id is not None:
            continue  # Already assigned to an active topic

        item_tokens = normalize_title(item.title)
        matched_topic_id = None

        if item_tokens:
            for t_id, t_toks in topic_tokens.items():
                if jaccard_similarity(item_tokens, t_toks) >= 0.4:
                    matched_topic_id = t_id
                    break

        if matched_topic_id:
            item.topic_id = matched_topic_id
        else:
            unassigned_items.append(item)

    db.commit()

    # 4. Form new groups for unassigned items
    new_topics_created = []
    if len(unassigned_items) >= 2:
        groups = await group_items_with_gemini(unassigned_items)
        item_id_map = {item.id: item for item in unassigned_items}

        for grp in groups:
            m_ids = grp.get("item_ids", [])
            valid_members = [item_id_map[mid] for mid in m_ids if mid in item_id_map]
            if len(valid_members) < 2:
                continue

            new_topic = Topic(
                title=grp.get("title", valid_members[0].title)[:512],
                summary=None,
                is_active=True,
                created_at=now,
                updated_at=now
            )
            db.add(new_topic)
            db.flush()  # populate new_topic.id

            for member in valid_members:
                member.topic_id = new_topic.id

            new_topics_created.append(new_topic)

        db.commit()

    # 5. Refresh counts, distinct source count & check staleness on all active topics
    all_active = db.query(Topic).filter(Topic.is_active == True).all()
    converged_new_topics = []

    for t in all_active:
        members = t.items
        t.item_count = len(members)
        distinct_sources = {m.source_id for m in members}
        t.source_count = len(distinct_sources)

        # Inactivate topics whose newest member is older than 48h
        newest_fetched = max([m.fetched_at for m in members], default=t.created_at)
        if (now - newest_fetched) > timedelta(hours=48):
            t.is_active = False
        else:
            t.updated_at = newest_fetched

        if t in new_topics_created and t.source_count >= 2:
            converged_new_topics.append(t)

    db.commit()

    # 6. Generate AI summaries for up to 5 new cross-platform topics
    if converged_new_topics:
        await summarize_topics_with_gemini(converged_new_topics, db)

    total_active = db.query(Topic).filter(Topic.is_active == True).count()
    logger.info(
        f"Clustering complete: {len(new_topics_created)} new topics, "
        f"{len(converged_new_topics)} cross-platform, {total_active} total active topics."
    )

    return {
        "status": "success",
        "new_topics": len(new_topics_created),
        "cross_platform_new": len(converged_new_topics),
        "active_topics": total_active
    }


async def run_topic_clustering(db: Session) -> dict[str, Any]:
    """
    Thread-safe, concurrency-locked entry point for running topic clustering.
    Can be invoked from scheduler or triggered directly via pipeline.
    """
    if clustering_lock.locked():
        logger.info("Clustering run already in progress. Skipping duplicate execution.")
        return {"status": "skipped", "message": "Clustering run already in progress"}

    async with clustering_lock:
        return await _execute_clustering(db)
