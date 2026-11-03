import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.main import app
from backend.seed import init_db, seed_db

def test_phase3_frontend_delivery():
    print("=" * 70)
    print("PHASE 3 VERIFICATION SUITE — FRONTEND INTEGRATION & ASSET DELIVERY")
    print("=" * 70)

    init_db()
    seed_db()
    client = TestClient(app)

    # 1. Test Root Index Serving
    print("\n--- 1. Testing Root Index Serving (GET /) ---")
    resp_root = client.get("/")
    assert resp_root.status_code == 200
    assert "text/html" in resp_root.headers.get("content-type", "")
    assert "SocialPulse" in resp_root.text
    assert "network-canvas" in resp_root.text
    print("[OK] GET / serves frontend/index.html with valid HTML shell.")

    # 2. Test CSS & JS Module Delivery
    print("\n--- 2. Testing CSS & JS Static Asset Delivery ---")
    assets = [
        "/static/css/styles.css",
        "/static/js/app.js",
        "/static/js/api.js",
        "/static/js/utils.js"
    ]
    for asset in assets:
        resp = client.get(asset)
        assert resp.status_code == 200, f"Failed to load asset {asset}: {resp.status_code}"
        assert len(resp.text) > 50
        print(f"[OK] {asset:25} -> {resp.status_code} ({len(resp.text)} bytes)")

    # 3. Test Active Platform SVG Icons
    print("\n--- 3. Testing Platform SVG Icons ---")
    icons = [
        "youtube.svg", "mastodon.svg", "bluesky.svg", "google-trends.svg",
        "instagram.svg", "facebook.svg", "twitter.svg", "reddit.svg", "twitch.svg"
    ]
    for icon in icons:
        path = f"/static/assets/icons/{icon}"
        resp = client.get(path)
        assert resp.status_code == 200, f"Missing icon {icon}: {resp.status_code}"
        assert "<svg" in resp.text
        print(f"[OK] {path:35} -> 200 OK (Valid SVG)")

    print("\n" + "=" * 70)
    print("ALL PHASE 3 FRONTEND DELIVERY TESTS PASSED (100% GREEN)!")
    print("=" * 70)

if __name__ == "__main__":
    test_phase3_frontend_delivery()
