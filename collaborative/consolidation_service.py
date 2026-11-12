import datetime
import os
import statistics
from typing import Dict, List, Optional, Tuple

from collaborative.schemas import (
    IndicadorConfiabilidadeSchema,
    PontoHistoricoPrecoSchema,
    PrecoEstabelecimentoSchema,
)


# Limites configuráveis de atualidade (em dias)
DIAS_PRECO_RECENTE = int(os.getenv("COLLAB_DIAS_RECENTE", "7"))
DIAS_PRECO_ATENCAO = int(os.getenv("COLLAB_DIAS_ATENCAO", "30"))
MINIMO_USUARIOS_CONSOLIDADO = 3
AVISO_DADOS_LIMITADOS = "Dados colaborativos limitados nesta região."


def _converter_para_datetime_utc(valor) -> datetime.datetime:
    agora = datetime.datetime.now(datetime.timezone.utc)
    if isinstance(valor, datetime.datetime):
        if valor.tzinfo is None:
            return valor.replace(tzinfo=datetime.timezone.utc)
        return valor
    if isinstance(valor, str) and valor.strip():
        try:
            dt = datetime.datetime.fromisoformat(valor.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        except ValueError:
            pass
    return agora


def calcular_atualidade(
    data_compra: datetime.datetime,
    referencia_utc: Optional[datetime.datetime] = None,
) -> Tuple[int, str, str]:
    """
    Calcula a quantidade de dias desde a compra, o rótulo humano ("Comprado hoje",
    "Comprado ontem", "Comprado há X dias") e o status de atualidade:
    - Até 7 dias: 'RECENTE'
    - De 8 a 30 dias: 'ATENCAO'
    - Acima de 30 dias: 'DESATUALIZADO'
    """
    agora = referencia_utc or datetime.datetime.now(datetime.timezone.utc)
    dt_compra = _converter_para_datetime_utc(data_compra)

    diferenca = agora.date() - dt_compra.date()
    dias = max(0, diferenca.days)

    if dias == 0:
        rotulo = "Comprado hoje"
    elif dias == 1:
        rotulo = "Comprado ontem"
    else:
        rotulo = f"Comprado há {dias} dias"

    if dias <= DIAS_PRECO_RECENTE:
        status = "RECENTE"
    elif dias <= DIAS_PRECO_ATENCAO:
        status = "ATENCAO"
    else:
        status = "DESATUALIZADO"

    return dias, rotulo, status


def calcular_indicador_confiabilidade(
    quantidade_usuarios_distintos: int,
    quantidade_registros_validos: int,
    status_atualidade_melhor: str,
    tem_gtin_ou_exata: bool,
    variacao_relativa: float = 0.0,
) -> IndicadorConfiabilidadeSchema:
    """
    Calcula o indicador de confiabilidade utilizando critérios objetivos e documentados
    (sem inventar porcentagens arbitrárias).
    """
    criterios = []

    if quantidade_usuarios_distintos >= MINIMO_USUARIOS_CONSOLIDADO:
        criterios.append(f"{quantidade_usuarios_distintos} contribuidores distintos na região")
    elif quantidade_usuarios_distintos == 2:
        criterios.append("2 contribuidores distintos na região")
    elif quantidade_usuarios_distintos == 1:
        criterios.append("1 contribuidor registrado na região")

    if status_atualidade_melhor == "RECENTE":
        criterios.append(f"Preços atualizados nos últimos {DIAS_PRECO_RECENTE} dias")
    elif status_atualidade_melhor == "ATENCAO":
        criterios.append(f"Preços registrados entre {DIAS_PRECO_RECENTE + 1} e {DIAS_PRECO_ATENCAO} dias")
    else:
        criterios.append(f"Registros com mais de {DIAS_PRECO_ATENCAO} dias")

    if tem_gtin_ou_exata:
        criterios.append("Identificação padronizada exata do produto")

    if quantidade_registros_validos >= 2 and variacao_relativa <= 0.25:
        criterios.append("Consistência de preços validada entre registros")

    dados_limitados = quantidade_usuarios_distintos < MINIMO_USUARIOS_CONSOLIDADO
    aviso = AVISO_DADOS_LIMITADOS if dados_limitados else None

    if (
        quantidade_usuarios_distintos >= MINIMO_USUARIOS_CONSOLIDADO
        and status_atualidade_melhor == "RECENTE"
        and tem_gtin_ou_exata
    ):
        nivel = "ALTA"
        rotulo = "Confiabilidade Alta · Dados colaborativos consolidados"
    elif (
        quantidade_usuarios_distintos >= 2
        and status_atualidade_melhor in ("RECENTE", "ATENCAO")
    ):
        nivel = "MEDIA"
        rotulo = "Confiabilidade Moderada · Dados regionais verificados"
    else:
        nivel = "INICIAL"
        rotulo = "Dados Colaborativos Iniciais"

    return IndicadorConfiabilidadeSchema(
        nivel=nivel,
        rotulo=rotulo,
        criterios_atendidos=criterios,
        quantidade_usuarios_distintos=quantidade_usuarios_distintos,
        quantidade_registros_validos=quantidade_registros_validos,
        status_atualidade=status_atualidade_melhor,
        dados_limitados=dados_limitados,
        aviso_dados_limitados=aviso,
    )


def consolidar_precos_por_estabelecimento(
    registros: List[Dict],
    distancias_cidades: Optional[Dict[str, float]] = None,
    incluir_desatualizados: bool = False,
    referencia_utc: Optional[datetime.datetime] = None,
) -> Tuple[List[PrecoEstabelecimentoSchema], int, int, Optional[str]]:
    """
    Consolida múltiplos registros colaborativos do mesmo produto por estabelecimento:
    - Filtra apenas registros com `status_validacao == 'APROVADO'`.
    - Não mistura preços antigos (> 30 dias) como se fossem atuais.
    - Para cada estabelecimento, seleciona o preço válido MAIS RECENTE (priorizando condição NORMAL)
      e calcula mediana, mínimo e máximo de apoio (nunca usando apenas média simples).
    - Ordena os estabelecimentos pelo MENOR PREÇO (e em caso de empate, pelo mais recente).
    Retorna:
      (lista_estabelecimentos_ordenada, total_usuarios_distintos, total_registros_validos, ultima_atualizacao_iso)
    """
    agora = referencia_utc or datetime.datetime.now(datetime.timezone.utc)
    distancias_map = distancias_cidades or {}

    agrupado_estab: Dict[str, List[Dict]] = {}
    usuarios_globais = set()
    total_validos = 0
    ultima_atualizacao_dt: Optional[datetime.datetime] = None

    for reg in registros:
        if reg.get("status_validacao", "APROVADO") != "APROVADO":
            continue

        preco = float(reg.get("preco", 0.0))
        if preco <= 0:
            continue

        dt_compra = _converter_para_datetime_utc(reg.get("data_compra"))
        dt_atualizado = _converter_para_datetime_utc(reg.get("atualizado_em") or reg.get("criado_em") or dt_compra)
        dias, rotulo_tempo, status_atual = calcular_atualidade(dt_compra, agora)

        if status_atual == "DESATUALIZADO" and not incluir_desatualizados:
            continue

        est_id = reg.get("estabelecimento_id") or "est_desconhecido"
        item_enriquecido = {
            **reg,
            "_dt_compra": dt_compra,
            "_dt_atualizado": dt_atualizado,
            "_dias": dias,
            "_rotulo_tempo": rotulo_tempo,
            "_status_atual": status_atual,
        }
        agrupado_estab.setdefault(est_id, []).append(item_enriquecido)

        anon_id = reg.get("identificador_anonimo_de_contribuicao")
        if anon_id:
            usuarios_globais.add(anon_id)
        total_validos += 1

        if ultima_atualizacao_dt is None or dt_atualizado > ultima_atualizacao_dt:
            ultima_atualizacao_dt = dt_atualizado

    resultado_estabs: List[PrecoEstabelecimentoSchema] = []

    for est_id, lista_regs in agrupado_estab.items():
        # Ordena registros do estabelecimento do mais recente para o mais antigo
        lista_regs.sort(key=lambda r: (r["_dt_compra"], r["_dt_atualizado"]), reverse=True)

        # Prioriza registros em condição NORMAL recentes; se todos forem PROMOCAO/ATACADO, usa o mais recente
        regs_normais = [r for r in lista_regs if r.get("condicao_preco", "NORMAL") == "NORMAL"]
        reg_referencia = regs_normais[0] if regs_normais else lista_regs[0]

        precos_estab = [float(r["preco"]) for r in lista_regs]
        # Filtro anti-anomalia intra-estabelecimento se houver >= 3 leituras
        if len(precos_estab) >= 3:
            med_local = statistics.median(precos_estab)
            precos_filtrados = [p for p in precos_estab if (med_local * 0.4) <= p <= (med_local * 2.2)]
            if precos_filtrados:
                precos_estab = precos_filtrados

        mediana_est = round(statistics.median(precos_estab), 2)
        min_est = round(min(precos_estab), 2)
        max_est = round(max(precos_estab), 2)

        usuarios_est = {
            r.get("identificador_anonimo_de_contribuicao")
            for r in lista_regs
            if r.get("identificador_anonimo_de_contribuicao")
        }

        cidade_id = reg_referencia.get("cidade_id", "desconhecida")
        dist_km = distancias_map.get(cidade_id)

        resultado_estabs.append(
            PrecoEstabelecimentoSchema(
                estabelecimento_id=est_id,
                nome_estabelecimento=reg_referencia.get("nome_estabelecimento", "Mercado"),
                cidade_id=cidade_id,
                nome_cidade=reg_referencia.get("nome_cidade", reg_referencia.get("cidade_id", "")),
                uf=reg_referencia.get("uf", "BA"),
                distancia_aproximada_km=dist_km,
                preco=round(float(reg_referencia["preco"]), 2),
                preco_por_unidade=(
                    round(float(reg_referencia["preco_por_unidade"]), 2)
                    if reg_referencia.get("preco_por_unidade")
                    else None
                ),
                unidade_padrao=reg_referencia.get("unidade_padrao", "UN"),
                condicao_preco=reg_referencia.get("condicao_preco", "NORMAL"),
                mediana_estabelecimento=mediana_est,
                preco_minimo_estabelecimento=min_est,
                preco_maximo_estabelecimento=max_est,
                data_compra=reg_referencia["_dt_compra"].strftime("%d/%m/%Y"),
                atualizado_em=reg_referencia["_dt_atualizado"].isoformat(),
                dias_desde_compra=reg_referencia["_dias"],
                rotulo_tempo=reg_referencia["_rotulo_tempo"],
                status_atualidade=reg_referencia["_status_atual"],
                quantidade_registros=len(lista_regs),
                quantidade_usuarios_distintos=max(1, len(usuarios_est)),
            )
        )

    # Ordena pelo MENOR PREÇO e, em caso de empate, pela compra mais recente (menor dias_desde_compra)
    resultado_estabs.sort(key=lambda e: (e.preco, e.dias_desde_compra))

    if resultado_estabs:
        menor_valor = resultado_estabs[0].preco
        for idx, item in enumerate(resultado_estabs):
            item.eh_menor_preco = (idx == 0) or (abs(item.preco - menor_valor) < 0.01)
            diff_reais = round(max(0.0, item.preco - menor_valor), 2)
            diff_pct = round(((item.preco - menor_valor) / menor_valor) * 100.0, 1) if menor_valor > 0 else 0.0
            item.diferenca_reais = diff_reais
            item.diferenca_percentual = diff_pct

    ultima_iso = ultima_atualizacao_dt.isoformat() if ultima_atualizacao_dt else None
    return resultado_estabs, len(usuarios_globais), total_validos, ultima_iso


def construir_historico_evolucao(
    registros: List[Dict],
    periodo_dias: int = 90,
    referencia_utc: Optional[datetime.datetime] = None,
) -> Tuple[List[PontoHistoricoPrecoSchema], str, float]:
    """
    Constrói a evolução histórica de preços agrupada por data de compra nos últimos `periodo_dias`.
    Retorna: (pontos_ordenados_cronologicamente, tendencia, variacao_percentual)
    """
    agora = referencia_utc or datetime.datetime.now(datetime.timezone.utc)
    limite_inferior = agora - datetime.timedelta(days=periodo_dias)

    por_data: Dict[str, List[Dict]] = {}
    for reg in registros:
        if reg.get("status_validacao", "APROVADO") != "APROVADO":
            continue
        preco = float(reg.get("preco", 0.0))
        if preco <= 0:
            continue
        dt = _converter_para_datetime_utc(reg.get("data_compra"))
        if dt < limite_inferior:
            continue
        chave_dia = dt.strftime("%Y-%m-%d")
        por_data.setdefault(chave_dia, []).append(reg)

    pontos: List[PontoHistoricoPrecoSchema] = []
    for chave_dia in sorted(por_data.keys()):
        itens_dia = por_data[chave_dia]
        itens_dia.sort(key=lambda x: float(x["preco"]))
        precos_dia = [float(x["preco"]) for x in itens_dia]
        partes_dt = chave_dia.split("-")
        data_br = f"{partes_dt[2]}/{partes_dt[1]}/{partes_dt[0]}"

        pontos.append(
            PontoHistoricoPrecoSchema(
                data_referencia=data_br,
                menor_preco=round(min(precos_dia), 2),
                mediana_preco=round(statistics.median(precos_dia), 2),
                maior_preco=round(max(precos_dia), 2),
                quantidade_registros=len(precos_dia),
                estabelecimento_menor_preco=itens_dia[0].get("nome_estabelecimento", "Mercado"),
            )
        )

    if len(pontos) < 2:
        return pontos, "INSUFICIENTE", 0.0

    primeiro = pontos[0].menor_preco
    ultimo = pontos[-1].menor_preco
    if primeiro <= 0:
        return pontos, "INSUFICIENTE", 0.0

    variacao_pct = round(((ultimo - primeiro) / primeiro) * 100.0, 1)
    if variacao_pct <= -2.0:
        tendencia = "QUEDA"
    elif variacao_pct >= 2.0:
        tendencia = "ALTA"
    else:
        tendencia = "ESTAVEL"

    return pontos, tendencia, variacao_pct

