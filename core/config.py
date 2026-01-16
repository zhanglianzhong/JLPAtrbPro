from dataclasses import dataclass
from typing import Dict


@dataclass
class AssetsConfig:
    symbols: Dict[str, float]


@dataclass
class FeesConfig:
    base_perp_fee_bps: float
    funding_rate_bps_daily: float


@dataclass
class ExecutionConfig:
    max_single_order_usd: float
    twap_total_minutes: int
    max_market_impact_bps: float
    flat_orderbook_haircut_pct: float
    crunch_orderbook_haircut_pct: float


@dataclass
class StrategyParams:
    rebalance_minutes: int
    delta_bounds_pct: Dict[str, float]
    rolling_delta_minutes: int


@dataclass
class JLPConfig:
    jlp_supply: float
    initial_undistributed_fees_usd: float


@dataclass
class SimulationConfig:
    days: int
    seed: int
    initial_prices: Dict[str, float]
    gbm_mu_daily: Dict[str, float]
    gbm_sigma_daily: Dict[str, float]
    initial_spot_holdings: Dict[str, float]
    initial_long_perp: Dict[str, float]
    initial_short_perp: Dict[str, float]

