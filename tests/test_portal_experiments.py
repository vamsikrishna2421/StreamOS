"""Experiments M01-M10: MAC-based portal mechanisms, run against the local
synthetic portal. Each test maps to the brief's numbered experiment and
records a PASS/FAIL observation.

The portal is driven through its logic class with an injectable clock so
expiry and lockout are deterministic (no sleeps).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portal_sim.portal import AuthError, Identity, MockPortal, Status  # noqa: E402


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def mac(suffix: str) -> str:
    return f"00:1A:79:{suffix}"


# --- M01: a registered identity can open a session ----------------------
def test_m01_registered_identity_opens_session():
    p = MockPortal()
    p.create_account("acc1", max_sessions=1)
    p.register("acc1", Identity(mac=mac("AA:BB:01")))
    sess = p.open_session(Identity(mac=mac("AA:BB:01")))
    assert sess["token"]
    assert p.active_count("acc1") == 1


# --- M02: an unregistered identity is rejected ---------------------------
def test_m02_unregistered_identity_rejected():
    p = MockPortal()
    p.create_account("acc1")
    with pytest.raises(AuthError) as ei:
        p.open_session(Identity(mac=mac("DE:AD:02")))
    assert ei.value.http == 403


# --- M03: identical prefix does NOT imply equivalent registration -------
def test_m03_shared_prefix_not_equivalent():
    p = MockPortal()
    p.create_account("acc1")
    p.register("acc1", Identity(mac=mac("AA:BB:03")))  # only this suffix
    # same prefix 00:1A:79, different suffix -> not registered
    with pytest.raises(AuthError):
        p.open_session(Identity(mac=mac("AA:BB:FF")))
    # the registered one still works
    assert p.open_session(Identity(mac=mac("AA:BB:03")))["token"]


# --- M04: same identity on two devices, one-session policy --------------
def test_m04_same_identity_two_devices_reject_policy():
    p = MockPortal()
    p.create_account("acc1", max_sessions=1, on_limit="reject")
    p.register("acc1", Identity(mac=mac("AA:BB:04")))
    p.open_session(Identity(mac=mac("AA:BB:04"), device_id="tv"))
    with pytest.raises(AuthError) as ei:
        p.open_session(Identity(mac=mac("AA:BB:04"), device_id="phone"))
    assert ei.value.code == "session_limit"
    assert p.active_count("acc1") == 1


def test_m04_same_identity_replace_policy_reproduces_dropouts():
    """on_limit=replace reproduces the historic 'second device kicks the
    first' behaviour that made simultaneous playback unreliable."""
    p = MockPortal()
    p.create_account("acc1", max_sessions=1, on_limit="replace")
    p.register("acc1", Identity(mac=mac("AA:BB:04")))
    first = p.open_session(Identity(mac=mac("AA:BB:04"), device_id="tv"))
    second = p.open_session(Identity(mac=mac("AA:BB:04"), device_id="phone"))
    assert p.active_count("acc1") == 1          # still only one live session
    assert p.validate_session(first["token"])["valid"] is False   # evicted
    assert p.validate_session(second["token"])["valid"] is True


# --- M05: multiple registered devices under one account -----------------
def test_m05_multiple_registered_devices_account_wide_limit():
    p = MockPortal()
    p.create_account("acc1", max_sessions=2, on_limit="reject")
    p.register("acc1", Identity(mac=mac("AA:BB:05")))
    p.register("acc1", Identity(mac=mac("AA:CC:05")))
    p.open_session(Identity(mac=mac("AA:BB:05")))
    p.open_session(Identity(mac=mac("AA:CC:05")))
    assert p.active_count("acc1") == 2
    # a third concurrent session (re-using a registered mac) hits the cap
    with pytest.raises(AuthError) as ei:
        p.open_session(Identity(mac=mac("AA:BB:05")))
    assert ei.value.code == "session_limit"


# --- M06: concurrent playback under configurable limits -----------------
@pytest.mark.parametrize("limit,expect_second", [(1, False), (2, True)])
def test_m06_concurrent_playback(limit, expect_second):
    p = MockPortal()
    p.create_account("acc1", max_sessions=limit, on_limit="reject")
    p.register("acc1", Identity(mac=mac("AA:BB:06")))
    p.register("acc1", Identity(mac=mac("AA:CC:06")))
    assert p.open_session(Identity(mac=mac("AA:BB:06")))["token"]
    if expect_second:
        assert p.open_session(Identity(mac=mac("AA:CC:06")))["token"]
    else:
        with pytest.raises(AuthError):
            p.open_session(Identity(mac=mac("AA:CC:06")))


# --- M07: session expiry and renewal ------------------------------------
def test_m07_session_expiry_and_renewal():
    clk = Clock()
    p = MockPortal(default_ttl=100.0, clock=clk)
    p.create_account("acc1")
    p.register("acc1", Identity(mac=mac("AA:BB:07")))
    sess = p.open_session(Identity(mac=mac("AA:BB:07")))
    assert p.validate_session(sess["token"])["valid"] is True
    clk.advance(50)
    # renew before expiry extends the lifetime
    p.renew_session(sess["token"])
    clk.advance(80)                      # 130 since open, but renewed at 50
    assert p.validate_session(sess["token"])["valid"] is True
    clk.advance(200)                     # now well past renewed expiry
    assert p.validate_session(sess["token"])["valid"] is False
    with pytest.raises(AuthError) as ei:
        p.renew_session(sess["token"])
    assert ei.value.code in ("session_expired", "unknown_session")


# --- M08: account blocking and recovery ---------------------------------
def test_m08_block_then_restore():
    p = MockPortal(enumeration_safe=False)   # study specific reasons here
    p.create_account("acc1")
    p.register("acc1", Identity(mac=mac("AA:BB:08")))
    assert p.open_session(Identity(mac=mac("AA:BB:08")))["token"]
    p.set_status("acc1", Status.BLOCKED)
    with pytest.raises(AuthError) as ei:
        p.open_session(Identity(mac=mac("AA:BB:08")))
    assert ei.value.code == "account_blocked"
    # administrator restores access
    p.set_status("acc1", Status.ACTIVE)
    assert p.open_session(Identity(mac=mac("AA:BB:08")))["token"]


# --- M09: identity collision / ambiguous records ------------------------
def test_m09_identity_collision_last_write_wins_deterministically():
    p = MockPortal()
    p.create_account("acc1")
    p.create_account("acc2")
    m = mac("AA:BB:09")
    p.register("acc1", Identity(mac=m))
    p.register("acc2", Identity(mac=m))   # same mac registered to two accounts
    # the index resolves to exactly one account, deterministically the last
    sess = p.open_session(Identity(mac=m))
    assert sess["account_id"] == "acc2"
    # no duplicate/ambiguous session is created
    assert p.active_count("acc2") == 1
    assert p.active_count("acc1") == 0


# --- M10: enumeration resistance + rate limiting ------------------------
def test_m10_enumeration_safe_responses_indistinguishable():
    p = MockPortal(enumeration_safe=True)
    p.create_account("acc1", status=Status.BLOCKED)
    p.register("acc1", Identity(mac=mac("AA:BB:10")))   # registered but blocked
    # unknown mac
    try:
        p.open_session(Identity(mac=mac("FF:FF:FF")))
    except AuthError as e:
        unknown_code = e.code
    # known-but-blocked mac
    try:
        p.open_session(Identity(mac=mac("AA:BB:10")))
    except AuthError as e:
        blocked_code = e.code
    assert unknown_code == blocked_code == "invalid_credentials"


def test_m10_rate_limit_locks_out_repeated_failures():
    clk = Clock()
    p = MockPortal(rate_max_failures=3, rate_window_s=60, lockout_s=300,
                   clock=clk)
    p.create_account("acc1")
    target = Identity(mac=mac("AA:BB:10"))
    for _ in range(3):
        with pytest.raises(AuthError):
            p.open_session(target)
    # further attempts are rate-limited (429) regardless of validity
    with pytest.raises(AuthError) as ei:
        p.open_session(target)
    assert ei.value.http == 429
    # lockout clears after the window
    clk.advance(301)
    with pytest.raises(AuthError) as ei2:
        p.open_session(target)
    assert ei2.value.http == 403   # back to normal denial, not lockout
