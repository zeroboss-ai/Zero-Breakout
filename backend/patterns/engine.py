from typing import List, Dict, Any, Type, Optional
import pandas as pd
import logging
from .base import BasePatternDetector, PatternSignal
from .detectors import (
    ATHBreakoutDetector,
    FiftyTwoWeekHighDetector,
    FiftyTwoWeekLowDetector,
    Near52WeekHighDetector,
    IPOBreakoutDetector,
    RangeBreakoutDetector,
    MACrossoverDetector
)
from ..database import (
    get_connection,
    insert_signals_batch,
    get_all_active_symbols,
    get_stock_price_history
)

logger = logging.getLogger("ZeroBreakout.PatternEngine")

class PatternEngine:
    """
    Central Pattern Scanning Engine.
    Orchestrates pattern detectors and stores results in the signals table.
    """
    def __init__(self):
        self.detectors: List[BasePatternDetector] = []
        self._register_default_detectors()

    def _register_default_detectors(self):
        """Registers all built-in pattern detectors"""
        self.register(ATHBreakoutDetector())
        self.register(FiftyTwoWeekHighDetector())
        self.register(FiftyTwoWeekLowDetector())
        self.register(Near52WeekHighDetector())
        self.register(IPOBreakoutDetector())
        self.register(RangeBreakoutDetector())
        self.register(MACrossoverDetector())

    def register(self, detector: BasePatternDetector):
        """Registers a new pattern detector into the engine"""
        self.detectors.append(detector)
        logger.info(f"Registered pattern detector: {detector.name} ({detector.category})")

    def scan_stock(self, symbol: str, df: pd.DataFrame, stock_info: Dict[str, Any]) -> List[PatternSignal]:
        """Runs all registered pattern detectors for a single stock"""
        if df.empty or len(df) < 10:
            return []

        signals = []
        for detector in self.detectors:
            try:
                sig = detector.detect(df, stock_info)
                if sig:
                    signals.append(sig)
            except Exception as e:
                logger.error(f"Error detecting {detector.name} for {symbol}: {e}")
        return signals

    def scan_all_stocks(self) -> Dict[str, Any]:
        """
        Scans all active stocks in the database, extracts triggered signals,
        and saves them to the signals table.
        """
        stocks = get_all_active_symbols()
        total_scanned = 0
        total_signals_found = 0
        all_signals_data = []

        logger.info(f"Starting pattern scan for {len(stocks)} stocks...")

        for stock in stocks:
            symbol = stock["symbol"]
            history = get_stock_price_history(symbol, limit_days=1300)
            if not history:
                continue

            df = pd.DataFrame(history)
            # Ensure proper numeric columns
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.sort_values(by="date", ascending=True).reset_index(drop=True)
            signals = self.scan_stock(symbol, df, stock)
            
            for s in signals:
                all_signals_data.append(s.to_dict())

            total_scanned += 1
            total_signals_found += len(signals)

        if all_signals_data:
            insert_signals_batch(all_signals_data)

        logger.info(f"Scan complete: {total_scanned} stocks scanned, {total_signals_found} signals generated.")
        return {
            "stocks_scanned": total_scanned,
            "signals_detected": total_signals_found,
            "timestamp": pd.Timestamp.now().isoformat()
        }

# Global singleton pattern engine
pattern_engine = PatternEngine()
