import math
import re
from typing import Dict, List, Optional, Tuple

from collaborative.normalizer import remover_acentos
from extractor import COD_UF_IBGE


# Base geográfica determinística de municípios (Código IBGE, Nome, UF, Região, Lat, Lon)
# Utilizada para cálculo de distância entre municípios (ex: até 30 km) sem rastreamento GPS de usuários.
CATALOGO_MUNICIPIOS: Dict[str, Dict] = {
    "2928901": {
        "codigo_ibge": "2928901",
        "nome": "Santa Inês",
        "uf": "BA",
        "regiao_id": "ba_vale_jiquirica",
        "nome_regiao": "Vale do Jiquiriçá - BA",
        "lat": -13.2922,
        "lon": -39.8189,
    },
    "2922409": {
        "codigo_ibge": "2922409",
        "nome": "Mutuípe",
        "uf": "BA",
        "regiao_id": "ba_vale_jiquirica",
        "nome_regiao": "Vale do Jiquiriçá - BA",
        "lat": -13.2269,
        "lon": -39.5042,
    },
    "2917607": {
        "codigo_ibge": "2917607",
        "nome": "Jaguaquara",
        "uf": "BA",
        "regiao_id": "ba_vale_jiquirica",
        "nome_regiao": "Vale do Jiquiriçá - BA",
        "lat": -13.5308,
        "lon": -39.9708,
    },
    "2932002": {
        "codigo_ibge": "2932002",
        "nome": "Ubaíra",
        "uf": "BA",
        "regiao_id": "ba_vale_jiquirica",
        "nome_regiao": "Vale do Jiquiriçá - BA",
        "lat": -13.2681,
        "lon": -39.6628,
    },
    "2908903": {
        "codigo_ibge": "2908903",
        "nome": "Cravolândia",
        "uf": "BA",
        "regiao_id": "ba_vale_jiquirica",
        "nome_regiao": "Vale do Jiquiriçá - BA",
        "lat": -13.3589,
        "lon": -39.8147,
    },
    "2901007": {
        "codigo_ibge": "2901007",
        "nome": "Amargosa",
        "uf": "BA",
        "regiao_id": "ba_vale_jiquirica",
        "nome_regiao": "Vale do Jiquiriçá - BA",
        "lat": -13.0303,
        "lon": -39.6047,
    },
    "2918001": {
        "codigo_ibge": "2918001",
        "nome": "Jequié",
        "uf": "BA",
        "regiao_id": "ba_sudoeste_jequie",
        "nome_regiao": "Região de Jequié - BA",
        "lat": -13.8575,
        "lon": -40.0836,
    },
    "2928703": {
        "codigo_ibge": "2928703",
        "nome": "Santo Antônio de Jesus",
        "uf": "BA",
        "regiao_id": "ba_reconcavo",
        "nome_regiao": "Recôncavo Baiano - BA",
        "lat": -12.9689,
        "lon": -39.2614,
    },
    "2927408": {
        "codigo_ibge": "2927408",
        "nome": "Salvador",
        "uf": "BA",
        "regiao_id": "ba_metropolitana_salvador",
        "nome_regiao": "Região Metropolitana de Salvador - BA",
        "lat": -12.9714,
        "lon": -38.5014,
    },
    "2919207": {
        "codigo_ibge": "2919207",
        "nome": "Lauro de Freitas",
        "uf": "BA",
        "regiao_id": "ba_metropolitana_salvador",
        "nome_regiao": "Região Metropolitana de Salvador - BA",
        "lat": -12.8944,
        "lon": -38.3272,
    },
    "2905701": {
        "codigo_ibge": "2905701",
        "nome": "Camaçari",
        "uf": "BA",
        "regiao_id": "ba_metropolitana_salvador",
        "nome_regiao": "Região Metropolitana de Salvador - BA",
        "lat": -12.6975,
        "lon": -38.3242,
    },
    "2910800": {
        "codigo_ibge": "2910800",
        "nome": "Feira de Santana",
        "uf": "BA",
        "regiao_id": "ba_feira_santana",
        "nome_regiao": "Região de Feira de Santana - BA",
        "lat": -12.2664,
        "lon": -38.9664,
    },
    "3550308": {
        "codigo_ibge": "3550308",
        "nome": "São Paulo",
        "uf": "SP",
        "regiao_id": "sp_metropolitana",
        "nome_regiao": "Região Metropolitana de São Paulo - SP",
        "lat": -23.5505,
        "lon": -46.6333,
    },
    "3518800": {
        "codigo_ibge": "3518800",
        "nome": "Guarulhos",
        "uf": "SP",
        "regiao_id": "sp_metropolitana",
        "nome_regiao": "Região Metropolitana de São Paulo - SP",
        "lat": -23.4543,
        "lon": -46.5337,
    },
    "3534401": {
        "codigo_ibge": "3534401",
        "nome": "Osasco",
        "uf": "SP",
        "regiao_id": "sp_metropolitana",
        "nome_regiao": "Região Metropolitana de São Paulo - SP",
        "lat": -23.5325,
        "lon": -46.7917,
    },
    "3547809": {
        "codigo_ibge": "3547809",
        "nome": "Santo André",
        "uf": "SP",
        "regiao_id": "sp_metropolitana",
        "nome_regiao": "Região Metropolitana de São Paulo - SP",
        "lat": -23.6639,
        "lon": -46.5383,
    },
    "3548708": {
        "codigo_ibge": "3548708",
        "nome": "São Bernardo do Campo",
        "uf": "SP",
        "regiao_id": "sp_metropolitana",
        "nome_regiao": "Região Metropolitana de São Paulo - SP",
        "lat": -23.6944,
        "lon": -46.5654,
    },
    "3304557": {
        "codigo_ibge": "3304557",
        "nome": "Rio de Janeiro",
        "uf": "RJ",
        "regiao_id": "rj_metropolitana",
        "nome_regiao": "Região Metropolitana do Rio de Janeiro - RJ",
        "lat": -22.9068,
        "lon": -43.1729,
    },
    "3303302": {
        "codigo_ibge": "3303302",
        "nome": "Niterói",
        "uf": "RJ",
        "regiao_id": "rj_metropolitana",
        "nome_regiao": "Região Metropolitana do Rio de Janeiro - RJ",
        "lat": -22.8832,
        "lon": -43.1034,
    },
    "3106200": {
        "codigo_ibge": "3106200",
        "nome": "Belo Horizonte",
        "uf": "MG",
        "regiao_id": "mg_metropolitana",
        "nome_regiao": "Região Metropolitana de Belo Horizonte - MG",
        "lat": -19.9167,
        "lon": -43.9345,
    },
    "4106902": {
        "codigo_ibge": "4106902",
        "nome": "Curitiba",
        "uf": "PR",
        "regiao_id": "pr_metropolitana",
        "nome_regiao": "Região Metropolitana de Curitiba - PR",
        "lat": -25.4284,
        "lon": -49.2733,
    },
    "4314902": {
        "codigo_ibge": "4314902",
        "nome": "Porto Alegre",
        "uf": "RS",
        "regiao_id": "rs_metropolitana",
        "nome_regiao": "Região Metropolitana de Porto Alegre - RS",
        "lat": -30.0346,
        "lon": -51.2177,
    },
}


# Índice auxiliar por (UF, NOME_SEM_ACENTO) -> codigo_ibge
INDICE_NOME_UF_IBGE: Dict[Tuple[str, str], str] = {}
for _ibge, _dados in CATALOGO_MUNICIPIOS.items():
    _chave = (_dados["uf"].upper(), remover_acentos(_dados["nome"]).upper())
    INDICE_NOME_UF_IBGE[_chave] = _ibge


def calcular_distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Fórmula de Haversine para calcular distância aproximada em km entre dois municípios."""
    raio_terra_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(raio_terra_km * c, 1)


def _slug_municipio(municipio: str, uf: str) -> str:
    mun_clean = re.sub(r"[^a-z0-9]+", "_", remover_acentos(municipio).lower()).strip("_")
    uf_clean = re.sub(r"[^a-z]+", "", (uf or "br").lower())[:2]
    return f"{uf_clean}_{mun_clean}" if mun_clean else f"{uf_clean}_geral"


def identificar_regiao(
    municipio: Optional[str] = None,
    uf: Optional[str] = None,
    codigo_ibge: Optional[str] = None,
    chave_nota: Optional[str] = None,
    endereco_nota: Optional[str] = None,
) -> Dict:
    """
    Resolve a identificação regional priorizando:
    1. Código IBGE de 7 dígitos (quando fornecido ou extraído da nota)
    2. Par (Município, UF)
    3. Extração a partir do endereço comercial da nota
    4. UF extraída dos 2 primeiros dígitos da chave de acesso fiscal
    """
    # Fallback de UF pela chave de acesso
    if not uf and chave_nota:
        limpa = re.sub(r"\D", "", str(chave_nota))
        if len(limpa) >= 2:
            uf = COD_UF_IBGE.get(limpa[:2])

    # Fallback de município/UF pelo endereço comercial da nota
    if (not municipio or not uf) and endereco_nota:
        partes = [p.strip() for p in endereco_nota.split(",") if p.strip()]
        if len(partes) >= 2:
            possivel_uf = partes[-1].upper().strip()
            if len(possivel_uf) == 2 and possivel_uf.isalpha():
                uf = uf or possivel_uf
                cand_mun = partes[-2].strip()
                m_ibge = re.match(r"^(\d{7})\s*-\s*(.+)$", cand_mun)
                if m_ibge:
                    codigo_ibge = codigo_ibge or m_ibge.group(1)
                    municipio = municipio or m_ibge.group(2).strip()
                else:
                    municipio = municipio or cand_mun

    uf_norm = (uf or "BA").strip().upper()[:2]

    # 1. Tenta resolver diretamente pelo código IBGE no catálogo
    if codigo_ibge:
        ibge_limpo = re.sub(r"\D", "", str(codigo_ibge))
        if ibge_limpo in CATALOGO_MUNICIPIOS:
            cat = CATALOGO_MUNICIPIOS[ibge_limpo]
            return {
                "cidade_id": ibge_limpo,
                "codigo_ibge": ibge_limpo,
                "nome_cidade": cat["nome"],
                "uf": cat["uf"],
                "regiao_id": cat["regiao_id"],
                "nome_regiao": cat["nome_regiao"],
                "lat": cat["lat"],
                "lon": cat["lon"],
            }

    # 2. Tenta resolver pelo par (UF, Nome do Município)
    if municipio and municipio.strip():
        mun_sem_acento = remover_acentos(municipio).upper().strip()
        # Remove eventual sufixo "(BA)" ou "- BA"
        mun_sem_acento = re.sub(r"\s*\([A-Z]{2}\)\s*$", "", mun_sem_acento)
        mun_sem_acento = re.sub(r"\s*[-/]\s*[A-Z]{2}\s*$", "", mun_sem_acento).strip()

        ibge_encontrado = INDICE_NOME_UF_IBGE.get((uf_norm, mun_sem_acento))
        if not ibge_encontrado:
            # Procura em qualquer UF caso a UF não tenha sido informada com precisão
            for (_u, _n), _cod in INDICE_NOME_UF_IBGE.items():
                if _n == mun_sem_acento:
                    ibge_encontrado = _cod
                    break

        if ibge_encontrado and ibge_encontrado in CATALOGO_MUNICIPIOS:
            cat = CATALOGO_MUNICIPIOS[ibge_encontrado]
            return {
                "cidade_id": ibge_encontrado,
                "codigo_ibge": ibge_encontrado,
                "nome_cidade": cat["nome"],
                "uf": cat["uf"],
                "regiao_id": cat["regiao_id"],
                "nome_regiao": cat["nome_regiao"],
                "lat": cat["lat"],
                "lon": cat["lon"],
            }

        # Município fora do catálogo estático: gera identificador determinístico baseado em UF + slug
        cidade_slug = _slug_municipio(mun_sem_acento, uf_norm)
        ibge_final = re.sub(r"\D", "", str(codigo_ibge)) if codigo_ibge else None
        cidade_id_final = ibge_final if (ibge_final and len(ibge_final) == 7) else cidade_slug
        return {
            "cidade_id": cidade_id_final,
            "codigo_ibge": ibge_final,
            "nome_cidade": municipio.strip().title(),
            "uf": uf_norm,
            "regiao_id": f"{uf_norm.lower()}_regional",
            "nome_regiao": f"Região Estadual - {uf_norm}",
            "lat": None,
            "lon": None,
        }

    # 3. Fallback regional seguro
    return {
        "cidade_id": "2928901",
        "codigo_ibge": "2928901",
        "nome_cidade": "Santa Inês",
        "uf": uf_norm,
        "regiao_id": "ba_vale_jiquirica",
        "nome_regiao": "Vale do Jiquiriçá - BA",
        "lat": -13.2922,
        "lon": -39.8189,
    }


def obter_cidades_abrangencia(
    regiao_base: Dict,
    abrangencia: str = "cidade_e_proximos",
    raio_km: int = 30,
) -> Tuple[List[str], Dict[str, float]]:
    """
    Retorna a lista de `cidade_id` elegíveis para comparação e o mapa de distâncias aproximadas (km):
    - `apenas_cidade`: apenas a própria `cidade_id` do usuário.
    - `cidade_e_proximos`: a própria cidade + municípios dentro do `raio_km` (padrão 30 km) ou mesma microrregião.
    - `regiao_ampliada`: toda a mesorregião (`regiao_id`) e municípios até `max(raio_km * 2, 80)` km na mesma UF.
    """
    cidade_principal = regiao_base["cidade_id"]
    uf_principal = regiao_base["uf"]
    regiao_id = regiao_base["regiao_id"]
    lat_base = regiao_base.get("lat")
    lon_base = regiao_base.get("lon")

    distancias: Dict[str, float] = {cidade_principal: 0.0}
    # Também aceita o slug equivalente da mesma cidade (para compatibilidade de registros com/sem IBGE)
    slug_alt = _slug_municipio(regiao_base["nome_cidade"], uf_principal)
    distancias[slug_alt] = 0.0

    if abrangencia == "apenas_cidade":
        cidades = list(dict.fromkeys([cidade_principal, slug_alt]))
        return cidades, distancias

    limite_km = float(raio_km) if abrangencia == "cidade_e_proximos" else float(max(raio_km * 3, 100))

    for cod_ibge, dados in CATALOGO_MUNICIPIOS.items():
        if cod_ibge == cidade_principal:
            continue
        if dados["uf"] != uf_principal:
            continue

        dist = None
        if lat_base is not None and lon_base is not None and dados.get("lat") is not None:
            dist = calcular_distancia_km(lat_base, lon_base, dados["lat"], dados["lon"])

        incluir = False
        if dist is not None and dist <= limite_km:
            incluir = True
        elif abrangencia == "regiao_ampliada" and dados["regiao_id"] == regiao_id:
            incluir = True
        elif lat_base is None and dados["regiao_id"] == regiao_id:
            incluir = True

        if incluir:
            dist_val = dist if dist is not None else 15.0
            distancias[cod_ibge] = dist_val
            distancias[_slug_municipio(dados["nome"], dados["uf"])] = dist_val

    return list(distancias.keys()), distancias

