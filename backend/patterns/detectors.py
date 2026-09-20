import numpy as np
import pandas as pd
from typing import Optional, Dict, Any, List
from .base import BasePatternDetector, PatternSignal

class ATHBreakoutDetector(BasePatternDetector):
    """
    Pattern 1: All-time high breakout.
    Triggers when price tests or clears the stock's TRUE lifetime All-Time High within strict recency (last 4 sessions)
    and within the active entry buy zone (-1.5% to +6.0% vs lifetime ATH).
    """
    @property
    def name(self) -> str:
        return "All-Time High Breakout"

    @property
    def category(self) -> str:
        return "breakout"

    def detect(self, df: pd.DataFrame, stock_info: Dict[str, Any]) -> Optional[PatternSignal]:
        # Require at least 180 trading days to validate true All-Time High breakouts
        if len(df) < 180:
            return None

        latest_candle = df.iloc[-1]
        latest_close = float(latest_candle["close"])
        latest_high = float(latest_candle["high"])
        latest_date = str(latest_candle["date"])
        symbol = str(stock_info.get("symbol", latest_candle.get("symbol", "UNKNOWN")))

        # 1. Determine TRUE lifetime All-Time High
        stored_ath = float(stock_info.get("all_time_high", 0) or 0)
        hist_high = float(df["high"].max())
        true_ath = max(stored_ath, hist_high)

        # Must have a valid positive ATH
        if true_ath <= 0:
            return None

        # 2. Strict Distance Check against TRUE lifetime ATH
        pct_vs_ath = ((latest_close - true_ath) / true_ath) * 100.0

        # Must be within actionable zone (-1.5% to +6.0% of true lifetime ATH)
        # If price is lower than -1.5% (e.g. -10%, -60% like Solara), it is NOT an ATH breakout!
        if not (-1.5 <= pct_vs_ath <= 6.0):
            return None

        # 3. Check recency: Did price test or break the true lifetime ATH in the last 4 trading sessions?
        recent_highs = df.iloc[-4:]["high"].values
        if not any(h >= true_ath * 0.985 for h in recent_highs):
            return None

        # 4. Check if breakout is fresh (first time crossing ATH today vs yesterday)
        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else 0.0
        is_fresh = bool(prev_close < true_ath * 0.99 and (latest_close >= true_ath * 0.99 or latest_high >= true_ath))

        support_level = round(float(df.iloc[-20:]["low"].min()) if len(df) >= 20 else true_ath * 0.965, 2)
        sma_20 = round(float(df["close"].rolling(20).mean().iloc[-1]), 2) if len(df) >= 20 else round(true_ath * 0.97, 2)

        return PatternSignal(
            symbol=symbol,
            pattern_type=self.name,
            trigger_date=latest_date,
            pivot_price=round(true_ath, 2),
            current_price=latest_close,
            percent_vs_pivot=round(pct_vs_ath, 2),
            metadata={
                "prior_ath": round(true_ath, 2),
                "support_level": support_level,
                "sma_20": sma_20,
                "is_fresh": is_fresh,
                "fresh_label": "Fresh ATH Breakout Today" if is_fresh else "Active ATH Setup",
                "breakout_volume": int(latest_candle.get("volume", 0)),
                "description": f"Testing lifetime All-Time High of ₹{true_ath:.2f} ({pct_vs_ath:+.2f}%). Base support at ₹{support_level:.2f}."
            }
        )


class FiftyTwoWeekHighDetector(BasePatternDetector):
    """
    Pattern 2: 52-week high breakout.
    Active only if breakout occurred in last 4 sessions and price is within [-1.5%, +5.5%] of 52W High.
    Requires at least 200+ trading days of historical data.
    """
    @property
    def name(self) -> str:
        return "52-Week High Breakout"

    @property
    def category(self) -> str:
        return "breakout"

    def detect(self, df: pd.DataFrame, stock_info: Dict[str, Any]) -> Optional[PatternSignal]:
        # Require at least 200 trading days (nearly a full year) for 52W high validity
        if len(df) < 200:
            return None

        lookback = min(252, len(df) - 1)
        # Prior 52W high excluding latest 4-day breakout window
        base_window = df.iloc[-(lookback + 1):-4] if len(df) > 10 else df.iloc[-(lookback + 1):-1]
        high_52w = float(base_window["high"].max())

        latest_candle = df.iloc[-1]
        latest_close = float(latest_candle["close"])
        latest_high = float(latest_candle["high"])
        latest_date = str(latest_candle["date"])
        symbol = str(stock_info.get("symbol", latest_candle.get("symbol", "UNKNOWN")))

        if high_52w <= 0:
            return None

        pct_vs_pivot = ((latest_close - high_52w) / high_52w) * 100.0

        # Strict Actionable Zone: -1.5% to +5.5%
        if not (-1.5 <= pct_vs_pivot <= 5.5):
            return None

        # Check recency
        recent_highs = df.iloc[-4:]["high"].values
        if not any(h >= high_52w * 0.99 for h in recent_highs):
            return None

        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else 0.0
        is_fresh = bool(prev_close < high_52w and (latest_close >= high_52w * 0.99 or latest_high >= high_52w))

        support_level = round(float(df.iloc[-20:]["low"].min()) if len(df) >= 20 else high_52w * 0.965, 2)
        sma_20 = round(float(df["close"].rolling(20).mean().iloc[-1]), 2) if len(df) >= 20 else round(high_52w * 0.97, 2)

        return PatternSignal(
            symbol=symbol,
            pattern_type=self.name,
            trigger_date=latest_date,
            pivot_price=round(high_52w, 2),
            current_price=latest_close,
            percent_vs_pivot=round(pct_vs_pivot, 2),
            metadata={
                "high_52w": round(high_52w, 2),
                "lookback_days": lookback,
                "support_level": support_level,
                "sma_20": sma_20,
                "is_fresh": is_fresh,
                "fresh_label": "Fresh 52W High Today" if is_fresh else "Active 52W Setup",
                "description": f"Testing 52-Week High resistance of ₹{high_52w:.2f} ({pct_vs_pivot:+.2f}%). Base support at ₹{support_level:.2f}."
            }
        )


class FiftyTwoWeekLowDetector(BasePatternDetector):
    """
    Pattern 3: 52-week low breakdown.
    Triggers when price freshly broke below 52-week support within the last 4 sessions.
    """
    @property
    def name(self) -> str:
        return "52-Week Low Breakdown"

    @property
    def category(self) -> str:
        return "breakdown"

    def detect(self, df: pd.DataFrame, stock_info: Dict[str, Any]) -> Optional[PatternSignal]:
        # Require at least 200 trading days for 52W low breakdown
        if len(df) < 200:
            return None

        lookback = min(252, len(df) - 1)
        base_window = df.iloc[-(lookback + 1):-4] if len(df) > 10 else df.iloc[-(lookback + 1):-1]
        low_52w = float(base_window["low"].min())

        latest_candle = df.iloc[-1]
        latest_close = float(latest_candle["close"])
        latest_date = str(latest_candle["date"])
        symbol = str(stock_info.get("symbol", latest_candle.get("symbol", "UNKNOWN")))

        if low_52w <= 0:
            return None

        pct_vs_pivot = ((latest_close - low_52w) / low_52w) * 100.0

        # Actionable breakdown range: -5.0% to +0.5%
        if not (-5.0 <= pct_vs_pivot <= 0.5):
            return None

        recent_lows = df.iloc[-4:]["low"].values
        if not any(l <= low_52w * 1.005 for l in recent_lows):
            return None

        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else 0.0
        is_fresh = bool(prev_close >= low_52w and latest_close < low_52w)
        resistance_level = round(float(df.iloc[-20:]["high"].max()) if len(df) >= 20 else low_52w * 1.05, 2)
        sma_20 = round(float(df["close"].rolling(20).mean().iloc[-1]), 2) if len(df) >= 20 else round(low_52w * 1.02, 2)

        return PatternSignal(
            symbol=symbol,
            pattern_type=self.name,
            trigger_date=latest_date,
            pivot_price=round(low_52w, 2),
            current_price=latest_close,
            percent_vs_pivot=round(pct_vs_pivot, 2),
            metadata={
                "low_52w": round(low_52w, 2),
                "lookback_days": lookback,
                "support_level": round(low_52w, 2),
                "sma_20": sma_20,
                "resistance_level": resistance_level,
                "is_fresh": is_fresh,
                "fresh_label": "Fresh 52W Breakdown" if is_fresh else "52W Breakdown",
                "description": f"Broke below 52-week support floor of ₹{low_52w:.2f} ({pct_vs_pivot:+.2f}%)."
            }
        )


class RangeBreakoutDetector(BasePatternDetector):
    """
    Pattern 4: Range breakout.
    Tight consolidation (<=8.0%) for 15-25 bars, breaking out within the last 3 sessions.
    Active range: 0.0% to +5.5% vs range high.
    """
    @property
    def name(self) -> str:
        return "Range Breakout"

    @property
    def category(self) -> str:
        return "breakout"

    def detect(self, df: pd.DataFrame, stock_info: Dict[str, Any]) -> Optional[PatternSignal]:
        if len(df) < 25:
            return None

        consolidation_period = 20
        consolidation_window = df.iloc[-(consolidation_period + 3):-3]

        range_high = float(consolidation_window["high"].max())
        range_low = float(consolidation_window["low"].min())

        if range_low <= 0:
            return None

        range_pct = ((range_high - range_low) / range_low) * 100.0
        if range_pct > 8.0:
            return None

        latest_candle = df.iloc[-1]
        latest_close = float(latest_candle["close"])
        latest_vol = float(latest_candle.get("volume", 0))
        latest_date = str(latest_candle["date"])
        symbol = str(stock_info.get("symbol", latest_candle.get("symbol", "UNKNOWN")))

        pct_vs_pivot = ((latest_close - range_high) / range_high) * 100.0

        # Must be within actionable breakout range (0.0% to +5.5%)
        if not (0.0 <= pct_vs_pivot <= 5.5):
            return None

        # Breakout must have happened in last 3 sessions
        recent_closes = df.iloc[-3:]["close"].values
        if not any(c >= range_high for c in recent_closes):
            return None

        avg_vol = float(df.iloc[-21:-3]["volume"].mean()) if "volume" in df.columns else 0.0
        vol_ratio = (latest_vol / avg_vol) if avg_vol > 0 else 1.0

        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else 0.0
        is_fresh = bool(prev_close <= range_high and latest_close > range_high)
        sma_20 = round(float(df["close"].rolling(20).mean().iloc[-1]), 2) if len(df) >= 20 else round(range_low, 2)

        return PatternSignal(
            symbol=symbol,
            pattern_type=self.name,
            trigger_date=latest_date,
            pivot_price=round(range_high, 2),
            current_price=latest_close,
            percent_vs_pivot=round(pct_vs_pivot, 2),
            metadata={
                "range_high": round(range_high, 2),
                "range_low": round(range_low, 2),
                "support_level": round(range_low, 2),
                "sma_20": sma_20,
                "is_fresh": is_fresh,
                "fresh_label": "Fresh Range Breakout Today" if is_fresh else "Active Range Breakout",
                "volume_multiple": round(vol_ratio, 2),
                "description": f"Consolidated {range_pct:.1f}% for {consolidation_period} sessions; expanding above ₹{range_high:.2f}. Base support at ₹{range_low:.2f}."
            }
        )


class DoubleBottomDetector(BasePatternDetector):
    """
    Pattern 5: W pattern (Double bottom).
    """
    @property
    def name(self) -> str:
        return "Double Bottom (W)"

    @property
    def category(self) -> str:
        return "reversal"

    def detect(self, df: pd.DataFrame, stock_info: Dict[str, Any]) -> Optional[PatternSignal]:
        if len(df) < 30:
            return None

        # Look at trailing 40 bars for recent W formation
        window = df.iloc[-40:].copy().reset_index(drop=True)
        lows = window["low"].values
        closes = window["close"].values
        highs = window["high"].values
        n = len(window)

        # Identify local trough minima
        trough_indices = []
        for i in range(2, n - 2):
            left = lows[max(0, i - 2):i]
            right = lows[i + 1:min(n, i + 3)]
            if len(left) > 0 and len(right) > 0:
                if lows[i] <= np.min(left) and lows[i] <= np.min(right):
                    trough_indices.append(i)

        if len(trough_indices) < 2:
            return None

        # Iterate trough pairs (starting with the most recent troughs)
        for idx in range(len(trough_indices) - 2, -1, -1):
            t1_idx = trough_indices[idx]
            for j in range(idx + 1, len(trough_indices)):
                t2_idx = trough_indices[j]
                
                # Recency check: T2 must have formed within last 16 trading bars
                if (n - 1 - t2_idx) > 16:
                    continue

                spacing = t2_idx - t1_idx
                if spacing < 4 or spacing > 24:
                    continue

                t1_val = float(lows[t1_idx])
                t2_val = float(lows[t2_idx])

                # Troughs must be roughly equal (within 3.5%)
                trough_diff_pct = abs(t1_val - t2_val) / min(t1_val, t2_val) * 100.0
                if trough_diff_pct > 3.5:
                    continue

                # Neckline peak between t1 and t2
                middle_segment = highs[t1_idx:t2_idx + 1]
                if len(middle_segment) == 0:
                    continue
                neckline_peak = float(np.max(middle_segment))

                avg_trough = (t1_val + t2_val) / 2.0
                depth_pct = ((neckline_peak - avg_trough) / avg_trough) * 100.0
                if depth_pct < 3.0:
                    continue

                latest_candle = df.iloc[-1]
                latest_close = float(latest_candle["close"])
                latest_date = str(latest_candle["date"])
                symbol = str(stock_info.get("symbol", latest_candle.get("symbol", "UNKNOWN")))

                pct_vs_pivot = ((latest_close - neckline_peak) / neckline_peak) * 100.0

                if not (-1.0 <= pct_vs_pivot <= 6.0):
                    continue

                recent_highs = closes[-4:]
                if not any(c >= neckline_peak * 0.99 for c in recent_highs):
                    continue

                prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else 0.0
                is_fresh = bool(prev_close < neckline_peak and latest_close >= neckline_peak * 0.995)
                sma_20 = round(float(df["close"].rolling(20).mean().iloc[-1]), 2) if len(df) >= 20 else round(t2_val, 2)

                return PatternSignal(
                    symbol=symbol,
                    pattern_type=self.name,
                    trigger_date=latest_date,
                    pivot_price=round(neckline_peak, 2),
                    current_price=latest_close,
                    percent_vs_pivot=round(pct_vs_pivot, 2),
                    metadata={
                        "trough1_price": round(t1_val, 2),
                        "trough2_price": round(t2_val, 2),
                        "neckline_pivot": round(neckline_peak, 2),
                        "support_level": round(t2_val, 2),
                        "sma_20": sma_20,
                        "trough_spacing_days": spacing,
                        "is_fresh": is_fresh,
                        "fresh_label": "Fresh W Breakout Today" if is_fresh else "Active W Setup",
                        "description": f"Double bottom W base (troughs ₹{t1_val:.2f} & ₹{t2_val:.2f}); neckline at ₹{neckline_peak:.2f} ({pct_vs_pivot:+.2f}%). Base support at ₹{t2_val:.2f}."
                    }
                )

        return None


class Near52WeekHighDetector(BasePatternDetector):
    """
    Pattern: Near 52-Week High Pre-Breakout Setup.
    Detects stocks consolidating within striking distance (-1.0% to -8.0%) of their established 52-Week High.
    """
    @property
    def name(self) -> str:
        return "Near 52-Week High"

    @property
    def category(self) -> str:
        return "consolidation"

    def detect(self, df: pd.DataFrame, stock_info: Dict[str, Any]) -> Optional[PatternSignal]:
        if len(df) < 200:
            return None

        lookback = min(252, len(df))
        base_window = df.iloc[-(lookback):-7]
        if len(base_window) < 50:
            return None

        established_52wh = float(base_window["high"].max())
        if established_52wh <= 0:
            return None

        latest_candle = df.iloc[-1]
        latest_close = float(latest_candle["close"])
        latest_date = str(latest_candle["date"])
        symbol = str(stock_info.get("symbol", latest_candle.get("symbol", "UNKNOWN")))

        pct_from_52wh = ((latest_close - established_52wh) / established_52wh) * 100.0

        if not (-8.0 <= pct_from_52wh <= -1.0):
            return None

        recent_window = df.iloc[-7:]
        if any(float(h) > established_52wh * 1.01 for h in recent_window["high"].values):
            return None

        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else 0.0
        prev_pct = ((prev_close - established_52wh) / established_52wh) * 100.0 if prev_close > 0 else -99.0
        is_fresh = bool(prev_pct < -8.0 and pct_from_52wh >= -8.0)

        support_level = round(float(df.iloc[-20:]["low"].min()) if len(df) >= 20 else established_52wh * 0.92, 2)
        sma_20 = round(float(df["close"].rolling(20).mean().iloc[-1]), 2) if len(df) >= 20 else round(established_52wh * 0.94, 2)

        return PatternSignal(
            symbol=symbol,
            pattern_type=self.name,
            trigger_date=latest_date,
            pivot_price=round(established_52wh, 2),
            current_price=latest_close,
            percent_vs_pivot=round(pct_from_52wh, 2),
            metadata={
                "high_52w": round(established_52wh, 2),
                "pct_down_from_high": round(abs(pct_from_52wh), 2),
                "support_level": support_level,
                "sma_20": sma_20,
                "is_fresh": is_fresh,
                "fresh_label": "Fresh Near 52W High" if is_fresh else "Active Near 52W Setup",
                "description": f"Consolidating within striking distance ({pct_from_52wh:.2f}%) of 52-Week High (₹{established_52wh:.2f}). Base support at ₹{support_level:.2f}."
            }
        )


class MACrossoverDetector(BasePatternDetector):
    """
    Pattern 8: Moving Average Crossover.
    """
    @property
    def name(self) -> str:
        return "MA Crossover"

    @property
    def category(self) -> str:
        return "moving_average"

    def detect(self, df: pd.DataFrame, stock_info: Dict[str, Any]) -> Optional[PatternSignal]:
        if len(df) < 55:
            return None

        closes = df["close"]
        sma_20_series = closes.rolling(window=20).mean()
        sma_50_series = closes.rolling(window=50).mean()

        has_recent_crossover = False
        cross_bar_idx = -1
        for offset in range(-3, 0):
            prev_20 = sma_20_series.iloc[offset - 1]
            prev_50 = sma_50_series.iloc[offset - 1]
            curr_20 = sma_20_series.iloc[offset]
            curr_50 = sma_50_series.iloc[offset]

            if pd.notna(prev_20) and pd.notna(prev_50) and pd.notna(curr_20) and pd.notna(curr_50):
                if prev_20 <= prev_50 and curr_20 > curr_50:
                    has_recent_crossover = True
                    cross_bar_idx = offset
                    break

        if not has_recent_crossover:
            return None

        latest_candle = df.iloc[-1]
        latest_close = float(latest_candle["close"])
        latest_date = str(latest_candle["date"])
        symbol = str(stock_info.get("symbol", latest_candle.get("symbol", "UNKNOWN")))
        latest_50 = float(sma_50_series.iloc[-1])
        latest_20 = float(sma_20_series.iloc[-1])

        pct_vs_pivot = ((latest_close - latest_50) / latest_50) * 100.0

        if not (0.0 <= pct_vs_pivot <= 4.5):
            return None

        is_fresh = (cross_bar_idx == -1)
        support_level = round(latest_50 * 0.98, 2)

        return PatternSignal(
            symbol=symbol,
            pattern_type=self.name,
            trigger_date=latest_date,
            pivot_price=round(latest_50, 2),
            current_price=latest_close,
            percent_vs_pivot=round(pct_vs_pivot, 2),
            metadata={
                "sma_20": round(latest_20, 2),
                "sma_50": round(latest_50, 2),
                "support_level": support_level,
                "is_fresh": is_fresh,
                "cross_type": "Fresh Bullish 20/50 SMA Crossover",
                "description": f"Bullish Moving Average cross: 20 SMA (₹{latest_20:.2f}) crossed over 50 SMA (₹{latest_50:.2f}). Support at ₹{support_level:.2f}."
            }
        )


class IPOBreakoutDetector(BasePatternDetector):
    """
    Pattern: IPO Breakout (IPO Base / All-Time High Breakout for genuine newly listed stocks).
    Strict Rules:
    1. Must be listed within the last 18 months (<= 550 calendar days from official NSE listing date).
    2. Must have between 20 and 320 trading sessions.
    3. Strictly excludes legacy/old migrated companies.
    4. Triggers when price breaks out to or tests its lifetime All-Time High.
    """
    @property
    def name(self) -> str:
        return "IPO Breakout"

    @property
    def category(self) -> str:
        return "breakout"

    def detect(self, df: pd.DataFrame, stock_info: Dict[str, Any]) -> Optional[PatternSignal]:
        # Validate official listing date
        listing_date_str = stock_info.get("listing_date")
        if listing_date_str:
            try:
                l_date = pd.to_datetime(listing_date_str)
                days_since_listing = (pd.Timestamp.now() - l_date).days
                # Strictly require listing within last 18 months (550 days) and at least 15 days of trading
                if days_since_listing > 550 or days_since_listing < 15:
                    return None
            except Exception:
                return None
        else:
            # If listing_date not set, require strict candle length
            if not (20 <= len(df) <= 300):
                return None

        latest_candle = df.iloc[-1]
        latest_close = float(latest_candle["close"])
        latest_high = float(latest_candle["high"])
        latest_date = str(latest_candle["date"])
        symbol = str(stock_info.get("symbol", latest_candle.get("symbol", "UNKNOWN")))

        if symbol.endswith("-B") or symbol.endswith("-BE") or symbol.endswith("-BZ"):
            return None

        stored_ath = float(stock_info.get("all_time_high", 0) or 0)
        prior_candles_max = float(df.iloc[:-1]["high"].max()) if len(df) > 1 else float(df.iloc[-1]["high"])
        prior_ath = max(prior_candles_max, stored_ath) if stored_ath > 0 else prior_candles_max
        if prior_ath <= 0:
            return None

        pct_vs_pivot = ((latest_close - prior_ath) / prior_ath) * 100.0

        if not (-1.5 <= pct_vs_pivot <= 6.5):
            return None

        recent_highs = df.iloc[-4:]["high"].values
        if not any(h >= prior_ath * 0.99 for h in recent_highs):
            return None

        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else 0.0
        is_fresh = bool(prev_close < prior_ath and (latest_close >= prior_ath * 0.99 or latest_high >= prior_ath))

        support_level = round(float(df.iloc[-15:]["low"].min()) if len(df) >= 15 else prior_ath * 0.95, 2)
        sma_20 = round(float(df["close"].rolling(20).mean().iloc[-1]), 2) if len(df) >= 20 else round(prior_ath * 0.96, 2)
        candles_count = len(df)

        return PatternSignal(
            symbol=symbol,
            pattern_type=self.name,
            trigger_date=latest_date,
            pivot_price=round(prior_ath, 2),
            current_price=latest_close,
            percent_vs_pivot=round(pct_vs_pivot, 2),
            metadata={
                "prior_ath": round(prior_ath, 2),
                "candles_since_ipo": candles_count,
                "listing_date": listing_date_str or "Recent",
                "support_level": support_level,
                "sma_20": sma_20,
                "is_fresh": is_fresh,
                "fresh_label": "Fresh IPO ATH Breakout" if is_fresh else "Active IPO ATH Setup",
                "breakout_volume": int(latest_candle.get("volume", 0)),
                "description": f"Mainboard IPO (listed {listing_date_str or 'recently'}) testing lifetime ATH of ₹{prior_ath:.2f} ({pct_vs_pivot:+.2f}%). Base support at ₹{support_level:.2f}."
            }
        )

