import json
import re
from pathlib import Path

MOCK_AI_FILE = Path(__file__).resolve().parent.parent / "mock" / "mock_ai_summaries.json"

INDIAN_LOCATIONS = [
    # States & Union Territories (longer names)
    ("Andaman and Nicobar Islands", "Andaman and Nicobar Islands"),
    ("Arunachal Pradesh", "Arunachal Pradesh"),
    ("Himachal Pradesh", "Himachal Pradesh"),
    ("Jammu and Kashmir", "Jammu & Kashmir"),
    ("Jammu & Kashmir", "Jammu & Kashmir"),
    ("Madhya Pradesh", "Madhya Pradesh"),
    ("Andhra Pradesh", "Andhra Pradesh"),
    ("Uttar Pradesh", "Uttar Pradesh"),
    ("Uttarakhand", "Uttarakhand"),
    ("West Bengal", "West Bengal"),
    ("Tamil Nadu", "Tamil Nadu"),
    ("Chhattisgarh", "Chhattisgarh"),
    ("Maharashtra", "Maharashtra"),
    ("Chandigarh", "Chandigarh"),
    ("Puducherry", "Puducherry"),
    ("Pondicherry", "Puducherry"),
    ("Telangana", "Telangana"),
    ("Karnataka", "Karnataka"),
    ("Rajasthan", "Rajasthan"),
    ("Meghalaya", "Meghalaya"),
    ("Jharkhand", "Jharkhand"),
    ("Himachal", "Himachal Pradesh"),
    ("Nagaland", "Nagaland"),
    ("Gujarat", "Gujarat"),
    ("Haryana", "Haryana"),
    ("Manipur", "Manipur"),
    ("Mizoram", "Mizoram"),
    ("Tripura", "Tripura"),
    ("Punjab", "Punjab"),
    ("Odisha", "Odisha"),
    ("Orissa", "Odisha"),
    ("Kerala", "Kerala"),
    ("Sikkim", "Sikkim"),
    ("Ladakh", "Ladakh"),
    ("Assam", "Assam"),
    ("Bihar", "Bihar"),
    ("Delhi", "New Delhi"),
    ("Goa", "Goa"),

    # Delhi NCR & Northern Hubs
    ("Greater Noida", "Greater Noida, Uttar Pradesh"),
    ("New Delhi", "New Delhi"),
    ("Gurugram", "Gurugram, Haryana"),
    ("Gurgaon", "Gurugram, Haryana"),
    ("Faridabad", "Faridabad, Haryana"),
    ("Ghaziabad", "Ghaziabad, Uttar Pradesh"),
    ("Noida", "Noida, Uttar Pradesh"),

    # Telangana Districts & Cities
    ("Hanamkonda", "Hanamkonda, Telangana"),
    ("Karimnagar", "Karimnagar, Telangana"),
    ("Nizamabad", "Nizamabad, Telangana"),
    ("Ramagundam", "Ramagundam, Telangana"),
    ("Mahbubnagar", "Mahbubnagar, Telangana"),
    ("Warangal", "Warangal, Telangana"),
    ("Khammam", "Khammam, Telangana"),
    ("Siddipet", "Siddipet, Telangana"),
    ("Nalgonda", "Nalgonda, Telangana"),
    ("Suryapet", "Suryapet, Telangana"),
    ("Mancherial", "Mancherial, Telangana"),
    ("Adilabad", "Adilabad, Telangana"),
    ("Secunderabad", "Hyderabad, Telangana"),
    ("Hyderabad", "Hyderabad, Telangana"),

    # Andhra Pradesh Cities & Districts
    ("Visakhapatnam", "Visakhapatnam, Andhra Pradesh"),
    ("Rajahmundry", "Rajahmundry, Andhra Pradesh"),
    ("Vijayawada", "Vijayawada, Andhra Pradesh"),
    ("Anantapur", "Anantapur, Andhra Pradesh"),
    ("Kakinada", "Kakinada, Andhra Pradesh"),
    ("Tirupati", "Tirupati, Andhra Pradesh"),
    ("Kurnool", "Kurnool, Andhra Pradesh"),
    ("Nellore", "Nellore, Andhra Pradesh"),
    ("Guntur", "Guntur, Andhra Pradesh"),
    ("Kadapa", "Kadapa, Andhra Pradesh"),
    ("Vizag", "Visakhapatnam, Andhra Pradesh"),
    ("Ongole", "Ongole, Andhra Pradesh"),
    ("Eluru", "Eluru, Andhra Pradesh"),

    # Karnataka Cities & Districts
    ("Chhatrapati Sambhajinagar", "Chhatrapati Sambhajinagar, Maharashtra"),
    ("Pimpri-Chinchwad", "Pune, Maharashtra"),
    ("Navi Mumbai", "Navi Mumbai, Maharashtra"),
    ("Bengaluru", "Bengaluru, Karnataka"),
    ("Bangalore", "Bengaluru, Karnataka"),
    ("Kalaburagi", "Kalaburagi, Karnataka"),
    ("Davanagere", "Davanagere, Karnataka"),
    ("Mangaluru", "Mangaluru, Karnataka"),
    ("Mangalore", "Mangaluru, Karnataka"),
    ("Hubballi", "Hubballi, Karnataka"),
    ("Belagavi", "Belagavi, Karnataka"),
    ("Shivamogga", "Shivamogga, Karnataka"),
    ("Gulbarga", "Kalaburagi, Karnataka"),
    ("Dharwad", "Hubballi, Karnataka"),
    ("Belgaum", "Belagavi, Karnataka"),
    ("Ballari", "Ballari, Karnataka"),
    ("Bellary", "Ballari, Karnataka"),
    ("Shimoga", "Shivamogga, Karnataka"),
    ("Mysuru", "Mysuru, Karnataka"),
    ("Mysore", "Mysuru, Karnataka"),
    ("Tumkur", "Tumakuru, Karnataka"),
    ("Tumakuru", "Tumakuru, Karnataka"),
    ("Udupi", "Udupi, Karnataka"),
    ("Bidar", "Bidar, Karnataka"),

    # Maharashtra Cities
    ("Aurangabad", "Chhatrapati Sambhajinagar, Maharashtra"),
    ("Vasai-Virar", "Vasai-Virar, Maharashtra"),
    ("Ahmednagar", "Ahmednagar, Maharashtra"),
    ("Chandrapur", "Chandrapur, Maharashtra"),
    ("Dombivli", "Dombivli, Maharashtra"),
    ("Amravati", "Amravati, Maharashtra"),
    ("Kolhapur", "Kolhapur, Maharashtra"),
    ("Jalgaon", "Jalgaon, Maharashtra"),
    ("Solapur", "Solapur, Maharashtra"),
    ("Nagpur", "Nagpur, Maharashtra"),
    ("Nashik", "Nashik, Maharashtra"),
    ("Nanded", "Nanded, Maharashtra"),
    ("Kalyan", "Kalyan, Maharashtra"),
    ("Sangli", "Sangli, Maharashtra"),
    ("Mumbai", "Mumbai, Maharashtra"),
    ("Bombay", "Mumbai, Maharashtra"),
    ("Thane", "Thane, Maharashtra"),
    ("Akola", "Akola, Maharashtra"),
    ("Latur", "Latur, Maharashtra"),
    ("Dhule", "Dhule, Maharashtra"),
    ("Pune", "Pune, Maharashtra"),

    # Tamil Nadu Cities
    ("Thiruvananthapuram", "Thiruvananthapuram, Kerala"),
    ("Tiruchirappalli", "Tiruchirappalli, Tamil Nadu"),
    ("Tirunelveli", "Tirunelveli, Tamil Nadu"),
    ("Thoothukudi", "Thoothukudi, Tamil Nadu"),
    ("Coimbatore", "Coimbatore, Tamil Nadu"),
    ("Thanjavur", "Thanjavur, Tamil Nadu"),
    ("Tiruppur", "Tiruppur, Tamil Nadu"),
    ("Dindigul", "Dindigul, Tamil Nadu"),
    ("Tuticorin", "Thoothukudi, Tamil Nadu"),
    ("Kozhikode", "Kozhikode, Kerala"),
    ("Madurai", "Madurai, Tamil Nadu"),
    ("Vellore", "Vellore, Tamil Nadu"),
    ("Chennai", "Chennai, Tamil Nadu"),
    ("Madras", "Chennai, Tamil Nadu"),
    ("Trichy", "Tiruchirappalli, Tamil Nadu"),
    ("Salem", "Salem, Tamil Nadu"),
    ("Erode", "Erode, Tamil Nadu"),
    ("Ooty", "Ooty, Tamil Nadu"),

    # Kerala Cities & Districts
    ("Trivandrum", "Thiruvananthapuram, Kerala"),
    ("Alappuzha", "Alappuzha, Kerala"),
    ("Pathanamthitta", "Pathanamthitta, Kerala"),
    ("Malappuram", "Malappuram, Kerala"),
    ("Kasaragod", "Kasaragod, Kerala"),
    ("Kottayam", "Kottayam, Kerala"),
    ("Palakkad", "Palakkad, Kerala"),
    ("Thrissur", "Thrissur, Kerala"),
    ("Wayanad", "Wayanad, Kerala"),
    ("Alleppey", "Alappuzha, Kerala"),
    ("Calicut", "Kozhikode, Kerala"),
    ("Kannur", "Kannur, Kerala"),
    ("Kollam", "Kollam, Kerala"),
    ("Kochi", "Kochi, Kerala"),
    ("Cochin", "Kochi, Kerala"),
    ("Malabar", "Malabar, Kerala"),

    # Gujarat Cities
    ("Gandhinagar", "Gandhinagar, Gujarat"),
    ("Bhavnagar", "Bhavnagar, Gujarat"),
    ("Ahmedabad", "Ahmedabad, Gujarat"),
    ("Vadodara", "Vadodara, Gujarat"),
    ("Jamnagar", "Jamnagar, Gujarat"),
    ("Junagadh", "Junagadh, Gujarat"),
    ("Rajkot", "Rajkot, Gujarat"),
    ("Baroda", "Vadodara, Gujarat"),
    ("Surat", "Surat, Gujarat"),
    ("Anand", "Anand, Gujarat"),
    ("Morbi", "Morbi, Gujarat"),

    # Uttar Pradesh Cities
    ("Muzaffarnagar", "Muzaffarnagar, Uttar Pradesh"),
    ("Shahjahanpur", "Shahjahanpur, Uttar Pradesh"),
    ("Prayagraj", "Prayagraj, Uttar Pradesh"),
    ("Saharanpur", "Saharanpur, Uttar Pradesh"),
    ("Moradabad", "Moradabad, Uttar Pradesh"),
    ("Gorakhpur", "Gorakhpur, Uttar Pradesh"),
    ("Allahabad", "Prayagraj, Uttar Pradesh"),
    ("Firozabad", "Firozabad, Uttar Pradesh"),
    ("Bareilly", "Bareilly, Uttar Pradesh"),
    ("Varanasi", "Varanasi, Uttar Pradesh"),
    ("Lucknow", "Lucknow, Uttar Pradesh"),
    ("Mathura", "Mathura, Uttar Pradesh"),
    ("Ayodhya", "Ayodhya, Uttar Pradesh"),
    ("Aligarh", "Aligarh, Uttar Pradesh"),
    ("Kanpur", "Kanpur, Uttar Pradesh"),
    ("Meerut", "Meerut, Uttar Pradesh"),
    ("Banaras", "Varanasi, Uttar Pradesh"),
    ("Jhansi", "Jhansi, Uttar Pradesh"),
    ("Kashi", "Varanasi, Uttar Pradesh"),
    ("Agra", "Agra, Uttar Pradesh"),

    # Madhya Pradesh Cities
    ("Chhindwara", "Chhindwara, Madhya Pradesh"),
    ("Burhanpur", "Burhanpur, Madhya Pradesh"),
    ("Jabalpur", "Jabalpur, Madhya Pradesh"),
    ("Gwalior", "Gwalior, Madhya Pradesh"),
    ("Khandwa", "Khandwa, Madhya Pradesh"),
    ("Ratlam", "Ratlam, Madhya Pradesh"),
    ("Ujjain", "Ujjain, Madhya Pradesh"),
    ("Bhopal", "Bhopal, Madhya Pradesh"),
    ("Indore", "Indore, Madhya Pradesh"),
    ("Sagar", "Sagar, Madhya Pradesh"),
    ("Dewas", "Dewas, Madhya Pradesh"),
    ("Satna", "Satna, Madhya Pradesh"),
    ("Rewa", "Rewa, Madhya Pradesh"),

    # Rajasthan Cities
    ("Sri Ganganagar", "Sri Ganganagar, Rajasthan"),
    ("Chittorgarh", "Chittorgarh, Rajasthan"),
    ("Bhilwara", "Bhilwara, Rajasthan"),
    ("Bharatpur", "Bharatpur, Rajasthan"),
    ("Bikaner", "Bikaner, Rajasthan"),
    ("Udaipur", "Udaipur, Rajasthan"),
    ("Jodhpur", "Jodhpur, Rajasthan"),
    ("Jaipur", "Jaipur, Rajasthan"),
    ("Alwar", "Alwar, Rajasthan"),
    ("Ajmer", "Ajmer, Rajasthan"),
    ("Sikar", "Sikar, Rajasthan"),
    ("Kota", "Kota, Rajasthan"),

    # Punjab & Haryana
    ("Yamunanagar", "Yamunanagar, Haryana"),
    ("Bahadurgarh", "Bahadurgarh, Haryana"),
    ("Panchkula", "Panchkula, Haryana"),
    ("Jalandhar", "Jalandhar, Punjab"),
    ("Ludhiana", "Ludhiana, Punjab"),
    ("Amritsar", "Amritsar, Punjab"),
    ("Bathinda", "Bathinda, Punjab"),
    ("Patiala", "Patiala, Punjab"),
    ("Panipat", "Panipat, Haryana"),
    ("Sonipat", "Sonipat, Haryana"),
    ("Ambala", "Ambala, Haryana"),
    ("Rohtak", "Rohtak, Haryana"),
    ("Karnal", "Karnal, Haryana"),
    ("Mohali", "Mohali, Punjab"),
    ("Hisar", "Hisar, Haryana"),

    # West Bengal & East
    ("Bhubaneswar", "Bhubaneswar, Odisha"),
    ("Muzaffarpur", "Muzaffarpur, Bihar"),
    ("Darjeeling", "Darjeeling, West Bengal"),
    ("Jamshedpur", "Jamshedpur, Jharkhand"),
    ("Hazaribagh", "Hazaribagh, Jharkhand"),
    ("Kharagpur", "Kharagpur, West Bengal"),
    ("Bhagalpur", "Bhagalpur, Bihar"),
    ("Durgapur", "Durgapur, West Bengal"),
    ("Siliguri", "Siliguri, West Bengal"),
    ("Rourkela", "Rourkela, Odisha"),
    ("Asansol", "Asansol, West Bengal"),
    ("Dhanbad", "Dhanbad, Jharkhand"),
    ("Kolkata", "Kolkata, West Bengal"),
    ("Calcutta", "Kolkata, West Bengal"),
    ("Cuttack", "Cuttack, Odisha"),
    ("Deoghar", "Deoghar, Jharkhand"),
    ("Bokaro", "Bokaro, Jharkhand"),
    ("Howrah", "Howrah, West Bengal"),
    ("Ranchi", "Ranchi, Jharkhand"),
    ("Purnia", "Purnia, Bihar"),
    ("Patna", "Patna, Bihar"),
    ("Gaya", "Gaya, Bihar"),
    ("Puri", "Puri, Odisha"),

    # Northeast & Hill States
    ("Dharamshala", "Dharamshala, Himachal Pradesh"),
    ("Rishikesh", "Rishikesh, Uttarakhand"),
    ("Dibrugarh", "Dibrugarh, Assam"),
    ("Guwahati", "Guwahati, Assam"),
    ("Haridwar", "Haridwar, Uttarakhand"),
    ("Dehradun", "Dehradun, Uttarakhand"),
    ("Shillong", "Shillong, Meghalaya"),
    ("Agartala", "Agartala, Tripura"),
    ("Silchar", "Silchar, Assam"),
    ("Srinagar", "Srinagar, Jammu & Kashmir"),
    ("Shimla", "Shimla, Himachal Pradesh"),
    ("Manali", "Manali, Himachal Pradesh"),
    ("Kashmir", "Jammu & Kashmir"),
    ("Aizawl", "Aizawl, Mizoram"),
    ("Gangtok", "Gangtok, Sikkim"),
    ("Imphal", "Imphal, Manipur"),
    ("Kohima", "Kohima, Nagaland"),
    ("Jammu", "Jammu, Jammu & Kashmir"),
    ("Kullu", "Kullu, Himachal Pradesh"),
    ("Solan", "Solan, Himachal Pradesh"),

    # Chhattisgarh & Goa
    ("Rajnandgaon", "Rajnandgaon, Chhattisgarh"),
    ("Bilaspur", "Bilaspur, Chhattisgarh"),
    ("Bhilai", "Bhilai, Chhattisgarh"),
    ("Raipur", "Raipur, Chhattisgarh"),
    ("Panaji", "Panaji, Goa"),
    ("Margao", "Margao, Goa"),

    # Generic Fallback
    ("India", "India"),
]

# Ensure longer location names are matched first to avoid substring shadowing
SORTED_INDIAN_LOCATIONS = sorted(INDIAN_LOCATIONS, key=lambda x: len(x[0]), reverse=True)

CATEGORY_KEYWORDS = [
    ("Politics", [
        "minister", "ministers", "ministry", "prime minister", "chief minister",
        "cabinet minister", "union minister", "delhi cm", "up cm", "bjp", "congress",
        "aap", "tmc", "dmk", "tdp", "ysrcp", "brs", "sp", "bsp", "rjd", "jdu", "cpim",
        "election", "elections", "vote", "voter", "voters", "voting", "voter list",
        "ballot", "evm", "parliament", "lok sabha", "rajya sabha", "supreme court",
        "high court", "court verdict", "court order", "court ruling", "court notice", "judiciary",
        "government", "governance", "policy", "modi", "rahul gandhi", "kejriwal",
        "amit shah", "nara lokesh", "yogi", "stalin", "siddaramaiah", "mamata", "nitish",
        "member of parliament", "mp election", "mla", "parliament bill",
        "legislative bill", "constitution", "assembly", "cabinet", "protest rally",
        "political rally", "political party", "political speech", "political campaign",
        "opposition leader", "ruling party", "it rules", "blocking order", "takedown notice",
        "aatmanirbhar", "sanatan", "neet", "manifesto", "coalition", "police", "fir",
        "custody", "bail", "cbi", "ed", "nia", "governor", "collector", "ias", "ips",
        "panchayat", "municipal", "dharna", "spokesperson", "nda", "india bloc", "by-poll",
        "constituency", "misinformation", "deepfake", "fact check", "it cell",
        "[trending in news]"
    ]),
    ("Health", [
        "covid", "virus", "health", "hospital", "doctor", "medicine", "vaccine",
        "cancer", "disease", "aiims", "mental health", "diet", "surgery", "outbreak",
        "medical", "dengue", "nipah", "epidemic", "clinic", "patient", "wellness",
        "fitness", "w.h.o.", "world health organization", "nutrition", "pharma"
    ]),
    ("Sports", [
        "cricket", "match", "tournament", "ipl", "bcci", "virat", "rohit", "dhoni",
        "football", "goal", "player", "athlete", "olympics", "medal", "trophy",
        "championship", "tennis", "badminton", "chess", "stadium", "world cup",
        "league", "wicket", "sixer", "score", "batsman", "bowler", "fifa", "isl"
    ]),
    ("Entertainment", [
        "movie", "film", "trailer", "teaser", "actor", "actress", "bollywood",
        "tollywood", "kollywood", "song", "music", "concert", "box office", "netflix",
        "ott", "cinema", "star", "episode", "season", "album", "comedy", "theatrical",
        "premiere", "shah rukh", "salman", "vijay", "prabhas", "deepika", "oscars"
    ]),
    ("Gaming", [
        "game", "gameplay", "streamer", "streaming", "stream", "twitch", "esports", "gta", "playstation",
        "xbox", "valve", "steam", "nintendo", "discord", "rpg", "fps", "gamer",
        "dota", "counter-strike", "bgmi", "pubg", "roblox", "minecraft"
    ]),
    ("Business", [
        "stock", "market", "sensex", "nifty", "rbi", "sebi", "economy", "bank",
        "startup", "funding", "investor", "earnings", "inflation", "finance",
        "valuation", "acquisition", "rupee", "crypto", "revenue", "fiscal", "gdp",
        "trade", "hdfc", "tcs", "reliance", "adani", "shares", "ipo"
    ]),
    ("Science", [
        "space", "isro", "nasa", "satellite", "rocket", "physics", "quantum",
        "biology", "research", "scientist", "telescope", "climate", "astronomy",
        "chemistry", "laboratory", "mission", "chandrayaan", "gaganyaan", "aditya"
    ]),
    ("Breaking News", [
        "alert", "breaking", "urgent", "accident", "blast", "crash", "disaster",
        "cyclone", "earthquake", "flood", "rescue", "collapse", "emergency", "warning",
        "death", "fire", "casualty", "landslide"
    ]),
    ("Culture", [
        "festival", "diwali", "holi", "eid", "puja", "ganesh", "chaturthi", "heritage",
        "temple", "tradition", "history", "art", "museum", "classical", "culture",
        "ritual", "spiritual", "navratri", "kumbh"
    ]),
    ("Lifestyle", [
        "fashion", "food", "travel", "recipe", "wedding", "tourism", "trend",
        "vlog", "style", "culinary", "destination", "luxury", "beauty", "outfit"
    ]),
    ("Technology", [
        "ai", "software", "code", "app", "python", "developer", "chip", "linux",
        "algorithm", "cybersecurity", "gadget", "cloud", "smartphone", "open source",
        "google", "apple", "microsoft", "meta", "nvidia", "github", "hardware"
    ])
]

def detect_indian_location_heuristic(text: str) -> str | None:
    """Detect if title or description mentions a genuine Indian city, state, or key institution."""
    if not text:
        return None
    for keyword, loc_label in SORTED_INDIAN_LOCATIONS:
        if re.search(rf"\b{re.escape(keyword)}\b", text, re.IGNORECASE):
            return loc_label
    return None

def classify_category_heuristic(text: str, default_source: str = "") -> str:
    """Classify text into one of the 12 taxonomy categories based on keywords."""
    if not text:
        text = ""
    lower_text = text.lower()

    for cat_name, keywords in CATEGORY_KEYWORDS:
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", lower_text):
                return cat_name

    # Source-based defaults if no keyword match
    source_lower = default_source.lower()
    if "[trending in news]" in lower_text or "categoryid=25" in lower_text:
        return "Politics"
    if "twitch" in source_lower:
        return "Gaming"
    if any(s in source_lower for s in ["_news", "news"]):
        return "Politics"
    if "youtube" in source_lower:
        return "Entertainment"
    if "google_trends" in source_lower:
        return "Breaking News"
    if any(s in source_lower for s in ["hackernews", "devto", "lemmy"]):
        return "Technology"
    if any(s in source_lower for s in ["twitter", "facebook", "reddit", "instagram"]):
        return "Culture"

    return "Other"

def get_mock_ai_summary(platform_slug: str, title: str = "", description: str = "") -> tuple[str, str, str | None, bool]:
    """
    Return heuristic/template summary, category tag, location_india, and is_platform_trend.
    Returns: (summary_text, category_name, location_india, is_platform_trend)
    """
    full_text = f"{title} {description}".strip()
    loc = detect_indian_location_heuristic(full_text)
    cat = classify_category_heuristic(full_text, default_source=platform_slug)

    summary = f"Trending on {platform_slug.replace('_', ' ').title()} with active community engagement and viral discussions across India."
    if loc:
        summary = f"Major trending story centered in {loc} sparking widespread conversational reach and public discussion."

    return (summary, cat, loc, True)
