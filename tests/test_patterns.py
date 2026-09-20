import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from backend.patterns.detectors import (
    ATHBreakoutDetector,
    FiftyTwoWeekHighDetector,
    FiftyTwoWeekLowDetector,
    RangeBreakoutDetector,
    DoubleBottomDetector,
    MACrossoverDetector
)

def create_synthetic_df(close_series, volume_series=None):
    n = len(close_series)
    dates = [(datetime(2025, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]
    if volume_series is None:
        volumes = [100000] * n
    else:
        volumes = volume_series
    
    opens = [c * 0.99 for c in close_series]
    highs = [c * 1.01 for c in close_series]
    lows = [c * 0.98 for c in close_series]
    
    return pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": close_series,
        "volume": volumes
    })

def test_ath_breakout_detector():
    detector = ATHBreakoutDetector()
    # 200 days: 190 days below 100, last days breaking out to 105
    closes = [90.0] * 180 + [98.0] * 19 + [105.0]
    df = create_synthetic_df(closes)
    # Give historical high of 100 in earlier period
    df.loc[50, "high"] = 100.0
    df.loc[len(df)-1, "high"] = 106.0
    
    stock_info = {"symbol": "TESTATH", "all_time_high": 100.0}
    signal = detector.detect(df, stock_info)
    
    assert signal is not None
    assert signal.pattern_type == "All-Time High Breakout"
    assert signal.pivot_price == 106.0 or signal.pivot_price == 100.0
    assert signal.current_price == 105.0

def test_52w_high_detector():
    detector = FiftyTwoWeekHighDetector()
    closes = [100.0] * 250 + [103.0]
    df = create_synthetic_df(closes)
    df.loc[len(df)-1, "high"] = 104.0
    
    stock_info = {"symbol": "TEST52W"}
    signal = detector.detect(df, stock_info)
    
    assert signal is not None
    assert signal.pattern_type == "52-Week High Breakout"
    assert signal.current_price == 103.0

def test_52w_low_detector():
    detector = FiftyTwoWeekLowDetector()
    closes = [100.0] * 250 + [96.0]
    df = create_synthetic_df(closes)
    df.loc[len(df)-1, "low"] = 95.0
    
    stock_info = {"symbol": "TEST52WLOW"}
    signal = detector.detect(df, stock_info)
    
    assert signal is not None
    assert signal.pattern_type == "52-Week Low Breakdown"
    assert signal.current_price == 96.0

def test_range_breakout_detector():
    detector = RangeBreakoutDetector()
    # Consolidate between 100 and 104 for 25 days, then surge to 110 with volume 3x
    closes = [102.0] * 30 + [103.0] * 20 + [110.0]
    volumes = [50000] * 50 + [200000]
    df = create_synthetic_df(closes, volume_series=volumes)
    # range high is 105
    for i in range(30, 50):
        df.loc[i, "high"] = 104.5
        df.loc[i, "low"] = 101.0
    df.loc[len(df)-1, "high"] = 111.0
    
    stock_info = {"symbol": "TESTRANGE"}
    signal = detector.detect(df, stock_info)
    
    assert signal is not None
    assert signal.pattern_type == "Range Breakout"
    assert signal.current_price == 110.0

def test_double_bottom_detector():
    detector = DoubleBottomDetector()
    # Construct W: 45 days
    # Trough 1 at day 10 (price 100), Peak at day 22 (price 112), Trough 2 at day 35 (price 100), Breakout at day 44 (price 115)
    prices = [110.0] * 45
    df = create_synthetic_df(prices)
    
    # Set lows and highs to form clean W
    df.loc[10, "low"] = 98.0
    df.loc[10, "close"] = 99.0
    
    df.loc[22, "high"] = 112.0
    df.loc[22, "close"] = 111.0
    
    df.loc[35, "low"] = 98.5
    df.loc[35, "close"] = 99.5
    
    df.loc[44, "high"] = 116.0
    df.loc[44, "close"] = 115.0
    
    stock_info = {"symbol": "TEST_W"}
    signal = detector.detect(df, stock_info)
    
    assert signal is not None
    assert "Double Bottom" in signal.pattern_type

if __name__ == "__main__":
    test_ath_breakout_detector()
    test_52w_high_detector()
    test_52w_low_detector()
    test_range_breakout_detector()
    test_double_bottom_detector()
    print("All pattern detector unit tests passed successfully!")
