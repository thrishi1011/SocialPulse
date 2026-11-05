import asyncio
import json
import logging
import unicodedata
from typing import Iterable
import httpx

from backend.config import settings
from backend.utils.rate_limiter import gemini_rate_limiter

logger = logging.getLogger("socialpulse.translator")

# In-memory translation cache to avoid duplicate API calls
_TRANSLATION_CACHE: dict[str, str] = {
    # Pre-seed common regional Indian trends and names for instant zero-latency resolution
    "எஸ். பி. வேலுமணி": "S. P. Velumani",
    "संजय राउत": "Sanjay Raut",
    "శని దేవుడు": "Lord Shani",
    "ইমরান খান": "Imran Khan",
    "क्राइम थ्रिलर": "Crime Thriller",
    "రవితేజ": "Ravi Teja",
    "தவெக": "TVK Party",
    "மோடி": "Narendra Modi",
    "राहुल गांधी": "Rahul Gandhi",
    "केजरीवाल": "Arvind Kejriwal",
}

def is_non_english(text: str) -> bool:
    """
    Returns True if the text contains non-Latin characters (Devanagari, Tamil, Telugu,
    Bengali, Gujarati, Kannada, Malayalam, Arabic, etc.).
    """
    if not text:
        return False
    for ch in text:
        code = ord(ch)
        # Indic scripts block range: 0x0900 (Devanagari) to 0x0DFF (Malayalam/Sinhala)
        if 0x0900 <= code <= 0x0DFF:
            return True
        # Additional scripts (Gurmukhi, Thai, etc.) or non-Latin letter codes
        if code > 0x024F and unicodedata.category(ch).startswith("L"):
            return True
    return False

async def _translate_with_mymemory(client: httpx.AsyncClient, text: str) -> str | None:
    """Translate or transliterate using MyMemory free API."""
    try:
        # Detect or use autodetect pair with English target
        resp = await client.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": "autodetect|en"},
            timeout=5.0
        )
        if resp.status_code == 200:
            data = resp.json()
            trans = data.get("responseData", {}).get("translatedText")
            if trans and not is_non_english(trans):
                # Clean up HTML entities if any
                import html
                return html.unescape(trans).strip()
    except Exception as e:
        logger.debug(f"MyMemory translation fallback failed for '{text}': {e}")
    return None

async def _translate_batch_with_gemini(texts: list[str]) -> dict[str, str]:
    """Translate a batch of non-English strings into clean English using Gemini AI."""
    active_key = settings.GEMINI_KEY_SCRAP or settings.GEMINI_KEY
    if not active_key or settings.MOCK_AI_MODE:
        return {}

    try:
        import google.generativeai as genai
        genai.configure(api_key=active_key)
    except Exception as e:
        logger.error(f"Failed to configure Gemini for translation: {e}")
        return {}

    prompt = f"""You are a professional multilingual translator and social media trending news expert.
Translate or transliterate the following trending topics/news headlines from their original language into clean, standard, natural English:
- If it is a person's name or place, transliterate to their recognized English Latin spelling (e.g., 'संजय राउत' -> 'Sanjay Raut', 'எஸ். பி. வேலுமணி' -> 'S. P. Velumani').
- If it is a topic/phrase/movie genre, translate to standard English (e.g., 'क्राइम थ्रिलर' -> 'Crime Thriller', 'శని దேవుడు' -> 'Lord Shani').
- Return ONLY a valid JSON object mapping each input string to its English equivalent.

INPUT STRINGS:
{json.dumps(texts, ensure_ascii=False, indent=2)}
"""

    gemini_rate_limiter.acquire()
    models_to_try = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-3.7-flash",
        "gemini-3.5-flash-lite"
    ]

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={"response_mime_type": "application/json"}
            )
            resp = model.generate_content(prompt)
            raw = resp.text.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            mapping = json.loads(raw.strip())
            if isinstance(mapping, dict):
                return {k: str(v).strip() for k, v in mapping.items() if v}
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower():
                logger.warning("Gemini translation quota reached (429). Falling back to offline translation.")
                break
            logger.warning(f"Translation with {model_name} failed: {e}. Trying next...")
            continue

    return {}

async def translate_trends_to_english(texts: Iterable[str]) -> dict[str, str]:
    """
    Given an iterable of text strings, identify any non-English items and return a dictionary
    mapping original string -> translated English string.
    English strings are left as-is (mapped to themselves).
    """
    result: dict[str, str] = {}
    needed: list[str] = []

    for t in texts:
        clean = (t or "").strip()
        if not clean:
            continue
        if not is_non_english(clean):
            result[clean] = clean
        elif clean in _TRANSLATION_CACHE:
            result[clean] = _TRANSLATION_CACHE[clean]
        else:
            needed.append(clean)

    if not needed:
        return result

    # 1. Try batch translation with Gemini
    gemini_translations = await _translate_batch_with_gemini(needed)
    for orig, trans in gemini_translations.items():
        if trans and not is_non_english(trans):
            result[orig] = trans
            _TRANSLATION_CACHE[orig] = trans

    # 2. For any still missing, use MyMemory as fallback
    missing = [t for t in needed if t not in result]
    if missing:
        async with httpx.AsyncClient(timeout=6.0) as client:
            for text in missing:
                trans = await _translate_with_mymemory(client, text)
                if trans:
                    result[text] = trans
                    _TRANSLATION_CACHE[text] = trans
                else:
                    # Fallback transliteration or title cleanup
                    result[text] = text

    return result

async def translate_single_to_english(text: str) -> str:
    """Convenience helper to translate a single string to English."""
    clean = (text or "").strip()
    if not clean or not is_non_english(clean):
        return clean
    mapping = await translate_trends_to_english([clean])
    return mapping.get(clean, clean)
