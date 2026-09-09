from pathlib import Path

from ai_actuator.tunnel import _extract_trycloudflare_url, discover_cloudflared


def test_extract_trycloudflare_url():
    line = "INF | https://doom-pure-secrets-michigan.trycloudflare.com |"
    assert _extract_trycloudflare_url(line) == "https://doom-pure-secrets-michigan.trycloudflare.com"


def test_extract_trycloudflare_url_none():
    assert _extract_trycloudflare_url("no public URL here") is None


def test_discover_explicit_cloudflared(tmp_path: Path):
    executable = tmp_path / "cloudflared.exe"
    executable.write_bytes(b"fake")
    assert discover_cloudflared(str(executable)) == executable.resolve()
