import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from starlette.testclient import TestClient
from backend.main import app
from backend.seed_data import seed_database_if_empty

def run_integration_tests():
    print("Seeding test database...")
    seed_database_if_empty()

    client = TestClient(app)

    print("\n1. Testing GET /api/signals...")
    resp = client.get("/api/signals")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert "signals" in data
    assert data["count"] > 0
    print(f"   [OK] Returned {data['count']} signals")

    print("\n2. Testing GET /api/signals with pattern filter...")
    resp = client.get("/api/signals?pattern=All-Time+High+Breakout")
    assert resp.status_code == 200
    ath_data = resp.json()
    print(f"   [OK] Returned {ath_data['count']} ATH Breakout signals")

    print("\n3. Testing GET /api/signals with search query...")
    resp = client.get("/api/signals?search=IFCI")
    assert resp.status_code == 200
    search_data = resp.json()
    assert search_data["count"] > 0
    print(f"   [OK] Search query matched {search_data['count']} items")

    print("\n4. Testing GET /api/stocks/IFCI/setup...")
    resp = client.get("/api/stocks/IFCI/setup")
    assert resp.status_code == 200
    setup_data = resp.json()
    assert setup_data["symbol"] == "IFCI"
    assert "current_price" in setup_data
    print(f"   [OK] IFCI Setup loaded: Price=Rs {setup_data['current_price']}, ATH=Rs {setup_data['all_time_high']}")

    print("\n5. Testing GET /api/stocks/IFCI/history (1Y & 5Y)...")
    resp_1y = client.get("/api/stocks/IFCI/history?range=1Y")
    assert resp_1y.status_code == 200
    h1y = resp_1y.json()
    assert len(h1y["candles"]) > 0
    assert "sma_20" in h1y["candles"][-1]
    assert "sma_50" in h1y["candles"][-1]

    resp_5y = client.get("/api/stocks/IFCI/history?range=5Y")
    assert resp_5y.status_code == 200
    h5y = resp_5y.json()
    assert len(h5y["candles"]) > 100
    print(f"   [OK] 1Y Candles: {len(h1y['candles'])}, History Candles: {len(h5y['candles'])} with SMAs calculated")

    print("\n6. Testing Watchlist toggle & retrieval...")
    # Clean prior state if any
    from backend.database import get_connection
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM watchlist WHERE user_id = 'default_user' AND symbol = 'IFCI'")
    conn.close()

    resp_add = client.post("/api/watchlist/IFCI")
    assert resp_add.status_code == 200
    assert resp_add.json()["in_watchlist"] is True

    resp_wl = client.get("/api/watchlist")
    assert resp_wl.status_code == 200
    wl_items = resp_wl.json()["items"]
    assert any(item["symbol"] == "IFCI" for item in wl_items)
    print(f"   [OK] Watchlist contains {len(wl_items)} items including IFCI")

    print("\n7. Testing Gemini AI Analysis endpoint...")
    resp_ai = client.get("/api/stocks/IFCI/ai-analysis")
    assert resp_ai.status_code == 200
    ai_data = resp_ai.json()
    assert "data" in ai_data
    assert "summary" in ai_data["data"]
    print(f"   [OK] AI Breakdown source: {ai_data.get('source')}")

    print("\n8. Testing GET / (Frontend root)...")
    resp_root = client.get("/")
    assert resp_root.status_code == 200
    assert "ZeroBreakout" in resp_root.text
    print("   [OK] Frontend index.html served successfully")

    print("\n9. Testing GET /api/stats...")
    resp_stats = client.get("/api/stats")
    assert resp_stats.status_code == 200
    stats = resp_stats.json()
    print(f"   [OK] Tracked Stocks: {stats['total_stocks_tracked']}, Active Signals: {stats['total_active_signals']}")

    print("\n10. Testing GET /.well-known/assetlinks.json (TWA / Play Store)...")
    resp_al = client.get("/.well-known/assetlinks.json")
    assert resp_al.status_code == 200
    assert "application/json" in resp_al.headers.get("content-type", "")
    al_data = resp_al.json()
    assert isinstance(al_data, list)
    assert len(al_data) > 0
    assert al_data[0]["target"]["namespace"] == "android_app"
    print(f"   [OK] Digital Asset Links served correctly with Content-Type application/json")

    print("\n==========================================")
    print("ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("==========================================")

if __name__ == "__main__":
    run_integration_tests()
