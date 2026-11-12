from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


NivelCorrespondencia = Literal["EXATA", "EQUIVALENTE", "APROXIMADA", "SEM_CORRESPONDENCIA"]
NivelConfiabilidade = Literal["ALTA", "MEDIA", "INICIAL"]
StatusAtualidade = Literal["RECENTE", "ATENCAO", "DESATUALIZADO"]
AbrangenciaRegional = Literal["apenas_cidade", "cidade_e_proximos", "regiao_ampliada"]
CondicaoPreco = Literal["NORMAL", "PROMOCAO", "ATACADO"]


class PreferenciasCompartilhamentoRequest(BaseModel):
    compartilhamento_ativo: bool = Field(
        default=True,
        description="Define se o usuário autoriza contribuir anonimamente com dados comerciais de suas notas.",
    )
    municipio: Optional[str] = Field(
        None,
        max_length=120,
        description="Município de referência do usuário para comparações regionais.",
    )
    uf: Optional[str] = Field(
        None,
        min_length=2,
        max_length=2,
        description="Sigla da UF (ex: BA, SP, PR, RJ).",
    )
    codigo_ibge: Optional[str] = Field(
        None,
        max_length=10,
        description="Código IBGE de 7 dígitos do município, quando conhecido.",
    )
    abrangencia: AbrangenciaRegional = Field(
        default="cidade_e_proximos",
        description="Abrangência geográfica das comparações.",
    )
    raio_km: int = Field(
        default=30,
        ge=5,
        le=150,
        description="Distância máxima em km para municípios próximos (padrão: 30 km).",
    )

    @field_validator("uf")
    @classmethod
    def normalizar_uf(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip().upper()


class PreferenciasCompartilhamentoResponse(BaseModel):
    sucesso: bool
    compartilhamento_ativo: bool
    cidade_id: str
    municipio: str
    uf: str
    codigo_ibge: Optional[str] = None
    regiao_id: str
    abrangencia: AbrangenciaRegional
    raio_km: int
    atualizado_em: str


class IndicadorConfiabilidadeSchema(BaseModel):
    nivel: NivelConfiabilidade
    rotulo: str
    criterios_atendidos: List[str]
    quantidade_usuarios_distintos: int
    quantidade_registros_validos: int
    status_atualidade: StatusAtualidade
    dados_limitados: bool
    aviso_dados_limitados: Optional[str] = None


class PrecoEstabelecimentoSchema(BaseModel):
    estabelecimento_id: str
    nome_estabelecimento: str
    cidade_id: str
    nome_cidade: str
    uf: str
    distancia_aproximada_km: Optional[float] = None
    preco: float
    preco_por_unidade: Optional[float] = None
    unidade_padrao: str = "UN"
    condicao_preco: CondicaoPreco = "NORMAL"
    mediana_estabelecimento: Optional[float] = None
    preco_minimo_estabelecimento: Optional[float] = None
    preco_maximo_estabelecimento: Optional[float] = None
    data_compra: str
    atualizado_em: str
    dias_desde_compra: int
    rotulo_tempo: str
    status_atualidade: StatusAtualidade
    quantidade_registros: int
    quantidade_usuarios_distintos: int
    eh_menor_preco: bool = False
    diferenca_reais: float = 0.0
    diferenca_percentual: float = 0.0


class ComparacaoProdutoResponse(BaseModel):
    produto_id: str
    nome_produto: str
    nome_normalizado: str
    marca: Optional[str] = None
    categoria: str
    quantidade_embalagem: float
    unidade_medida: str
    unidade_padrao: str
    gtin: Optional[str] = None
    nivel_correspondencia: NivelCorrespondencia
    regiao_consultada: str
    abrangencia: AbrangenciaRegional
    menor_preco: Optional[float] = None
    maior_preco: Optional[float] = None
    mediana_regional: Optional[float] = None
    estabelecimento_mais_barato: Optional[str] = None
    economia_maxima_reais: float = 0.0
    economia_maxima_percentual: float = 0.0
    total_usuarios_contribuintes: int = 0
    total_registros_validos: int = 0
    ultima_atualizacao_sistema: Optional[str] = None
    confiabilidade: IndicadorConfiabilidadeSchema
    estabelecimentos: List[PrecoEstabelecimentoSchema] = Field(default_factory=list)
    similares_equivalentes: List["ResumoProdutoPesquisaSchema"] = Field(default_factory=list)


class ResumoProdutoPesquisaSchema(BaseModel):
    produto_id: str
    nome_produto: str
    subtitulo: str
    marca: Optional[str] = None
    categoria: str
    quantidade_embalagem: float
    unidade_medida: str
    gtin: Optional[str] = None
    nivel_correspondencia: NivelCorrespondencia
    menor_preco: float
    maior_preco: float
    preco_por_unidade: Optional[float] = None
    unidade_padrao: str
    estabelecimento_mais_barato: str
    nome_cidade: str
    uf: str
    economia_potencial_reais: float
    economia_potencial_percentual: float
    total_estabelecimentos: int
    total_usuarios_distintos: int
    total_registros_validos: int
    data_ultima_compra: str
    rotulo_tempo: str
    status_atualidade: StatusAtualidade
    confiabilidade: IndicadorConfiabilidadeSchema
    estabelecimentos_preview: List[PrecoEstabelecimentoSchema] = Field(default_factory=list)


class PesquisaColaborativaResponse(BaseModel):
    termo_pesquisado: str
    cidade_referencia: str
    uf_referencia: str
    abrangencia: AbrangenciaRegional
    raio_km: int
    total_encontrados: int
    ultima_atualizacao_consulta: str
    produtos: List[ResumoProdutoPesquisaSchema] = Field(default_factory=list)


class PontoHistoricoPrecoSchema(BaseModel):
    data_referencia: str
    menor_preco: float
    mediana_preco: float
    maior_preco: float
    quantidade_registros: int
    estabelecimento_menor_preco: str


class HistoricoProdutoResponse(BaseModel):
    produto_id: str
    nome_produto: str
    regiao_consultada: str
    periodo_dias: int
    tendencia: Literal["QUEDA", "ESTAVEL", "ALTA", "INSUFICIENTE"]
    variacao_periodo_percentual: float
    pontos: List[PontoHistoricoPrecoSchema] = Field(default_factory=list)


class ProcessamentoNotaResponse(BaseModel):
    sucesso: bool
    job_id: str
    nota_id: str
    status: Literal["CONCLUIDO", "EM_PROCESSAMENTO", "IGNORADO_OPT_OUT", "IDEMPOTENTE"]
    itens_processados: int
    itens_aprovados: int
    itens_rejeitados_ou_quarentena: int
    cidade_identificada: Optional[str] = None
    uf_identificada: Optional[str] = None
    estabelecimento_id: Optional[str] = None
    mensagem: str

