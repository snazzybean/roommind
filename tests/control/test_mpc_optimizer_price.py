"""Price-weighted MPC: per-block tariff multipliers scale the energy cost.

The energy term must stay byte-identical when no price series is given, and a
PEAK multiplier must move consumption out of the expensive blocks.
"""

from __future__ import annotations

from custom_components.roommind.control.mpc_optimizer import MPCOptimizer
from custom_components.roommind.control.thermal_model import RCModel


def _optimizer() -> MPCOptimizer:
    # Heavy thermal mass (UFH-like): the optimizer can bank heat in cheap
    # blocks and coast through expensive ones, which is what this tests.
    model = RCModel(C=200.0, U=50.0, Q_heat=1000.0, Q_cool=1500.0)
    return MPCOptimizer(model, can_heat=True, can_cool=False, w_comfort=1.0, w_energy=1.0)


def _run(prices: list[float] | None) -> list[str]:
    n = len(prices) if prices else 24
    return (
        _optimizer()
        .optimize(
            T_room=19.5,
            T_outdoor_series=[5.0] * n,
            heat_target_series=[21.0] * n,
            dt_minutes=5,
            price_series=prices,
        )
        .actions
    )


def test_price_series_none_matches_flat_series() -> None:
    """A flat 1.0 series is identical to passing nothing at all."""
    flat = _run(None)
    ones = _run([1.0] * 24)
    assert flat == ones


def test_expensive_tail_moves_energy_into_cheap_head() -> None:
    """Heating in the expensive blocks shrinks when their price rises."""
    flat = _run([1.0] * 24)
    prices = [1.0] * 12 + [5.0] * 12
    peak = _run(prices)
    heating_in_expensive_flat = sum(1 for a in flat[12:] if a == "heating")
    heating_in_expensive_peak = sum(1 for a in peak[12:] if a == "heating")
    assert heating_in_expensive_peak <= heating_in_expensive_flat
    # The room is below target in a cold house: with real demand the expensive
    # tail must actually shed at least one run, else the test scenario is degenerate.
    assert heating_in_expensive_flat > 0
    assert heating_in_expensive_peak < heating_in_expensive_flat
