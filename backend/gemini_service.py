import os
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger("ZeroBreakout.GeminiService")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def get_gemini_analysis(symbol: str, stock_data: Dict[str, Any], signal_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generates AI-powered technical pattern breakdown and trading insights using Gemini.
    Falls back to a structured algorithmic analysis if API key is not provided or network fails.
    """
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    
    current_price = stock_data.get("current_price", 0)
    company_name = stock_data.get("company_name", symbol)
    sector = stock_data.get("sector", "General")
    ath = stock_data.get("all_time_high", 0)
    change_pct = stock_data.get("change_pct", 0)

    pattern_type = signal_data.get("pattern_type", "Consolidation / Setup") if signal_data else "Technical Setup"
    pivot_price = signal_data.get("pivot_price", current_price) if signal_data else current_price
    pct_vs_pivot = signal_data.get("percent_vs_pivot", 0.0) if signal_data else 0.0
    trigger_date = signal_data.get("trigger_date", "Recent") if signal_data else "Recent"

    # If Gemini API key is available, attempt live generation
    if api_key:
        try:
            prompt = f"""You are a senior quantitative technical analyst specializing in Indian equities (NSE).
Analyze this technical chart pattern structure for {company_name} ({symbol}) for educational and technical research purposes:
- Current Price: ₹{current_price} ({change_pct:+.2f}%)
- Sector: {sector}
- All-Time High: ₹{ath}
- Detected Pattern: {pattern_type}
- Trigger Date: {trigger_date}
- Breakout Pivot / Resistance: ₹{pivot_price}
- Distance vs Pivot: {pct_vs_pivot:+.2f}%

Provide a concise, objective technical breakdown in JSON format with these exact keys:
{{
  "summary": "1-2 sentence core technical takeaway on price structure",
  "pattern_dynamics": "2-3 sentences on market dynamics, moving average alignment, and volume behavior",
  "key_levels": {{
    "base_support": "₹XXX",
    "pivot_resistance": "₹XXX",
    "range_high": "₹XXX",
    "range_low": "₹XXX"
  }},
  "structure_trend": "Bullish Trend / High-Tight Consolidation / Key Level Retest",
  "technical_observation": "Key technical observation regarding price action around moving averages"
}}
Return only valid JSON.
"""
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800}
            }
            resp = requests.post(url, json=payload, timeout=12)
            if resp.status_code == 200:
                res_data = resp.json()
                text = res_data["candidates"][0]["content"]["parts"][0]["text"]
                clean_text = text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.startswith("```"):
                    clean_text = clean_text[3:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                clean_text = clean_text.strip()
                parsed = json.loads(clean_text)
                return {
                    "source": "gemini-ai",
                    "data": parsed
                }
        except Exception as e:
            logger.warning(f"Gemini API generation failed, falling back to rule-based analysis: {e}")

    # Fallback high-quality algorithmic technical analysis
    base_support = round(pivot_price * 0.965, 2)
    range_high = round(pivot_price * 1.05, 2)
    range_low = round(pivot_price * 0.94, 2)

    return {
        "source": "algorithmic-synthesis",
        "data": {
            "summary": f"{symbol} formed a {pattern_type} around ₹{pivot_price:.2f}. Price action reflects constructive structural development in the {sector} sector.",
            "pattern_dynamics": f"The stock has developed base consolidation near ₹{pivot_price:.2f} ({pct_vs_pivot:+.2f}% vs pivot). Primary chart support is situated at ₹{base_support:.2f}.",
            "key_levels": {
                "base_support": f"₹{base_support:.2f}",
                "pivot_resistance": f"₹{pivot_price:.2f}",
                "range_high": f"₹{range_high:.2f}",
                "range_low": f"₹{range_low:.2f}"
            },
            "structure_trend": "Bullish Technical Structure" if pct_vs_pivot >= 0 else "Pre-Breakout Consolidation",
            "technical_observation": f"Holding above base support of ₹{base_support:.2f} keeps the technical breakout structure active."
        }
    }
