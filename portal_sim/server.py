"""HTTP facade over MockPortal, for the diagnostics UI and the harness.

Thin by design: all logic lives in portal.py. Admin routes set up synthetic
scenarios; the portal routes exercise the state machine.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .portal import AuthError, Identity, MockPortal, Status

app = FastAPI(title="StreamOS mock portal")
portal = MockPortal()


class AccountIn(BaseModel):
    account_id: str
    status: str = "active"
    max_sessions: int = 1
    on_limit: str = "reject"
    fingerprint_required: bool = False


class RegisterIn(BaseModel):
    account_id: str
    mac: str
    serial: str | None = None
    device_id: str | None = None


class OpenIn(BaseModel):
    mac: str
    serial: str | None = None
    device_id: str | None = None
    fingerprint: str | None = None


@app.post("/admin/reset")
def admin_reset():
    portal.reset()
    return {"ok": True}


@app.post("/admin/account")
def admin_account(body: AccountIn):
    portal.create_account(body.account_id, status=Status(body.status),
                          max_sessions=body.max_sessions, on_limit=body.on_limit,
                          fingerprint_required=body.fingerprint_required)
    return {"ok": True}


@app.post("/admin/register")
def admin_register(body: RegisterIn):
    portal.register(body.account_id,
                    Identity(mac=body.mac, serial=body.serial,
                             device_id=body.device_id))
    return {"ok": True}


@app.post("/admin/status")
def admin_status(account_id: str, status: str):
    portal.set_status(account_id, Status(status))
    return {"ok": True}


@app.post("/admin/expire_sessions")
def admin_expire_sessions(account_id: str):
    return {"expired": portal.force_expire_sessions(account_id)}


@app.get("/admin/state")
def admin_state():
    return portal.state()


@app.post("/session/open")
def session_open(body: OpenIn):
    try:
        return portal.open_session(Identity(**body.model_dump()))
    except AuthError as e:
        raise HTTPException(e.http, e.code)


@app.post("/session/renew")
def session_renew(token: str):
    try:
        return portal.renew_session(token)
    except AuthError as e:
        raise HTTPException(e.http, e.code)


@app.get("/session/validate")
def session_validate(token: str):
    return portal.validate_session(token)


@app.post("/session/close")
def session_close(token: str):
    return {"closed": portal.close_session(token)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8200, log_level="warning")
