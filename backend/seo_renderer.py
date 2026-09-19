import os
import re
import json
import html
from datetime import datetime
from typing import Optional, Dict, Any, List

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
INDEX_HTML_PATH = os.path.join(FRONTEND_DIR, "index.html")

BASE_URL = "https://www.zerobreakout.in"

def load_base_template() -> str:
    """Loads the base index.html file"""
    if os.path.exists(INDEX_HTML_PATH):
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "<html><body>ZeroBreakout Terminal</body></html>"

def generate_homepage_html() -> str:
    """Generates server-rendered homepage HTML with Organization and WebSite JSON-LD"""
    template = load_base_template()

    title = "ZeroBreakout — NSE Stock Breakout Scanner & Technical Setup Terminal"
    description = "Live algorithmic technical pattern scanner for Indian stock market (NSE). Real-time All-Time High, 52-Week High, IPO, and Range Breakout technical setups with dynamic charting."
    canonical_url = f"{BASE_URL}/"

    schema_data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": f"{BASE_URL}/#organization",
                "name": "ZeroBreakout",
                "url": BASE_URL,
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{BASE_URL}/static/assets/icon-512.png"
                },
                "description": "Algorithmic technical structure and breakout pattern scanner for Indian NSE equity markets.",
                "sameAs": [
                    "https://t.me/ZeroBreakout"
                ]
            },
            {
                "@type": "WebSite",
                "@id": f"{BASE_URL}/#website",
                "url": BASE_URL,
                "name": "ZeroBreakout",
                "description": "NSE Stock Technical Breakout Scanner Terminal",
                "publisher": {
                    "@id": f"{BASE_URL}/#organization"
                },
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": f"{BASE_URL}/stock/{{search_term_string}}",
                    "query-input": "required name=search_term_string"
                }
            }
        ]
    }

    head_injection = f"""
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description)}">
  <link rel="canonical" href="{canonical_url}">
  
  <!-- Open Graph / Facebook -->
  <meta property="og:type" content="website">
  <meta property="og:url" content="{canonical_url}">
  <meta property="og:title" content="{html.escape(title)}">
  <meta property="og:description" content="{html.escape(description)}">
  <meta property="og:image" content="{BASE_URL}/static/assets/icon-512.png">
  <meta property="og:site_name" content="ZeroBreakout">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:url" content="{canonical_url}">
  <meta name="twitter:title" content="{html.escape(title)}">
  <meta name="twitter:description" content="{html.escape(description)}">
  <meta name="twitter:image" content="{BASE_URL}/static/assets/icon-512.png">

  <!-- Schema.org Structured Data -->
  <script type="application/ld+json">
{json.dumps(schema_data, indent=2)}
  </script>
"""

    rendered = re.sub(r'<title>.*?</title>', '', template, flags=re.DOTALL)
    rendered = re.sub(r'<meta name="description" content=".*?">', '', rendered, flags=re.DOTALL)
    rendered = rendered.replace('</head>', f'{head_injection}\n</head>')

    return rendered

def generate_stock_ssr_html(setup: Dict[str, Any]) -> str:
    """
    Renders 100% Crawlable Server-Side HTML for a specific stock route (/stock/{symbol}).
    Includes real stock prices, breakout signals, support/resistance, and schema.org JSON-LD.
    """
    template = load_base_template()

    sym = str(setup.get("symbol", "")).upper()
    comp_name = setup.get("company_name") or sym
    sector = setup.get("sector") or "NSE Equity"
    price = float(setup.get("current_price", 0.0) or 0.0)
    change = float(setup.get("change", 0.0) or 0.0)
    change_pct = float(setup.get("change_pct", 0.0) or 0.0)
    is_gain = change >= 0
    mcap_cr = float(setup.get("market_cap_cr", 0.0) or 0.0)
    ath = float(setup.get("all_time_high", 0.0) or 0.0)

    sig = setup.get("latest_signal") or {}
    pattern_type = sig.get("pattern_type") or "Consolidation Base"
    pivot_price = float(sig.get("pivot_price", 0.0) or 0.0)
    pct_vs_pivot = float(sig.get("percent_vs_pivot", 0.0) or 0.0)
    meta = sig.get("metadata") or {}
    support_level = float(meta.get("support_level") or (pivot_price * 0.965 if pivot_price > 0 else price * 0.96))
    sma_20 = float(meta.get("sma_20") or (price * 0.98))
    sma_50 = float(meta.get("sma_50") or (price * 0.95))
    description = meta.get("description") or f"Technical structure setup for {comp_name} ({sym}) on NSE with resistance pivot at ₹{pivot_price:.2f} and base support at ₹{support_level:.2f}."

    price_str = f"₹{price:,.2f}" if price > 0 else "—"
    change_str = f"{'+' if is_gain else ''}{change:.2f} ({'+' if is_gain else ''}{change_pct:.2f}%)" if price > 0 else "—"
    change_class = "price-positive" if is_gain else "price-negative"
    mcap_str = f"₹{mcap_cr/1000:.1f}k Cr" if mcap_cr >= 1000 else (f"₹{mcap_cr:.0f} Cr" if mcap_cr > 0 else "—")
    ath_str = f"₹{ath:,.1f}" if ath > 0 else "—"
    pivot_str = f"₹{pivot_price:,.2f}" if pivot_price > 0 else "—"
    support_str = f"₹{support_level:,.2f}" if support_level > 0 else "—"
    sma20_str = f"₹{sma_20:,.2f}" if sma_20 > 0 else "—"
    sma50_str = f"₹{sma_50:,.2f}" if sma_50 > 0 else "—"
    vs_pivot_str = f"{'+' if pct_vs_pivot >= 0 else ''}{pct_vs_pivot:.2f}%" if pivot_price > 0 else "—"
    vs_pivot_class = "price-positive" if pct_vs_pivot >= 0 else "price-negative"

    page_title = f"{comp_name} ({sym}) — {pattern_type} Technical Setup | ZeroBreakout"
    page_description = f"Live technical chart analysis for {comp_name} ({sym}) on NSE. Current price: {price_str} ({change_str}), {pattern_type} pivot {pivot_str}, Base support {support_str}. Algorithmic breakout scanner."
    canonical_url = f"{BASE_URL}/stock/{sym}"

    schema_data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "Home",
                        "item": BASE_URL
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "NSE Breakout Scanner",
                        "item": f"{BASE_URL}/#scanner"
                    },
                    {
                        "@type": "ListItem",
                        "position": 3,
                        "name": f"{sym}",
                        "item": canonical_url
                    }
                ]
            },
            {
                "@type": "ItemPage",
                "@id": f"{canonical_url}#webpage",
                "url": canonical_url,
                "name": page_title,
                "description": page_description,
                "inLanguage": "en-IN",
                "isPartOf": {
                    "@type": "WebSite",
                    "@id": f"{BASE_URL}/#website",
                    "name": "ZeroBreakout",
                    "url": BASE_URL
                },
                "author": {
                    "@type": "Organization",
                    "name": "ZeroBreakout Quantitative Research Team",
                    "url": BASE_URL
                },
                "mainEntity": {
                    "@type": "FinancialProduct",
                    "name": comp_name,
                    "tickerSymbol": sym,
                    "exchange": "NSE",
                    "category": "Equity / Stock",
                    "description": f"NSE listed equity technical setup: {pattern_type}. Pivot price: {pivot_str}, Base support: {support_str}."
                }
            }
        ]
    }

    head_injection = f"""
  <title>{html.escape(page_title)}</title>
  <meta name="description" content="{html.escape(page_description)}">
  <link rel="canonical" href="{canonical_url}">

  <!-- Open Graph / Facebook -->
  <meta property="og:type" content="article">
  <meta property="og:url" content="{canonical_url}">
  <meta property="og:title" content="{html.escape(page_title)}">
  <meta property="og:description" content="{html.escape(page_description)}">
  <meta property="og:image" content="{BASE_URL}/static/assets/icon-512.png">
  <meta property="og:site_name" content="ZeroBreakout">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:url" content="{canonical_url}">
  <meta name="twitter:title" content="{html.escape(page_title)}">
  <meta name="twitter:description" content="{html.escape(page_description)}">
  <meta name="twitter:image" content="{BASE_URL}/static/assets/icon-512.png">

  <!-- Schema.org JSON-LD -->
  <script type="application/ld+json">
{json.dumps(schema_data, indent=2)}
  </script>
"""

    rendered = template

    rendered = re.sub(r'<title>.*?</title>', '', rendered, flags=re.DOTALL)
    rendered = re.sub(r'<meta name="description" content=".*?">', '', rendered, flags=re.DOTALL)
    rendered = rendered.replace('</head>', f'{head_injection}\n</head>')

    # Set Tab-Setup as ACTIVE and Tab-Scanner as INACTIVE for SSR
    rendered = rendered.replace('id="tab-scanner" class="tab-view active"', 'id="tab-scanner" class="tab-view"')
    rendered = rendered.replace('id="tab-setup" class="tab-view"', 'id="tab-setup" class="tab-view active"')

    # Update bottom navigation buttons
    rendered = rendered.replace('data-tab="scanner" class="nav-tab-btn active"', 'data-tab="scanner" class="nav-tab-btn"')
    rendered = rendered.replace('data-tab="setup" class="nav-tab-btn"', 'data-tab="setup" class="nav-tab-btn active"')

    # Inject Server-Side Stock Content into DOM elements
    rendered = re.sub(r'<h1 id="setupSymbol" class="setup-symbol">.*?</h1>', f'<h1 id="setupSymbol" class="setup-symbol">{html.escape(sym)}</h1>', rendered)
    rendered = re.sub(r'<span id="setupSector" class="setup-sector-tag">.*?</span>', f'<span id="setupSector" class="setup-sector-tag">{html.escape(sector)}</span>', rendered)
    rendered = re.sub(r'<div id="setupCompanyName" class="setup-company-name">.*?</div>', f'<div id="setupCompanyName" class="setup-company-name">{html.escape(comp_name)}</div>', rendered)
    rendered = re.sub(r'<span id="setupPrice" class="setup-current-price">.*?</span>', f'<span id="setupPrice" class="setup-current-price">{price_str}</span>', rendered)
    rendered = re.sub(r'<span id="setupChange" class="setup-price-change.*?">.*?</span>', f'<span id="setupChange" class="setup-price-change {change_class}">{change_str}</span>', rendered)
    rendered = re.sub(r'<b id="setupMcap">.*?</b>', f'<b id="setupMcap">{mcap_str}</b>', rendered)
    rendered = re.sub(r'<b id="setupAth">.*?</b>', f'<b id="setupAth">{ath_str}</b>', rendered)

    rendered = re.sub(r'<span id="statPatternType" class="stat-value">.*?</span>', f'<span id="statPatternType" class="stat-value">{html.escape(pattern_type)}</span>', rendered)
    rendered = re.sub(r'<span id="statPivotPrice" class="stat-value">.*?</span>', f'<span id="statPivotPrice" class="stat-value">{pivot_str}</span>', rendered)
    rendered = re.sub(r'<span id="statSupportLevel" class="stat-value">.*?</span>', f'<span id="statSupportLevel" class="stat-value">{support_str}</span>', rendered)
    rendered = re.sub(r'<span id="statSma20" class="stat-value">.*?</span>', f'<span id="statSma20" class="stat-value">{sma20_str}</span>', rendered)
    rendered = re.sub(r'<span id="statSma50" class="stat-value">.*?</span>', f'<span id="statSma50" class="stat-value">{sma50_str}</span>', rendered)
    rendered = re.sub(r'<span id="statVsPivot" class="stat-value.*?">.*?</span>', f'<span id="statVsPivot" class="stat-value {vs_pivot_class}">{vs_pivot_str}</span>', rendered)
    rendered = re.sub(r'<span id="statDescription">.*?</span>', f'<span id="statDescription">{html.escape(description)}</span>', rendered)

    script_injection = f"""
  <script>
    window.INITIAL_STOCK = "{html.escape(sym)}";
  </script>
"""
    rendered = rendered.replace('</body>', f'{script_injection}\n</body>')

    return rendered

def generate_sitemap_xml(stocks: List[Dict[str, Any]]) -> str:
    """
    Generates dynamic sitemap.xml covering core static routes and all active stock pages.
    """
    now_date = datetime.now().strftime("%Y-%m-%d")

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]

    core_pages = [
        {"loc": f"{BASE_URL}/", "priority": "1.0", "changefreq": "daily"},
        {"loc": f"{BASE_URL}/about", "priority": "0.8", "changefreq": "monthly"},
        {"loc": f"{BASE_URL}/privacy", "priority": "0.5", "changefreq": "monthly"},
        {"loc": f"{BASE_URL}/terms", "priority": "0.5", "changefreq": "monthly"},
    ]

    for page in core_pages:
        xml_lines.append(f"""  <url>
    <loc>{page['loc']}</loc>
    <lastmod>{now_date}</lastmod>
    <changefreq>{page['changefreq']}</changefreq>
    <priority>{page['priority']}</priority>
  </url>""")

    for s in stocks:
        sym = str(s.get("symbol", "")).strip().upper()
        if not sym:
            continue
        updated = s.get("updated_at") or now_date
        if isinstance(updated, str) and "T" in updated:
            updated = updated.split("T")[0]
        elif not isinstance(updated, str) or len(str(updated)) < 10:
            updated = now_date

        stock_url = html.escape(f"{BASE_URL}/stock/{sym}")
        xml_lines.append(f"""  <url>
    <loc>{stock_url}</loc>
    <lastmod>{updated}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>""")

    xml_lines.append('</urlset>')
    return "\n".join(xml_lines)
