import hashlib
import logging
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class ItemNotaSchema(BaseModel):
    nome: str = Field(..., min_length=1, description="Nome do produto ou serviço")
    codigo: Optional[str] = Field(None, description="Código do produto")
    quantidade: float = Field(..., gt=0, description="Quantidade comprada")
    unidade: str = Field(default="UN", description="Unidade de medida (ex: UN, KG, MT)")
    valor_unitario: float = Field(..., ge=0, description="Preço unitário")
    preco_kg: Optional[float] = Field(None, ge=0, description="Preço por quilo se aplicável")
    valor_total: float = Field(..., ge=0, description="Valor total do item")

    @model_validator(mode="after")
    def validar_consistencia_item(self):
        # Tolerância matemática de arredondamento
        esperado = round(self.quantidade * self.valor_unitario, 2)
        diferenca = abs(esperado - round(self.valor_total, 2))
        # Permite pequena margem de arredondamento de centavos
        if diferenca > 0.05 and self.valor_total > 0 and esperado > 0:
            logger.warning(
                f"Possível divergência no item '{self.nome}': qtd={self.quantidade} * unit={self.valor_unitario} "
                f"= {esperado}, informado={self.valor_total} (dif={diferenca})"
            )
        return self


class NotaFiscalSchema(BaseModel):
    tipo: Literal["NFC-e", "BP-e"] = Field(..., description="Tipo do documento fiscal")
    estabelecimento: Optional[str] = Field(None, description="Razão social ou nome do emissor")
    total: float = Field(..., ge=0, description="Valor total da nota")
    chave: Optional[str] = Field(None, min_length=40, max_length=60, description="Chave de acesso fiscal")
    numero: Optional[str] = Field(None, description="Número da nota")
    serie: Optional[str] = Field(None, description="Série da nota")
    emissao: Optional[str] = Field(None, description="Data/hora de emissão")
    produtos: List[ItemNotaSchema] = Field(default_factory=list, description="Lista de itens")

    # Campos específicos de BP-e
    origem: Optional[str] = None
    destino: Optional[str] = None
    data_hora: Optional[str] = None
    poltrona: Optional[str] = None
    prefixo: Optional[str] = None
    linha: Optional[str] = None
    tipo_viagem: Optional[str] = None
    tarifa: Optional[float] = None
    seguro: Optional[float] = None
    desconto: Optional[float] = None
    valor_pagar: Optional[float] = None
    forma_pagamento: Optional[str] = None
    valor_pago: Optional[float] = None
    troco: Optional[float] = None
    protocolo: Optional[str] = None

    @model_validator(mode="after")
    def validar_totais_e_itens(self):
        if self.tipo == "NFC-e" and self.produtos:
            soma_itens = round(sum(p.valor_total for p in self.produtos), 2)
            diferenca = abs(soma_itens - round(self.total, 2))
            # Permite até R$ 0.10 de diferença para possíveis descontos de centavos ou rateio de frete/acréscimo
            if diferenca > 0.10:
                logger.warning(
                    f"Divergência entre soma dos itens ({soma_itens}) e total declarado da nota ({self.total})"
                )
        return self


def gerar_id_deterministico_nota(dados_nota: dict, url_origem: Optional[str] = None) -> str:
    """
    Gera um identificador determinístico para a nota fiscal:
    1. Se houver chave de acesso fiscal (44 dígitos), usa a própria chave limpa.
    2. Se houver número + série + estabelecimento + total, gera hash SHA256 destes dados.
    3. Se houver url_origem (ex: link do QR Code da SEFAZ), gera hash SHA256 da URL normalizada.
    4. Fallback: hash do conteúdo completo.
    """
    chave = dados_nota.get("chave")
    if chave:
        chave_limpa = "".join(filter(str.isalnum, str(chave)))
        if len(chave_limpa) >= 40:
            return f"chave_{chave_limpa}"

    numero = dados_nota.get("numero")
    serie = dados_nota.get("serie")
    estabelecimento = dados_nota.get("estabelecimento") or ""
    total = dados_nota.get("total")

    if numero and total is not None:
        raw = f"{numero}_{serie}_{estabelecimento}_{total}".strip()
        hash_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return f"doc_{hash_id}"

    if url_origem:
        url_limpa = url_origem.strip().lower()
        hash_id = hashlib.sha256(url_limpa.encode("utf-8")).hexdigest()[:32]
        return f"url_{hash_id}"

    # Fallback determinístico pelo conteúdo da nota
    raw_fallback = str(sorted(dados_nota.items()))
    hash_id = hashlib.sha256(raw_fallback.encode("utf-8")).hexdigest()[:32]
    return f"raw_{hash_id}"

