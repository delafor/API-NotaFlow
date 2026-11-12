import datetime
import hashlib
import hmac
import os
import re
import statistics
from typing import Dict, List, Optional, Tuple


# Segredo de servidor para anonimização HMAC-SHA256 irreversível de contribuidores (LGPD)
_ANON_SECRET = os.getenv("COLLAB_ANON_SECRET", "notaflow-collab-lgpd-hmac-salt-v1").encode("utf-8")


def gerar_identificador_anonimo_contribuicao(uid: str) -> str:
    """
    Gera um identificador anônimo unidirecional (HMAC-SHA256) a partir do UID validado.
    Permite contabilizar quantos usuários distintos contribuíram com preços para um produto
    sem jamais armazenar ou expor o UID real na base colaborativa.
    """
    if not uid or not uid.strip():
        raise ValueError("UID obrigatório para geração de identificador anônimo.")
    digest = hmac.new(_ANON_SECRET, uid.strip().encode("utf-8"), hashlib.sha256).hexdigest()
    return f"anon_{digest[:24]}"


def gerar_id_deterministico_contribuicao(
    identificador_nota: str,
    produto_id: str,
    estabelecimento_id: str,
) -> str:
    """
    Gera o ID determinístico do registro em `precos_colaborativos/{registro_id}`.
    Garante idempotência: processar a mesma nota fiscal múltiplas vezes atualiza o mesmo registro,
    nunca duplicando contribuições.
    """
    base = f"{identificador_nota.strip()}__{produto_id.strip()}__{estabelecimento_id.strip()}"
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()[:28]
    return f"reg_{h}"


def parse_data_compra(
    emissao_str: Optional[str],
    data_str: Optional[str] = None,
    referencia_utc: Optional[datetime.datetime] = None,
) -> datetime.datetime:
    """
    Converte a data/hora real de emissão da nota fiscal para datetime UTC.
    """
    agora = referencia_utc or datetime.datetime.now(datetime.timezone.utc)
    candidatos = [emissao_str, data_str]

    for cand in candidatos:
        if not cand or not str(cand).strip():
            continue
        texto = str(cand).strip()

        # Formato DD/MM/YYYY HH:MM:SS ou DD/MM/YYYY
        m_br = re.search(
            r"(\d{2})/(\d{2})/(\d{4})(?:[\s-]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?",
            texto,
        )
        if m_br:
            try:
                dia = int(m_br.group(1))
                mes = int(m_br.group(2))
                ano = int(m_br.group(3))
                hora = int(m_br.group(4)) if m_br.group(4) else 12
                minuto = int(m_br.group(5)) if m_br.group(5) else 0
                segundo = int(m_br.group(6)) if m_br.group(6) else 0
                dt = datetime.datetime(ano, mes, dia, hora, minuto, segundo, tzinfo=datetime.timezone.utc)
                # Se a nota de teste tiver ano futuro (ex: 2026 no arquivo de exemplo), limita ao momento atual se necessário
                if dt > agora + datetime.timedelta(days=2):
                    return agora
                return dt
            except ValueError:
                pass

        # Formato ISO-8601
        try:
            dt_iso = datetime.datetime.fromisoformat(texto.replace("Z", "+00:00"))
            if dt_iso.tzinfo is None:
                dt_iso = dt_iso.replace(tzinfo=datetime.timezone.utc)
            if dt_iso > agora + datetime.timedelta(days=2):
                return agora
            return dt_iso
        except ValueError:
            pass

    return agora


def classificar_condicao_preco(
    quantidade_comprada: float,
    unidade_medida: str,
    desconto_nota: Optional[float] = None,
    nome_bruto: str = "",
) -> str:
    """
    Identifica se o preço registrado refere-se a condição NORMAL, ATACADO ou PROMOCAO,
    evitando misturar condições especiais sem identificação.
    """
    upper = (nome_bruto or "").upper()
    if "PROMO" in upper or "OFERTA" in upper or (desconto_nota and desconto_nota > 0):
        return "PROMOCAO"
    if "ATACADO" in upper or "CX FECHADA" in upper or "FARDO" in upper:
        return "ATACADO"
    # Compra de 12 ou mais unidades do mesmo item unitário sugere preço de atacado
    if unidade_medida == "UN" and quantidade_comprada >= 12:
        return "ATACADO"
    return "NORMAL"


def validar_preco_comercial(
    preco_unitario: float,
    precos_referencia_regiao: Optional[List[float]] = None,
) -> Tuple[str, Optional[str]]:
    """
    Valida se o preço comercial é plausível e previne manipulação / anomalias:
    Retorna: (status_validacao, motivo)
      - 'APROVADO': preço válido e consistente.
      - 'QUARENTENA_OUTLIER': valor anormalmente distante da mediana regional (mantido fora do ranking principal).
      - 'REJEITADO': valor inválido (<= 0, NaN ou acima do teto de segurança).
    """
    if preco_unitario is None or preco_unitario <= 0.01:
        return "REJEITADO", "Preço unitário menor ou igual a zero."

    if preco_unitario > 25000.0:
        return "REJEITADO", "Preço unitário excede o limite máximo comercial permitido."

    if precos_referencia_regiao and len(precos_referencia_regiao) >= 3:
        valores_limpos = [p for p in precos_referencia_regiao if p and p > 0]
        if len(valores_limpos) >= 3:
            mediana = statistics.median(valores_limpos)
            if mediana > 0:
                # Rejeita para quarentena se for menor que 25% da mediana (ex: erro de centavos)
                # ou maior que 300% da mediana (ex: fardo lançado como unidade)
                if preco_unitario < (mediana * 0.25) or preco_unitario > (mediana * 3.0):
                    return (
                        "QUARENTENA_OUTLIER",
                        f"Preço R$ {preco_unitario:.2f} diverge acentuadamente da mediana regional (R$ {mediana:.2f}).",
                    )

    return "APROVADO", None

