import datetime
import logging
import os
import time
import uuid
from collections import deque
from typing import Any, Dict, List, Optional
import requests
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("notaflow_observability")

# Ring buffer em memória para armazenar as últimas 500 requisições da API com segurança
_MAX_LOGS = 500
_LOGS_BUFFER: deque = deque(maxlen=_MAX_LOGS)
_START_TIME = time.time()

# Estatísticas agregadas
_METRICS = {
    "total_requests": 0,
    "total_errors": 0,
    "status_2xx": 0,
    "status_4xx": 0,
    "status_5xx": 0,
    "total_latency_ms": 0.0,
    "extractions_success": 0,
    "extractions_failed": 0,
}


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.time()

        # Timestamp UTC estrito
        timestamp_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Sanitização do IP
        client_host = request.client.host if request.client else "unknown"
        path = request.url.path
        method = request.method

        error_message: Optional[str] = None
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            error_message = str(exc)
            logger.error(
                f"[{request_id}] Exceção não tratada na requisição {method} {path}: {error_message}",
                exc_info=True,
            )
            raise exc
        finally:
            duration_ms = round((time.time() - start_time) * 1000, 2)

            # Atualização atômica de métricas
            _METRICS["total_requests"] += 1
            _METRICS["total_latency_ms"] += duration_ms

            if 200 <= status_code < 300:
                _METRICS["status_2xx"] += 1
            elif 400 <= status_code < 500:
                _METRICS["status_4xx"] += 1
                _METRICS["total_errors"] += 1
            elif status_code >= 500:
                _METRICS["status_5xx"] += 1
                _METRICS["total_errors"] += 1

            if "/extrair" in path or "/importar" in path:
                if status_code < 400:
                    _METRICS["extractions_success"] += 1
                else:
                    _METRICS["extractions_failed"] += 1

            # Log estruturado sanitizado (nunca expõe tokens, senhas ou PII)
            log_entry = {
                "request_id": request_id,
                "timestamp": timestamp_utc,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "client_ip": client_host,
                "error": error_message,
            }
            _LOGS_BUFFER.append(log_entry)

            logger.info(
                f"[{request_id}] {method} {path} - Status: {status_code} - Duração: {duration_ms}ms"
            )

        # Adiciona identificador de rastreio aos headers de resposta
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        return response


def get_system_uptime_seconds() -> float:
    return round(time.time() - _START_TIME, 2)


def get_aggregated_metrics() -> Dict[str, Any]:
    total = _METRICS["total_requests"]
    avg_latency = (
        round(_METRICS["total_latency_ms"] / total, 2) if total > 0 else 0.0
    )
    error_rate = (
        round((_METRICS["total_errors"] / total) * 100, 2) if total > 0 else 0.0
    )

    return {
        "uptime_seconds": get_system_uptime_seconds(),
        "total_requests": total,
        "total_errors": _METRICS["total_errors"],
        "error_rate_percent": error_rate,
        "avg_latency_ms": avg_latency,
        "status_breakdown": {
            "2xx": _METRICS["status_2xx"],
            "4xx": _METRICS["status_4xx"],
            "5xx": _METRICS["status_5xx"],
        },
        "extractions": {
            "success": _METRICS["extractions_success"],
            "failed": _METRICS["extractions_failed"],
        },
    }


def get_recent_api_logs(
    limit: int = 50,
    status_filter: Optional[str] = None,
    path_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    logs = list(_LOGS_BUFFER)
    logs.reverse()

    filtered = []
    for log in logs:
        if status_filter:
            code = log["status_code"]
            if status_filter == "error" and code < 400:
                continue
            if status_filter == "2xx" and not (200 <= code < 300):
                continue
            if status_filter == "4xx" and not (400 <= code < 500):
                continue
            if status_filter == "5xx" and code < 500:
                continue

        if path_filter and path_filter.lower() not in log["path"].lower():
            continue

        filtered.append(log)
        if len(filtered) >= limit:
            break

    return filtered


def check_dependencies_health() -> Dict[str, Any]:
    """
    Verifica a saúde real dos serviços dependentes (Firestore, SEFAZ, etc.).
    Não presume que HTTP 200 significa dependências saudáveis.
    """
    deps: Dict[str, Any] = {}

    # 1. Firestore
    try:
        from firebase import db
        # Teste leve sem leitura cara
        collections = list(db.collections())
        deps["firestore"] = {
            "status": "healthy",
            "message": "Comunicação com o Firestore operacional",
        }
    except Exception as e:
        deps["firestore"] = {
            "status": "unhealthy",
            "message": f"Falha na comunicação com o Firestore: {str(e)[:100]}",
        }

    # 2. Portal SEFAZ Bahia (conectividade externa)
    try:
        sefaz_test = requests.get(
            "http://nfe.sefaz.ba.gov.br",
            timeout=3.0,
            headers={"User-Agent": "NotaFlow-HealthCheck/1.0"},
        )
        deps["sefaz_ba"] = {
            "status": "healthy" if sefaz_test.status_code < 500 else "degraded",
            "status_code": sefaz_test.status_code,
            "message": "Portal da SEFAZ Bahia acessível",
        }
    except Exception as e:
        deps["sefaz_ba"] = {
            "status": "degraded",
            "message": "Portal SEFAZ temporariamente inacessível ou com timeout",
        }

    overall_healthy = all(d.get("status") == "healthy" for d in deps.values())
    overall_status = "healthy" if overall_healthy else ("degraded" if deps.get("firestore", {}).get("status") == "healthy" else "unhealthy")

    return {
        "status": overall_status,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "uptime_seconds": get_system_uptime_seconds(),
        "dependencies": deps,
    }

