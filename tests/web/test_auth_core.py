from sqlalchemy import select

from scripts.storage.models import Invite, Tenant
from scripts.web import auth
from scripts.web.invites import create_invite, main, revoke_invite


def test_hash_is_stable_and_is_not_the_code():
    assert auth.hash_code("abc") == auth.hash_code("abc")
    assert auth.hash_code("abc") != "abc"
    assert len(auth.hash_code("abc")) == 64


def test_new_codes_are_unique_and_long():
    codes = {auth.new_code() for _ in range(50)}
    assert len(codes) == 50
    assert all(len(code) >= 20 for code in codes)


def test_create_invite_stores_only_the_hash(patched_sessions):
    with patched_sessions() as session:
        code = create_invite(session, label="Maya", tenant_slug="maya")
        session.commit()
        row = session.scalar(select(Invite))
        assert row.code_hash == auth.hash_code(code)
        assert code not in (row.code_hash, row.label)
        assert session.scalar(select(Tenant.slug)) == "maya"
        assert row.tenant_id is not None and row.is_owner is False


def test_authenticate_accepts_a_live_code_and_records_use(patched_sessions):
    with patched_sessions() as session:
        code = create_invite(session, label="Maya", tenant_slug="maya")
        session.commit()
    identity = auth.authenticate(code)
    assert identity is not None and identity.label == "Maya" and identity.tenant_id is not None
    with patched_sessions() as session:
        assert session.scalar(select(Invite.last_used_at)) is not None


def test_authenticate_ignores_surrounding_whitespace(patched_sessions):
    with patched_sessions() as session:
        code = create_invite(session, label="Maya")
        session.commit()
    assert auth.authenticate(f"  {code}\n") is not None


def test_authenticate_rejects_unknown_and_empty_codes(patched_sessions):
    assert auth.authenticate("nope") is None
    assert auth.authenticate("") is None


def test_authenticate_rejects_a_revoked_code(patched_sessions):
    with patched_sessions() as session:
        code = create_invite(session, label="Maya")
        assert revoke_invite(session, "Maya") == 1
        session.commit()
    assert auth.authenticate(code) is None


def test_load_identity_returns_none_once_revoked(patched_sessions):
    with patched_sessions() as session:
        code = create_invite(session, label="Maya")
        session.commit()
    identity = auth.authenticate(code)
    with patched_sessions() as session:
        revoke_invite(session, "Maya")
        session.commit()
    assert auth.load_identity(identity.id) is None


def test_cli_create_list_revoke(patched_sessions, capsys):
    assert main(["create", "--label", "Maya", "--tenant-slug", "maya"]) == 0
    printed = capsys.readouterr().out
    code = printed.split(":")[-1].strip()
    assert auth.authenticate(code) is not None

    assert main(["list"]) == 0
    listing = capsys.readouterr().out
    assert "Maya" in listing and code not in listing

    assert main(["revoke", "--label", "Maya"]) == 0
    assert auth.authenticate(code) is None
