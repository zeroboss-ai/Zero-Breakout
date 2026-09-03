from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import pandas as pd
from pydantic import BaseModel, Field

class PatternSignal(BaseModel):
    symbol: str
    pattern_type: str
    trigger_date: str
    pivot_price: float
    current_price: float
    percent_vs_pivot: float
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "pattern_type": self.pattern_type,
            "trigger_date": self.trigger_date,
            "pivot_price": round(self.pivot_price, 2),
            "current_price": round(self.current_price, 2),
            "percent_vs_pivot": round(self.percent_vs_pivot, 2),
            "metadata": self.metadata
        }

class BasePatternDetector(ABC):
    """
    Abstract Base Class for all pattern detection algorithms.
    Any new pattern detector (e.g. VCP, Cup & Handle, custom oscillators)
    can simply inherit from BasePatternDetector and implement the `detect` method.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """User-friendly name of the pattern, e.g. 'All-Time High Breakout'"""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """Category: 'breakout', 'reversal', 'moving_average', 'chart_pattern'"""
        pass

    @abstractmethod
    def detect(self, df: pd.DataFrame, stock_info: Dict[str, Any]) -> Optional[PatternSignal]:
        """
        Takes historical OHLCV DataFrame (sorted ascending by date with columns:
        ['date', 'open', 'high', 'low', 'close', 'volume']) and stock metadata dictionary.
        
        Returns a PatternSignal if pattern is triggered on the latest candle (or recent trigger),
        or None if not triggered.
        """
        pass
