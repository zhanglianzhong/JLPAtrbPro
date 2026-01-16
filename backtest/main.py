from core.types import StrategyConfig
try:
    from .backtest import run_backtest
except Exception:
    from backtest import run_backtest

# 回测命令入口:通过 `python backtest/main.py` 直接运行


def main():
    assets = {"SOL": 150.0, "ETH": 3200.0, "BTC": 65000.0}
    mu = {"SOL": 0.0, "ETH": 0.0, "BTC": 0.0}
    sigma = {"SOL": 0.01, "ETH": 0.008, "BTC": 0.006}

    spot = {"SOL": 20000.0, "ETH": 1000.0, "BTC": 100.0}
    longp = {"SOL": 0.0, "ETH": 0.0, "BTC": 0.0}
    shortp = {"SOL": 0.0, "ETH": 0.0, "BTC": 0.0}

    strategy = StrategyConfig(
        rebalance_minutes=60,
        delta_bounds_pct={"SOL": 0.02, "ETH": 0.02, "BTC": 0.02},
        max_single_order_usd=200_000.0,
        twap_total_minutes=30,
        max_market_impact_bps=10.0,
        base_perp_fee_bps=5.0,
        flat_orderbook_haircut_pct=0.3,
        crunch_orderbook_haircut_pct=0.2,
        rolling_delta_minutes=60,
        jlp_units=1.0,
    )

    res = run_backtest(
        days=14,
        seed=42,
        initial_prices=assets,
        mu_daily=mu,
        sigma_daily=sigma,
        jlp_supply=1_000_000.0,
        undistributed_fees_usd=100_000.0,
        spot=spot,
        long_perp=longp,
        short_perp=shortp,
        strategy=strategy,
    )

    print("CAGR:", round(res.cagr * 100, 2), "%")
    print("Vol:", round(res.volatility * 100, 2), "%")
    print("Sharpe:", round(res.sharpe, 2))
    print("Total Return:", round(res.total_return * 100, 2), "%")
    print("Max Drawdown:", round(res.max_drawdown * 100, 2), "%")
    print("Perps costs:", round(res.perps_costs_pct * 100, 2), "%")


if __name__ == "__main__":
    main()
