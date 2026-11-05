import json
import logging
import time
from typing import Any
import google.generativeai as genai
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import TrendingItem, Category
from backend.utils.rate_limiter import gemini_rate_limiter
from backend.services.mock_ai import get_mock_ai_summary, detect_indian_location_heuristic, classify_category_heuristic
from backend.utils.translator import is_non_english

logger = logging.getLogger("socialpulse.ai_processor")

PREFERRED_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest"
]

BATCH_SIZE = 8

def get_gemini_api_key(source_category: str = "A") -> str:
    """Return GEMINI_KEY_SCRAP for category B (scraped news), otherwise GEMINI_KEY."""
    if source_category == "B" and settings.GEMINI_KEY_SCRAP:
        return settings.GEMINI_KEY_SCRAP
    return settings.GEMINI_KEY or settings.GEMINI_KEY_SCRAP


def clean_json_response(raw_text: str) -> str:
    """Strip markdown code fence wrappers from raw LLM output if present."""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def validate_location_india(loc: Any, title: str, description: str) -> str | None:
    """Validate and clean location_india string, applying heuristic if needed."""
    if loc is not None:
        if isinstance(loc, bool):
            loc = "India" if loc else None
        elif isinstance(loc, str):
            clean_loc = loc.strip()
            if clean_loc.lower() in ["null", "none", "n/a", "global", "false", ""]:
                loc = None
            elif clean_loc.lower() == "true":
                loc = "India"
            else:
                loc = clean_loc
        else:
            loc = None

    if not loc:
        loc = detect_indian_location_heuristic(f"{title} {description}")

    return loc.strip() if loc else None

def analyze_trend_with_gemini(
    title: str,
    description: str = "",
    platform_name: str = "",
    source_category: str = "A"
) -> dict[str, Any]:
    """
    Execute a structured single-item Gemini AI call (used as fallback for missing batch items).
    """
    active_key = get_gemini_api_key(source_category)
    if settings.MOCK_AI_MODE or not active_key:
        summary_text, cat_name, loc_india, is_trend = get_mock_ai_summary(platform_name.lower().replace(" ", "_"), title, description)
        return {
            "summary": summary_text,
            "category": cat_name,
            "location_india": loc_india,
            "is_platform_trend": is_trend,
            "success": True
        }

    try:
        genai.configure(api_key=active_key)
    except Exception as e:
        logger.error(f"Failed to configure Gemini API: {e}")
        cat = classify_category_heuristic(f"{title} {description}", default_source=platform_name)
        loc = detect_indian_location_heuristic(f"{title} {description}")
        return {
            "summary": "[AI Analysis Unavailable: Failed to configure Gemini API key.]",
            "category": cat,
            "location_india": loc,
            "is_platform_trend": True,
            "success": False
        }

    gemini_rate_limiter.acquire()

    cat_list_str = ", ".join([c["name"] for c in settings.CATEGORIES])
    cat_type_desc = "first-party live platform trend" if source_category == "A" else "verified third-party news coverage regarding social media trends"

    prompt = f"""You are SocialPulse AI, an expert social media trending intelligence engine.
Analyze the following {cat_type_desc} from {platform_name} and return ONLY a valid JSON object matching this schema:

{{
  "summary": "1-2 concise, factual sentences explaining why this topic is trending, the core context, and why users or developers are engaging with it.",
  "category": "Must be exactly one of: {cat_list_str}",
  "location_india": "Specific Indian city, district, or state as a string (e.g. 'Bengaluru, Karnataka', 'Mumbai', 'Kerala', 'India') ONLY if the story/topic genuinely and physically occurred in or directly targets that specific locality. If it is a nationwide Indian story without a specific local event, return 'India'. If international/global, return null. NEVER return a boolean.",
  "is_platform_trend": true or false (return true if this story is genuinely about a trending topic, viral post, creator discussion, or community event relating to {platform_name}; return false if it is off-topic general news, unrelated politics, or purely corporate financial filings)
}}

CRITICAL ACCURACY & CATEGORIZATION RULES:
1. UNVERIFIED CLAIMS & HEDGING: If the headline, source, or context contains hedging words such as 'alleged', 'unverified', 'claims', 'reportedly', 'according to a viral post', 'rumored', or refers to an anonymous social media claim (e.g. from Reddit, X, etc.) that lacks official verification, YOUR SUMMARY MUST EXPLICITLY PRESERVE THIS UNCERTAINTY. Use phrases like 'According to unverified social media claims...', 'Reportedly...', or 'An alleged claim that...'. NEVER present unconfirmed viral claims or rumors as established flat facts.
2. CREATOR & STREAMING CONTENT: Categorize video creators, streamers, Twitch drama, and gaming content as 'Gaming' or 'Entertainment'. NEVER categorize creator drama, bullying, or streaming spats as 'Health'.
3. NO GENERIC BOILERPLATE: Write unique, insightful 1-2 sentence explanations specific to the actual headline and details provided. Do not use generic template phrases like 'Major trending story centered in...'.
4. REAL LOCATIONS ONLY: location_india is ONLY filled when genuinely tied to that specific place in India. If global, international, or unmentioned, return null. Never guess or invent a location.

Platform: {platform_name}
Title/Headline: {title}
Context/Description: {description[:1200]}
"""

    for model_name in PREFERRED_MODELS:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            response = model.generate_content(prompt)
            raw_text = response.text
            cleaned = clean_json_response(raw_text)
            data = json.loads(cleaned)

            summary = data.get("summary", "").strip()
            category = data.get("category", "Technology").strip()
            location_india = validate_location_india(data.get("location_india"), title, description)
            is_platform_trend = data.get("is_platform_trend", True)

            if not summary:
                summary = f"Trending on {platform_name} with high community engagement and discussions."

            return {
                "summary": summary,
                "category": category,
                "location_india": location_india,
                "is_platform_trend": bool(is_platform_trend),
                "success": True
            }

        except Exception as e:
            last_error = str(e)
            if "429" in last_error or "404" in last_error or "503" in last_error:
                logger.warning(f"Model '{model_name}' failed ({last_error[:80]}). Trying next preferred model...")
                continue
            logger.error(f"Gemini API error with '{model_name}' for '{title[:35]}': {e}")
            continue

    cat_fallback = classify_category_heuristic(f"{title} {description}", default_source=platform_name)
    loc_fallback = detect_indian_location_heuristic(f"{title} {description}")

    return {
        "summary": "[AI analysis pending retry on next sweep]",
        "category": cat_fallback,
        "location_india": loc_fallback,
        "is_platform_trend": True,
        "success": False
    }

def analyze_batch_with_gemini(batch: list[TrendingItem]) -> dict[int, dict[str, Any]]:
    """
    Execute a batched Gemini AI call (8-10 items per call).
    Returns a dictionary mapping item.id -> analysis dict.
    Validates array length and ids, retries once on parse failure,
    and falls back to single-item calls for any missing items.
    """
    if not batch:
        return {}

    has_cat_b = any(getattr(item, "source_category", "A") == "B" for item in batch)
    active_key = get_gemini_api_key("B" if has_cat_b else "A")

    # In mock mode or missing API key, use mock AI generator
    if settings.MOCK_AI_MODE or not active_key:
        results: dict[int, dict[str, Any]] = {}
        for item in batch:
            plat = item.source.display_name if item.source else "Social Platform"
            summary_text, cat_name, loc_india, is_trend = get_mock_ai_summary(
                plat.lower().replace(" ", "_"),
                item.title,
                item.description or ""
            )
            results[item.id] = {
                "summary": summary_text,
                "category": cat_name,
                "location_india": loc_india,
                "is_platform_trend": is_trend,
                "success": True
            }
        return results

    try:
        genai.configure(api_key=active_key)
    except Exception as e:
        logger.error(f"Failed to configure Gemini API: {e}")
        return {
            item.id: {
                "summary": "[AI analysis pending retry on next sweep]",
                "category": classify_category_heuristic(f"{item.title} {item.description or ''}"),
                "location_india": detect_indian_location_heuristic(f"{item.title} {item.description or ''}"),
                "is_platform_trend": True,
                "success": False
            }
            for item in batch
        }

    cat_list_str = ", ".join([c["name"] for c in settings.CATEGORIES])
    batch_payload = [
        {
            "id": item.id,
            "title": item.title,
            "description": (item.description or "")[:400],
            "platform": item.source.display_name if item.source else "Social Platform",
            "source_category": item.source_category or "A"
        }
        for item in batch
    ]
    items_json_str = json.dumps(batch_payload, indent=2)

    prompt = f"""You are SocialPulse AI, an expert social media trending intelligence engine.
Analyze the following batch of {len(batch)} trending items and return ONLY a valid JSON array containing one object per item matching this exact schema:

[
  {{
    "id": <integer id of the item matching the input item id>,
    "summary": "1-2 concise, factual sentences explaining why this topic is trending, the core context, and why users or developers are engaging with it.",
    "category": "Must be exactly one of: {cat_list_str}",
    "location_india": "Specific Indian city, district, or state as a string (e.g. 'Bengaluru, Karnataka', 'Mumbai', 'Kerala', 'India') ONLY if the story/topic genuinely and physically occurred in or directly targets that specific locality. If it is a nationwide Indian story without a specific local event, return 'India'. If international/global, return null. NEVER guess or invent a location.",
    "is_platform_trend": true or false (return true if this story is genuinely about a trending topic, viral post, creator discussion, or community event relating to the platform; return false if it is off-topic general news, unrelated politics, or generic crime/corporate filings)
  }}
]

CRITICAL ACCURACY & CATEGORIZATION RULES:
1. UNVERIFIED CLAIMS & HEDGING: If the headline, source, or context contains hedging words such as 'alleged', 'unverified', 'claims', 'reportedly', 'according to a viral post', 'rumored', or refers to an anonymous social media claim (e.g. from Reddit, X, etc.) that lacks official verification, YOUR SUMMARY MUST EXPLICITLY PRESERVE THIS UNCERTAINTY. Use phrases like 'According to unverified social media claims...', 'Reportedly...', or 'An alleged claim that...'. NEVER present unconfirmed viral claims or rumors as established flat facts.
2. CREATOR & STREAMING CONTENT: Categorize video creators, streamers, Twitch drama, and gaming content as 'Gaming' or 'Entertainment'. NEVER categorize creator drama, bullying, or streaming spats as 'Health'.
3. NO GENERIC BOILERPLATE: Write unique, insightful 1-2 sentence explanations specific to the actual headline and details provided. Do not use generic template phrases like 'Major trending story centered in...'.
4. REAL LOCATIONS ONLY: location_india is ONLY filled when genuinely tied to that specific place in India. If global, international, or unmentioned, return null. Never guess or invent a location.
5. STRICT ID MATCHING: Every item in the input MUST have a corresponding object in the returned JSON array with the exact input "id".

ITEMS TO ANALYZE:
{items_json_str}
"""

    results: dict[int, dict[str, Any]] = {}
    batch_success = False

    # Try preferred models
    for model_name in PREFERRED_MODELS:
        try:
            # Count the batch call towards rate limiter
            gemini_rate_limiter.acquire()

            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            response = model.generate_content(prompt)
            raw_text = clean_json_response(response.text)

            # Attempt parsing
            data = None
            try:
                data = json.loads(raw_text)
            except Exception as pe:
                logger.warning(f"Batch parse failure with {model_name}: {pe}. Retrying once...")
                # Retry once on parse failure
                gemini_rate_limiter.acquire()
                retry_resp = model.generate_content(prompt)
                retry_text = clean_json_response(retry_resp.text)
                data = json.loads(retry_text)

            if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
                data = data["items"]

            if isinstance(data, list):
                item_by_id = {item.id: item for item in batch}
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    entry_id = entry.get("id")
                    if entry_id not in item_by_id:
                        continue

                    matched_item = item_by_id[entry_id]
                    summary = entry.get("summary", "").strip()
                    if not summary:
                        plat = matched_item.source.display_name if matched_item.source else "Social Platform"
                        summary = f"Trending on {plat} with high community engagement and discussions."

                    cat = entry.get("category", "Technology").strip()
                    loc = validate_location_india(entry.get("location_india"), matched_item.title, matched_item.description or "")
                    is_trend = entry.get("is_platform_trend", True)

                    results[entry_id] = {
                        "summary": summary,
                        "category": cat,
                        "location_india": loc,
                        "is_platform_trend": bool(is_trend),
                        "success": True
                    }

                batch_success = True
                break

        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "404" in err_msg or "503" in err_msg:
                logger.warning(f"Batch model '{model_name}' failed ({err_msg[:80]}). Trying next preferred model...")
                continue
            logger.error(f"Gemini API error during batch with '{model_name}': {e}")
            continue

    # Fall back to single-item calls only for items missing from the response
    for item in batch:
        if item.id not in results:
            plat = item.source.display_name if item.source else "Social Platform"
            src_cat = item.source_category or "A"
            logger.info(f"Item {item.id} missing from batch response. Falling back to single-item call...")
            single_res = analyze_trend_with_gemini(
                title=item.title,
                description=item.description or "",
                platform_name=plat,
                source_category=src_cat
            )
            results[item.id] = single_res

    return results

async def process_unprocessed_items(db: Session, limit: int = 50) -> tuple[int, int, int]:
    """
    Process un-summarized trending items in batches of 8-10 with Gemini AI.
    Returns: (total_attempted, succeeded, failed)
    """
    items = db.query(TrendingItem).filter(
        TrendingItem.ai_processed == False
    ).limit(limit).all()

    if not items:
        return (0, 0, 0)

    # Pre-cache category names
    all_cats = db.query(Category).all()
    cat_map = {c.name.lower(): c for c in all_cats}
    default_cat = cat_map.get("other") or (all_cats[0] if all_cats else None)

    succeeded = 0
    failed = 0

    # Process items in batches of 8
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i:i + BATCH_SIZE]
        batch_results = analyze_batch_with_gemini(batch)

        for item in batch:
            analysis = batch_results.get(item.id)
            if not analysis:
                item.ai_processed = False
                failed += 1
                continue

            src_cat = item.source_category or "A"

            # Translation check: ensure title is in English Latin script
            if is_non_english(item.title):
                eng_title = analysis.get("english_title")
                if eng_title and not is_non_english(eng_title):
                    item.title = eng_title
                else:
                    try:
                        from backend.utils.translator import translate_single_to_english
                        trans = await translate_single_to_english(item.title)
                        if trans and not is_non_english(trans):
                            item.title = trans
                    except Exception:
                        pass

            # Relevance filter: only purge off-topic items if platform has a healthy cushion of items (> 8)
            if src_cat == "B" and analysis.get("is_platform_trend") is False:
                src_count = db.query(TrendingItem).filter(TrendingItem.source_id == item.source_id).count()
                if src_count > 8:
                    logger.info(f"Purging off-topic news item: '{item.title[:40]}'")
                    db.delete(item)
                    succeeded += 1
                    continue
                else:
                    logger.info(f"Retaining off-topic news item to maintain minimum platform feed density: '{item.title[:40]}'")

            item.ai_summary = analysis.get("summary")
            item.location_india = analysis.get("location_india")

            assigned_cat_name = analysis.get("category", "Technology").lower()
            matched_cat = cat_map.get(assigned_cat_name, default_cat)
            if matched_cat:
                item.category_id = matched_cat.id

            if analysis.get("success", False):
                item.ai_processed = True
                succeeded += 1
            else:
                item.ai_processed = False
                failed += 1

        db.commit()

    return (len(items), succeeded, failed)
