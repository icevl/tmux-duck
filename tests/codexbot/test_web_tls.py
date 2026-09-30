"""HTTPS is served only when <state dir>/tls holds a cert and a key."""

from codexbot.web import server


def test_tls_files_need_both_cert_and_key(tmp_path, monkeypatch):
    monkeypatch.setattr(server.config, "config_dir", tmp_path)
    assert server.tls_files() is None

    tls = tmp_path / "tls"
    tls.mkdir()
    (tls / "cert.pem").write_text("cert")
    assert server.tls_files() is None

    (tls / "key.pem").write_text("key")
    assert server.tls_files() == (tls / "cert.pem", tls / "key.pem")


def test_ca_certificate_is_public(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from codexbot import config as config_module
    from codexbot.web.api import create_app
    from codexbot.web.events import EventBus

    monkeypatch.setattr(config_module.config, "config_dir", tmp_path)
    monkeypatch.setattr(config_module.config, "web_ui_password", "pw")
    client = TestClient(create_app(EventBus()))

    assert client.get("/ca.crt").status_code == 404

    tls = tmp_path / "tls"
    tls.mkdir()
    (tls / "rootCA.pem").write_text("-----BEGIN CERTIFICATE-----\n")
    r = client.get("/ca.crt")  # no login: the phone fetches it before trusting us
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/x-x509-ca-cert"
    assert r.text.startswith("-----BEGIN CERTIFICATE-----")
