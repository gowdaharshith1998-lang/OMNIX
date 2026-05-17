"""FIPS 204 §2.3 / §7.4: mod±, vector norms, power-of-two round."""

from __future__ import annotations

import omnix.axiom.params as P
import omnix.axiom.poly as poly


def test_modpm_upper_half_maps_negative() -> None:
    alpha = 1 << P.D
    # Coefficient exactly at α/2 stays positive (FIPS 204 ↔ reference reduce_mod_pm)
    assert poly.modpm(4096, alpha) == 4096
    assert poly.modpm(4097, alpha) == 4097 - alpha


def test_power2round_reconstruct() -> None:
    for r in (0, 1, 12345, P.Q - 1):
        r1, r0 = poly.power2round(r)
        m = 1 << P.D
        assert (m * r1 + r0) % P.Q == r % P.Q


def test_inf_norm_r_zero() -> None:
    assert poly.inf_norm_r([0] * P.N) == 0
