"""Synthetic logistic-growth rehearsal solver; no ecological calibration.

All times use the arbitrary time unit in model-contract.json. Biomass uses
synthetic biomass units. Only Python's standard library is required.
"""

from __future__ import annotations

import math


MAX_STEPS = 1_000_000


def _nonnegative(name: str, value: float, *, positive: bool = False) -> float:
    value = float(value)
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        relation = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be finite and {relation}")
    return value


def _parameters(r: float, K: float, d: float, B0: float):
    r = _nonnegative("r", r)
    K = _nonnegative("K", K, positive=True)
    d = _nonnegative("d", d)
    B0 = _nonnegative("B0", B0)
    q = r / K
    if not math.isfinite(q):
        raise ValueError("r/K must be representable as a finite float")
    return r - d, q, B0


def analytic(t: float, r: float, K: float, d: float, B0: float) -> float:
    """Return the analytic biomass for finite, nonnegative t, r, d, B0 and K>0.

    The r=d case is evaluated explicitly, without division by r-d. The
    growing branch uses negative exponentials to avoid exp((r-d)*t) overflow.
    """
    t = _nonnegative("t", t)
    a, q, B0 = _parameters(r, K, d, B0)
    if t == 0 or B0 == 0:
        return B0
    if a == 0:
        value = B0 / (1 + q * B0 * t)
    elif a > 0:
        value = B0 / (math.exp(-a * t) + (q * B0 / a) * -math.expm1(-a * t))
    else:
        value = B0 * math.exp(a * t) / (1 + (q * B0 / a) * math.expm1(a * t))
    if not math.isfinite(value) or value < 0:
        raise ArithmeticError("analytic result is outside the finite nonnegative domain")
    return value


def solve(
    r: float,
    K: float,
    d: float,
    B0: float,
    horizon: float,
    dt: float = 0.1,
) -> list[tuple[float, float]]:
    """Solve dB/dt=(r-d)*B-(r/K)*B**2 using fixed-step classical RK4.

    Include (0, B0) and the exact horizon; shorten the final step if needed.
    Invalid inputs raise ValueError. Nonfinite or negative RK stages/results
    raise ArithmeticError; no clipping, analytical substitution, or adaptive
    step reduction is performed. The in-memory result is capped at 1e6 steps.
    A successful run alone does not certify accuracy: compare with analytic().
    """
    a, q, B0 = _parameters(r, K, d, B0)
    horizon = _nonnegative("horizon", horizon)
    dt = _nonnegative("dt", dt, positive=True)
    ratio = horizon / dt
    if not math.isfinite(ratio) or ratio > MAX_STEPS:
        raise ValueError(f"requested grid exceeds {MAX_STEPS} steps")
    rows = [(0.0, B0)]
    if horizon == 0:
        return rows

    def rhs(biomass: float) -> float:
        if not math.isfinite(biomass) or biomass < 0:
            raise ArithmeticError("invalid RK4 stage; reduce dt or rescale inputs")
        slope = (a - q * biomass) * biomass
        if not math.isfinite(slope):
            raise ArithmeticError("nonfinite RK4 slope; reduce dt or rescale inputs")
        return slope

    biomass = B0
    t = 0.0
    step_count = math.ceil(ratio)
    for index in range(1, step_count + 1):
        t_next = horizon if index == step_count else min(index * dt, horizon)
        # A floating-point quotient can round up by one step. Once the
        # previous grid point has reached the horizon, do not duplicate it.
        if t_next <= t:
            continue
        step = t_next - t
        k1 = rhs(biomass)
        k2 = rhs(biomass + step * k1 / 2)
        k3 = rhs(biomass + step * k2 / 2)
        k4 = rhs(biomass + step * k3)
        biomass += step * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        if not math.isfinite(biomass) or biomass < 0:
            raise ArithmeticError("invalid RK4 result; reduce dt or rescale inputs")
        rows.append((t_next, biomass))
        t = t_next
    return rows
