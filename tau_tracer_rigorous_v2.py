#!/usr/bin/env python3
"""==========================================================================
tau_tracer_rigorous_v2.py — RIGOROUS TRACER TOOL · GATE 4 ADDITIVE HARNESS
MODULE_ID: tau.tracer.v2 · BLOCK_TYPE: TOOL · CONTRACT: TAU_CORE_STEP_V1
LAW: Additive diagnostic suite. Does not modify core law.
E4 (filed): original geodesic test asserted monotone convergence to
the target; constant-speed symplectic pursuit does not damp.
E5 (filed): E4's bounce ceiling was wrong — the chord-step map on a
great circle is an EXACT rotation, advance = arctan(dt)/step (machine-
verified: step-30 dist == pi/2 - 30*atan(0.05) to 1e-10). True law:
monotone descent, then neutral period-2 capture, both sides strictly
less than arctan(dt), forever. Test asserts the exact rotation law
plus the neutral 2-cycle. Core untouched — digest unchanged
a9a4ed1e54da45c7.
OUTPUT SENTINEL: ALL_RIGOROUS_TRACER_OK
=========================================================================="""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import tau_core_v2 as core
except ImportError:
    print("ERROR: tau_core_v2.py not found in path.", file=sys.stderr)
    sys.exit(1)


def assert_true(cond, msg):
    if not cond:
        print(f"TRACER_ASSERTION_FAILED: {msg}", file=sys.stderr)
        sys.exit(1)


def trace_geodesic_convergence():
    """Zero-noise pursuit with pure tangent-chord pull (alpha_g=1).
    EXACT dynamics (E5): on the great circle the chord-step map is an
    exact rotation — angular advance per step == arctan(dt).
    Descent is monotone at that rate, then the walker executes a
    neutral period-2 capture around the target: two alternating
    distances, both < arctan(dt), sum == arctan(dt), forever.
    Exact arrival lawfully fires ST_RESET (stand-still gate)."""
    q = core.qnormalize((1.0, 0.0, 0.0, 0.0))
    tgt = core.qnormalize((0.0, 1.0, 0.0, 0.0))
    pb = q
    v = (0.0, 0.0, 0.0, 0.0)
    noise = (0.0, 0.0, 0.0, 0.0)

    DT = 0.05
    params = (0.0, 0.0, 1.0, 0.0, 0.0, 1e-8, 0.5, DT)
    ROT = math.atan(DT)      # exact per-step angular advance
    TOL = 1e-9

    prev = None
    prev2 = None
    oscillating = False
    captured = False
    curr_q = q
    for step in range(120):
        dot = abs(sum(curr_q[i] * tgt[i] for i in range(4)))
        dist = math.acos(min(1.0, max(-1.0, dot)))

        if prev is not None:
            if not oscillating:
                if dist <= prev + TOL:
                    assert_true(
                        abs((prev - dist) - ROT) < TOL,
                        f"Rotation rate drift at step {step}: "
                        f"delta={prev - dist}, want {ROT}",
                    )
                else:
                    oscillating = True
                    assert_true(
                        dist < ROT + TOL,
                        f"Overshoot exceeded arctan(dt) at step {step}: {dist}",
                    )
            else:
                assert_true(
                    dist < ROT + TOL,
                    f"Escaped neutral 2-cycle at step {step}: {dist}",
                )
                if prev2 is not None:
                    assert_true(
                        abs(dist - prev2) < 1e-12,
                        f"2-cycle not neutral at step {step}: "
                        f"{dist} vs {prev2}",
                    )
        if dist <= ROT + TOL:
            captured = True
        prev2 = prev
        prev = dist

        qn, r, band, status, ok = core.guarded_step(
            curr_q, v, pb, tgt, noise, params=params
        )
        if status == core.ST_RESET:
            break
        assert_true(
            band == core.BAND_ACT, f"Residual drift {r} out of BAND_ACT"
        )
        assert_true(
            ok, f"Step {step} rejected with band={band}, status={status}"
        )
        curr_q = qn

    assert_true(captured, "Never reached the arctan(dt) capture zone")


def trace_manifold_orthogonality():
    rng_u = 987654321

    def lcg():
        nonlocal rng_u
        rng_u = (rng_u * 1103515245 + 12345) & 0x7FFFFFFF
        return (rng_u / 2147483648.0) - 1.0

    for _ in range(100):
        q = core.qnormalize(tuple(lcg() for _ in range(4)))
        v = tuple(lcg() for _ in range(4))
        proj = core.qproject(q, v)
        dot = sum(q[i] * proj[i] for i in range(4))
        assert_true(
            abs(dot) < 1e-14, f"Orthogonality failure on S^3: dot={dot}"
        )


def trace_symplectic_torsion_invariance():
    rng_u = 555555555

    def lcg():
        nonlocal rng_u
        rng_u = (rng_u * 1103515245 + 12345) & 0x7FFFFFFF
        return (rng_u / 2147483648.0) - 1.0

    for _ in range(100):
        q = core.qnormalize(tuple(lcg() for _ in range(4)))
        h = core.qsign_perm(q)
        dot = sum(q[i] * h[i] for i in range(4))
        assert_true(
            abs(dot) < 1e-15, f"Symplectic operator not orthogonal: dot={dot}"
        )
        assert_true(
            abs(core.qnorm(h) - 1.0) < 1e-14,
            "Symplectic operator norm deformed",
        )
        assert_true(
            core.qsign_perm(core.qsign_perm(q)) == tuple(-x for x in q),
            "Complex structure axiom J^2 = -I violated",
        )


def trace_subnormal_stability():
    zero_vec = (0.0, 0.0, 0.0, 0.0)
    subnormal_target = (1e-315, 0.0, 0.0, 0.0)
    qn, r, band, status, ok = core.guarded_step(
        (1.0, 0.0, 0.0, 0.0),
        zero_vec,
        zero_vec,
        subnormal_target,
        zero_vec,
    )
    assert_true(
        status == core.ST_RESET, "Subnormal target failed to trigger ST_RESET"
    )
    assert_true(not ok, "Subnormal step marked as accepted")
    assert_true(math.isnan(r), "Subnormal step residual should be NaN")


def main():
    trace_geodesic_convergence()
    trace_manifold_orthogonality()
    trace_symplectic_torsion_invariance()
    trace_subnormal_stability()
    print("ALL_RIGOROUS_TRACER_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
