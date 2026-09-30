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
