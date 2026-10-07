import os
import sys

# Garante que a raiz do projeto esteja no sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from security import is_domain_allowed, is_ip_blocked, validate_url


def assert_raises_value_error(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
        raise AssertionError(f"Esperava ValueError para {func.__name__}({args}), mas nenhuma exceção foi lançada.")
    except ValueError:
        pass


def test_ip_blocking_private_and_loopback():
    assert is_ip_blocked("127.0.0.1") is True
    assert is_ip_blocked("10.0.0.1") is True
    assert is_ip_blocked("172.16.0.1") is True
    assert is_ip_blocked("192.168.1.1") is True
    assert is_ip_blocked("169.254.169.254") is True
    assert is_ip_blocked("0.0.0.0") is True
    assert is_ip_blocked("::1") is True
    assert is_ip_blocked("::ffff:127.0.0.1") is True


def test_domain_allowlist():
    assert is_domain_allowed("dfe-portal.svrs.rs.gov.br") is True
    assert is_domain_allowed("subdomain.sefaz.ba.gov.br") is True
    assert is_domain_allowed("localhost") is False
    assert is_domain_allowed("metadata.google.internal") is False
    assert is_domain_allowed("evil-sefaz.gov.br.attacker.com") is False
    assert is_domain_allowed("attacker.com") is False


def test_validate_url_ssrf_protection():
    # Valid SEFAZ URL format
    parsed = validate_url("https://dfe-portal.svrs.rs.gov.br/board/bpe")
    assert parsed.hostname == "dfe-portal.svrs.rs.gov.br"

    # Blocked schemes
    assert_raises_value_error(validate_url, "file:///etc/passwd")
    assert_raises_value_error(validate_url, "ftp://dfe-portal.svrs.rs.gov.br/test")

    # Blocked credentials in URL
    assert_raises_value_error(validate_url, "https://user:pass@dfe-portal.svrs.rs.gov.br/test")

    # Blocked unallowed domain
    assert_raises_value_error(validate_url, "https://attacker.com/malicious")

    # Blocked loopback / internal IP in URL
    assert_raises_value_error(validate_url, "http://127.0.0.1:8000/internal")


if __name__ == "__main__":
    test_ip_blocking_private_and_loopback()
    test_domain_allowlist()
    test_validate_url_ssrf_protection()
    print("Todos os testes de segurança em test_security.py passaram com sucesso!")

