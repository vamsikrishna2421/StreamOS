"""Mock IPTV portal — a local, synthetic model of MAG/Stalker/Ministra-style
device authorization and session handling.

Purpose
-------
To study, safely and reproducibly, the *mechanisms* real MAC-based portals
use: identity registration, session opening, concurrency policy, session
expiry, account blocking, reconnection, rate limiting, and enumeration
resistance. Understanding these lets the hub behave as a well-mannered
client (back off correctly, renew on time, not hammer a portal).

Boundaries
----------
Everything here is synthetic. Identities and accounts exist only in this
process's memory. The simulator never contacts a real portal, never guesses
credentials, and is not a Stalker-compatible client — it reproduces the
state machine, not any provider's wire protocol. Mapping notes to real
concepts live in ``portal_sim/README.md``.

Design choices worth noting
---------------------------
* ``enumeration_safe`` (default on): every authorization failure returns the
  same opaque ``invalid_credentials`` result, so an outsider cannot tell a
  registered MAC from an unregistered one, an expired account from a blocked
  one. Turn it off to study the (worse) behaviour of a portal that leaks the
  specific reason — useful for contrast in experiment M10/M08.
* ``on_limit`` is per account: ``reject`` (refuse the new session) or
  ``replace`` (evict the oldest session, i.e. "session stealing"). Historic
  "two devices, same MAC, playback kept dropping" behaviour is exactly what
  ``replace`` reproduces.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    BLOCKED = "blocked"


class AuthError(Exception):
    def __init__(self, code: str, http: int = 403):
        super().__init__(code)
        self.code = code
        self.http = http


@dataclass
class Identity:
    """A device identity presented to the portal."""
    mac: str
    serial: str | None = None
    device_id: str | None = None
    fingerprint: str | None = None

    def key(self) -> str:
        return self.mac.lower()


@dataclass
class Session:
    token: str
    account_id: str
    identity_key: str
    created_at: float
    ttl: float
    expires_at: float


@dataclass
class Account:
    account_id: str
    status: Status = Status.ACTIVE
    max_sessions: int = 1
    on_limit: str = "reject"           # reject | replace
    fingerprint_required: bool = False
    # registered identities: mac(lower) -> Identity
    registered: dict[str, Identity] = field(default_factory=dict)


@dataclass
class _RateState:
    failures: int = 0
    window_start: float = 0.0
    locked_until: float = 0.0


class MockPortal:
    def __init__(self, *, enumeration_safe: bool = True,
                 default_ttl: float = 3600.0,
                 rate_max_failures: int = 5,
                 rate_window_s: float = 60.0,
                 lockout_s: float = 300.0,
                 clock=time.time):
        self.enumeration_safe = enumeration_safe
        self.default_ttl = default_ttl
        self.rate_max_failures = rate_max_failures
        self.rate_window_s = rate_window_s
        self.lockout_s = lockout_s
        self._clock = clock
        self._accounts: dict[str, Account] = {}
        self._mac_index: dict[str, str] = {}      # mac(lower) -> account_id
        self._sessions: dict[str, Session] = {}   # token -> Session
        self._rate: dict[str, _RateState] = {}    # mac(lower) -> rate state

    # --- administration (synthetic data setup) --------------------------
    def reset(self) -> None:
        self._accounts.clear()
        self._mac_index.clear()
        self._sessions.clear()
        self._rate.clear()

    def create_account(self, account_id: str, *, status: Status = Status.ACTIVE,
                       max_sessions: int = 1, on_limit: str = "reject",
                       fingerprint_required: bool = False) -> Account:
        acc = Account(account_id=account_id, status=status,
                      max_sessions=max_sessions, on_limit=on_limit,
                      fingerprint_required=fingerprint_required)
        self._accounts[account_id] = acc
        return acc

    def register(self, account_id: str, identity: Identity) -> None:
        acc = self._accounts[account_id]
        acc.registered[identity.key()] = identity
        self._mac_index[identity.key()] = account_id

    def set_status(self, account_id: str, status: Status) -> None:
        self._accounts[account_id].status = status
        # Blocking or expiring an account terminates its live sessions, as a
        # real portal does — otherwise stale sessions would keep occupying
        # concurrency slots after access is revoked.
        if status is not Status.ACTIVE:
            for tok in list(self._sessions):
                if self._sessions[tok].account_id == account_id:
                    del self._sessions[tok]

    def force_expire_sessions(self, account_id: str) -> int:
        n = 0
        for tok in list(self._sessions):
            if self._sessions[tok].account_id == account_id:
                self._sessions[tok].expires_at = self._clock() - 1
                n += 1
        return n

    # --- rate limiting --------------------------------------------------
    def _check_rate(self, mac_key: str) -> None:
        now = self._clock()
        st = self._rate.setdefault(mac_key, _RateState(window_start=now))
        if st.locked_until > now:
            raise AuthError("rate_limited", http=429)

    def _record_failure(self, mac_key: str) -> None:
        now = self._clock()
        st = self._rate.setdefault(mac_key, _RateState(window_start=now))
        if now - st.window_start > self.rate_window_s:
            st.window_start = now
            st.failures = 0
        st.failures += 1
        if st.failures >= self.rate_max_failures:
            st.locked_until = now + self.lockout_s

    def _record_success(self, mac_key: str) -> None:
        self._rate.pop(mac_key, None)

    def _deny(self, mac_key: str, specific: str) -> AuthError:
        self._record_failure(mac_key)
        if self.enumeration_safe:
            return AuthError("invalid_credentials", http=403)
        return AuthError(specific, http=403)

    # --- core state machine ---------------------------------------------
    def open_session(self, identity: Identity) -> dict:
        """Attempt to open a session for a presented identity.

        Returns a session descriptor on success. Raises AuthError otherwise.
        The resolution order mirrors a real portal: rate gate, identity
        lookup, account state, fingerprint, then concurrency policy.
        """
        key = identity.key()
        self._check_rate(key)

        account_id = self._mac_index.get(key)
        if account_id is None:
            raise self._deny(key, "unknown_identity")
        acc = self._accounts[account_id]

        if acc.status is Status.BLOCKED:
            raise self._deny(key, "account_blocked")
        if acc.status is Status.EXPIRED:
            raise self._deny(key, "subscription_expired")

        if acc.fingerprint_required and not identity.fingerprint:
            raise self._deny(key, "fingerprint_required")

        active = self._active_sessions(account_id)
        if len(active) >= acc.max_sessions:
            if acc.on_limit == "replace":
                oldest = min(active, key=lambda s: s.created_at)
                del self._sessions[oldest.token]
            else:
                self._record_failure(key)   # counts toward rate limiting too
                raise AuthError("session_limit", http=409)

        token = secrets.token_hex(16)
        now = self._clock()
        sess = Session(token=token, account_id=account_id, identity_key=key,
                       created_at=now, ttl=self.default_ttl,
                       expires_at=now + self.default_ttl)
        self._sessions[token] = sess
        self._record_success(key)
        return self._descr(sess)

    def renew_session(self, token: str) -> dict:
        sess = self._sessions.get(token)
        if sess is None:
            raise AuthError("unknown_session", http=404)
        if sess.expires_at <= self._clock():
            del self._sessions[token]
            raise AuthError("session_expired", http=401)
        acc = self._accounts[sess.account_id]
        if acc.status is not Status.ACTIVE:
            del self._sessions[token]
            raise AuthError("account_not_active", http=403)
        now = self._clock()
        sess.expires_at = now + sess.ttl
        return self._descr(sess)

    def validate_session(self, token: str) -> dict:
        sess = self._sessions.get(token)
        if sess is None:
            return {"valid": False, "reason": "unknown_session"}
        if sess.expires_at <= self._clock():
            return {"valid": False, "reason": "expired"}
        acc = self._accounts[sess.account_id]
        if acc.status is not Status.ACTIVE:
            return {"valid": False, "reason": f"account_{acc.status.value}"}
        return {"valid": True, "expires_in_s": round(sess.expires_at - self._clock(), 1)}

    def close_session(self, token: str) -> bool:
        return self._sessions.pop(token, None) is not None

    # --- introspection (for experiments / dashboards) ------------------
    def _active_sessions(self, account_id: str) -> list[Session]:
        now = self._clock()
        return [s for s in self._sessions.values()
                if s.account_id == account_id and s.expires_at > now]

    def active_count(self, account_id: str) -> int:
        return len(self._active_sessions(account_id))

    def state(self) -> dict:
        return {
            "accounts": len(self._accounts),
            "registered_macs": len(self._mac_index),
            "live_sessions": sum(1 for s in self._sessions.values()
                                 if s.expires_at > self._clock()),
            "enumeration_safe": self.enumeration_safe,
        }

    @staticmethod
    def _descr(sess: Session) -> dict:
        return {
            "token": sess.token,
            "account_id": sess.account_id,
            "ttl_s": sess.ttl,
            "expires_at": sess.expires_at,
        }
