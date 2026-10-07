import ipaddress
import logging
import os
import re
import socket
import time
import urllib.parse
from collections import defaultdict
from typing import List, Optional, Tuple

import requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Cloud metadata, localhost, and non-routable hostnames
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "169.254.169.254",
    "instance-data",
}

# Default allowlist of SEFAZ / SVRS fiscal portals
DEFAULT_ALLOWED_DOMAINS = [
    "svrs.rs.gov.br",
    "dfe-portal.svrs.rs.gov.br",
    "sefaz.ba.gov.br",
    "sefaz.rs.gov.br",
    "sefaz.mg.gov.br",
    "sefaz.sp.gov.br",
    "sefaz.pr.gov.br",
    "sefaz.go.gov.br",
    "sefaz.pe.gov.br",
    "sefaz.ce.gov.br",
    "sefaz.mt.gov.br",
    "sefaz.ms.gov.br",
    "sefaz.am.gov.br",
    "sefaz.pb.gov.br",
    "sefaz.rn.gov.br",
    "sefaz.al.gov.br",
    "sefaz.pi.gov.br",
    "sefaz.ma.gov.br",
    "sefaz.se.gov.br",
    "sefaz.es.gov.br",
    "sefaz.rr.gov.br",
    "sefaz.ap.gov.br",
    "sefaz.ac.gov.br",
    "sefaz.ro.gov.br",
    "sefaz.df.gov.br",
    "gov.br",
]


def get_allowed_domains() -> List[str]:
    raw = os.getenv("ALLOWED_DOMAINS", "")
    if not raw.strip():
        return DEFAULT_ALLOWED_DOMAINS
    env_domains = [d.strip().lower() for d in raw.split(",") if d.strip()]
    return list(set(DEFAULT_ALLOWED_DOMAINS + env_domains))


def is_ip_blocked(ip_str: str) -> bool:
    """
    Checks if an IP address string belongs to loopback, private, link-local,
    multicast, reserved, unspecified, or cloud metadata ranges.
    """
    try:
        ip = ipaddress.ip_address(ip_str)

        # Handle IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped

        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return True

        # Explicit Cloud Metadata IP check
        if str(ip) == "169.254.169.254":
            return True

        return False
    except ValueError:
        return True


def is_domain_allowed(hostname: str) -> bool:
    """
    Strictly checks whether hostname matches an allowed domain or ends with .domain.
    Prevents domain spoofing (e.g., evil-sefaz.gov.br.attacker.com).
    """
    hostname = hostname.lower().strip(".")
    if hostname in BLOCKED_HOSTNAMES:
        return False

    allowed_list = get_allowed_domains()
    for domain in allowed_list:
        domain = domain.lower().strip(".")
        if hostname == domain or hostname.endswith("." + domain):
            return True
    return False


def validate_url(url: str) -> urllib.parse.ParseResult:
    """
    Validates scheme, length, credentials, hostname, domain allowlist, and IP address for SSRF safety.
    """
    if not url or len(url) > 2048:
        raise ValueError("URL inválida ou excede o tamanho máximo de 2048 caracteres.")

    parsed = urllib.parse.urlparse(url)

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Esquema de URL '{parsed.scheme}' não é permitido. Apenas HTTP e HTTPS são aceitos.")

    if parsed.username or parsed.password:
        raise ValueError("URLs contendo credenciais de usuário (user:pass@host) são proibidas.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL não contém um hostname válido.")

    hostname_clean = hostname.lower().strip(".")

    if hostname_clean in BLOCKED_HOSTNAMES:
        raise ValueError(f"Acesso ao host '{hostname}' é proibido por razões de segurança.")

    # Domain allowlist check
    if not is_domain_allowed(hostname_clean):
        raise ValueError(f"O domínio '{hostname}' não está na lista de domínios fiscais permitidos.")

    # Port validation
    if parsed.port and parsed.port not in (80, 443):
        raise ValueError(f"Porta '{parsed.port}' não é permitida. Apenas portas padrão HTTP/HTTPS (80, 443) são aceitas.")

    # DNS resolution and Anti-SSRF IP check
    try:
        target_port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        addr_info = socket.getaddrinfo(hostname_clean, target_port)
        for item in addr_info:
            ip_addr = item[4][0]
            if is_ip_blocked(ip_addr):
                raise ValueError(f"O IP resolvido '{ip_addr}' para o host '{hostname}' é privado ou restrito.")
    except socket.gaierror:
        raise ValueError(f"Não foi possível resolver o endereço IP do host '{hostname}'.")

    return parsed


def safe_http_request(
    url: str,
    method: str = "GET",
    data: Optional[dict] = None,
    headers: Optional[dict] = None,
    session: Optional[requests.Session] = None,
) -> Tuple[str, str, requests.Response]:
    """
    Executes an HTTP GET or POST request safely:
    - Validates target URL against SSRF checks.
    - Does NOT follow redirects blindly (allow_redirects=False).
    - Inspects Location header and re-validates redirect URLs through validate_url().
    - Streams response and enforces MAX_CONTENT_LENGTH limit.
    - Applies connect and read timeouts.
    
    Returns (html_text, final_url, response_object).
    """
    max_redirects = int(os.getenv("MAX_REDIRECTS", "5"))
    max_content_length = int(os.getenv("MAX_CONTENT_LENGTH", str(5 * 1024 * 1024)))
    connect_timeout = float(os.getenv("HTTP_CONNECT_TIMEOUT", "5.0"))
    read_timeout = float(os.getenv("HTTP_READ_TIMEOUT", "15.0"))
    timeout = (connect_timeout, read_timeout)

    http_session = session or requests.Session()
    current_url = url
    current_method = method.upper()
    current_data = data

    for redirect_count in range(max_redirects + 1):
        # Validate URL before sending request
        validate_url(current_url)

        req_headers = headers.copy() if headers else {}
        
        response = http_session.request(
            method=current_method,
            url=current_url,
            data=current_data,
            headers=req_headers,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )

        # Check for HTTP redirects (301, 302, 303, 307, 308)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            if not location:
                break

            # Resolve relative redirect URLs safely
            next_url = urllib.parse.urljoin(current_url, location)
            
            if redirect_count >= max_redirects:
                raise ValueError("Número máximo de redirecionamentos HTTP excedido.")

            current_url = next_url
            if response.status_code in (301, 302, 303):
                current_method = "GET"
                current_data = None
            continue

        # Check Content-Length header if provided
        content_length_hdr = response.headers.get("Content-Length")
        if content_length_hdr and content_length_hdr.isdigit():
            if int(content_length_hdr) > max_content_length:
                raise ValueError(f"Tamanho do conteúdo ({content_length_hdr} bytes) excede o limite permitido ({max_content_length} bytes).")

        # Stream body in chunks up to max_content_length
        body_bytes = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                body_bytes.extend(chunk)
                if len(body_bytes) > max_content_length:
                    raise ValueError(f"Tamanho da resposta excede o limite máximo permitido de {max_content_length} bytes.")

        response.raise_for_status()

        encoding = response.encoding or "utf-8"
        try:
            html_text = body_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            html_text = body_bytes.decode("utf-8", errors="replace")

        return html_text, current_url, response

    raise ValueError("Falha ao obter resposta HTTP final após redirecionamentos.")


class RateLimiter:
    """In-memory sliding window rate limiter per client key (IP or UID)."""
    def __init__(self, requests_per_minute: int = 20):
        self.rate_limit = requests_per_minute
        self.requests = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        window_start = now - 60.0
        
        # Keep only timestamps in the last 60 seconds
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        
        if len(self.requests[key]) >= self.rate_limit:
            return False
            
        self.requests[key].append(now)
        return True


rate_limiter = RateLimiter(requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "20")))
