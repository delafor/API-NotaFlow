import hashlib
import re
from typing import Dict, Optional, Tuple

from collaborative.normalizer import remover_acentos


ABREVIACOES_ESTABELECIMENTO = {
    "MERC": "MERCADO",
    "MERC.": "MERCADO",
    "MERCAD": "MERCADO",
    "SUPERM": "SUPERMERCADO",
    "SUPERMERC": "SUPERMERCADO",
    "SUP": "SUPERMERCADO",
    "SUP.": "SUPERMERCADO",
    "ATAC": "ATACADISTA",
    "ATAC.": "ATACADISTA",
    "COM": "COMERCIO",
    "COM.": "COMERCIO",
    "DIST": "DISTRIBUIDORA",
    "LTDA": "",
    "LTDA.": "",
    "S/A": "",
    "S.A.": "",
    "S.A": "",
    "EIRELI": "",
    "ME": "",
    "EPP": "",
}


def validar_cnpj(cnpj: Optional[str]) -> Optional[str]:
    """
    Valida dígitos verificadores oficiais do CNPJ de 14 dígitos.
    Retorna os 14 dígitos limpos se válido, ou None caso contrário.
    """
    if not cnpj:
        return None
    limpo = re.sub(r"\D", "", str(cnpj))
    if len(limpo) != 14 or len(set(limpo)) == 1:
        return None

    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma_1 = sum(int(limpo[i]) * pesos_1[i] for i in range(12))
    resto_1 = soma_1 % 11
    dv_1 = 0 if resto_1 < 2 else 11 - resto_1
    if int(limpo[12]) != dv_1:
        return None

    pesos_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma_2 = sum(int(limpo[i]) * pesos_2[i] for i in range(13))
    resto_2 = soma_2 % 11
    dv_2 = 0 if resto_2 < 2 else 11 - resto_2
    if int(limpo[13]) != dv_2:
        return None

    return limpo


def extrair_cnpj_da_chave(chave: Optional[str]) -> Optional[str]:
    """Extrai e valida o CNPJ do emissor (posições 7 a 20) de uma chave fiscal de 44 dígitos."""
    if not chave:
        return None
    limpa = re.sub(r"\D", "", str(chave))
    if len(limpa) == 44:
        return validar_cnpj(limpa[6:20])
    return None


def normalizar_nome_estabelecimento(nome_bruto: Optional[str]) -> Tuple[str, str]:
    """
    Normaliza o nome do estabelecimento evitando duplicações por variação de escrita:
    Ex: 'Mercado Central', 'MERCADO CENTRAL', 'Merc. Central LTDA' -> ('MERCADO CENTRAL', 'Mercado Central')
    """
    if not nome_bruto or not nome_bruto.strip():
        return "ESTABELECIMENTO COMERCIAL", "Estabelecimento Comercial"

    sem_acento = remover_acentos(nome_bruto).upper()
    sem_acento = re.sub(r"[^\w\s.&/-]", " ", sem_acento)
    tokens = sem_acento.split()

    tokens_norm = []
    for idx, tk in enumerate(tokens):
        tk_clean = tk.strip(".-/")
        if not tk_clean:
            continue
        # Se for a primeira palavra, expande abreviações de tipo (ex: Merc. Central -> MERCADO CENTRAL)
        if tk in ABREVIACOES_ESTABELECIMENTO:
            exp = ABREVIACOES_ESTABELECIMENTO[tk]
            if exp:
                tokens_norm.append(exp)
        elif tk_clean in ABREVIACOES_ESTABELECIMENTO:
            exp = ABREVIACOES_ESTABELECIMENTO[tk_clean]
            if exp:
                tokens_norm.append(exp)
        else:
            tokens_norm.append(tk_clean)

    if not tokens_norm:
        tokens_norm = [re.sub(r"\W+", "", sem_acento) or "MERCADO"]

    nome_canonico = " ".join(tokens_norm)
    # Remove palavras duplicadas adjacentes (ex: "SUPERMERCADO SUPERMERCADO X")
    dedup = []
    for p in nome_canonico.split():
        if not dedup or dedup[-1] != p:
            dedup.append(p)
    nome_canonico = " ".join(dedup)

    # Formatação elegante para exibição
    preposicoes = {"DE", "DA", "DO", "DAS", "DOS", "E"}
    palavras_exib = []
    for i, p in enumerate(nome_canonico.split()):
        if i > 0 and p in preposicoes:
            palavras_exib.append(p.lower())
        elif len(p) <= 2 and p not in ("PA", "BA", "SP", "RJ"):
            palavras_exib.append(p.upper())
        else:
            palavras_exib.append(p.capitalize())

    nome_exibicao = " ".join(palavras_exib)
    return nome_canonico, nome_exibicao


def _extrair_identificador_filial_endereco(endereco: Optional[str]) -> Optional[str]:
    """Extrai logradouro + número ou bairro para diferenciar filiais quando não há CNPJ."""
    if not endereco or not endereco.strip():
        return None
    limpo = remover_acentos(endereco).upper()
    partes = [re.sub(r"[^\w\s]", "", p).strip() for p in limpo.split(",") if p.strip()]
    if not partes:
        return None
    # Usa as 2 primeiras partes (logradouro + número)
    trecho = "_".join(partes[:2])
    trecho = re.sub(r"\s+", "_", trecho)[:35]
    return trecho if trecho else None


def resolver_estabelecimento(
    nome_bruto: Optional[str],
    cnpj_bruto: Optional[str] = None,
    chave_nota: Optional[str] = None,
    endereco_comercial: Optional[str] = None,
    cidade_id: str = "desconhecida",
    nome_cidade: str = "Não informada",
    uf: str = "BR",
) -> Dict:
    """
    Resolve a identidade padronizada de um estabelecimento comercial:
    1. Se houver CNPJ válido (14 dígitos, que inclui o sufixo de filial /0001, /0002),
       utiliza `cnpj_<14_digitos>` como identificador inequívoco daquela unidade/filial.
    2. Se não houver CNPJ, combina `cidade_id` + `nome_canonico` + `assinatura_endereco` (quando presente)
       para que 'Mercado Central', 'MERCADO CENTRAL' e 'Merc. Central' na mesma cidade convirjam,
       mas filiais em endereços/cidades distintas não sejam fundidas indevidamente.
    """
    cnpj = validar_cnpj(cnpj_bruto) or extrair_cnpj_da_chave(chave_nota)
    nome_canonico, nome_exibicao = normalizar_nome_estabelecimento(nome_bruto)
    filial_end = _extrair_identificador_filial_endereco(endereco_comercial)

    raiz_cnpj = cnpj[:8] if cnpj else None
    ordem_filial_cnpj = cnpj[8:12] if cnpj else None

    if cnpj:
        estabelecimento_id = f"cnpj_{cnpj}"
        # Se for filial (> 0001) e houver bairro/endereço, enriquece o nome de exibição para diferenciar filiais na UI
        if ordem_filial_cnpj and ordem_filial_cnpj != "0001" and endereco_comercial:
            partes_end = [p.strip() for p in endereco_comercial.split(",") if p.strip()]
            bairro_cand = partes_end[2].title() if len(partes_end) >= 4 else f"Filial {int(ordem_filial_cnpj)}"
            if bairro_cand.lower() not in nome_exibicao.lower():
                nome_exibicao = f"{nome_exibicao} ({bairro_cand})"
    else:
        slug_nome = re.sub(r"[^a-z0-9]+", "_", nome_canonico.lower()).strip("_")
        base_hash_str = f"{cidade_id.lower()}__{slug_nome}"
        if filial_end:
            base_hash_str += f"__{filial_end.lower()}"
        hash_curto = hashlib.sha256(base_hash_str.encode("utf-8")).hexdigest()[:14]
        estabelecimento_id = f"est_{cidade_id.lower()}_{slug_nome[:20]}_{hash_curto}"

    return {
        "estabelecimento_id": estabelecimento_id,
        "cnpj": cnpj,
        "raiz_cnpj": raiz_cnpj,
        "ordem_filial": ordem_filial_cnpj,
        "nome_normalizado": nome_canonico,
        "nome_exibicao": nome_exibicao,
        "endereco_comercial": endereco_comercial,
        "cidade_id": cidade_id,
        "nome_cidade": nome_cidade,
        "uf": uf,
    }
