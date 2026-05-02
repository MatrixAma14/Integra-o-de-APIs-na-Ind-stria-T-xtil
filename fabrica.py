"""
Serviço da Fábrica — porta 8002
Gere as ordens de produção e o catálogo de peças.
"""

import sys
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

# ──────────────────────────────────────────────
# App FastAPI
# ──────────────────────────────────────────────
app = FastAPI(
    title="Serviço da Fábrica",
    description="Gere o catálogo de peças e as ordens de produção da fábrica têxtil.",
    version="1.0.0",
)

# ──────────────────────────────────────────────
# Modelos Pydantic
# ──────────────────────────────────────────────

class Peca(BaseModel):
    """Peça que a fábrica sabe produzir."""
    referencia: str = Field(..., description="Código único da peça")
    descricao: str = Field(..., description="Descrição da peça")
    categoria: str = Field(..., description="Categoria (ex: camisas, calcas, casacos)")


class OrdemProducao(BaseModel):
    """Ordem de produção registada na fábrica."""
    id: int = Field(..., description="Identificador único")
    referencia_peca: str = Field(..., description="Referência da peça a produzir")
    quantidade: int = Field(..., gt=0, description="Número de unidades solicitadas")
    estado: str = Field(default="pendente", description="pendente, em_producao, concluida, cancelada")
    criada_em: datetime = Field(default_factory=datetime.now, description="Momento de criação")
    concluida_em: Optional[datetime] = Field(default=None, description="Momento de conclusão")


class CriarOrdemRequest(BaseModel):
    """Body para criação de uma nova ordem de produção."""
    referencia_peca: str = Field(..., description="Referência da peça a produzir")
    quantidade: int = Field(..., gt=0, description="Número de unidades solicitadas")


class AtualizarEstadoRequest(BaseModel):
    """Body para atualização do estado de uma ordem."""
    estado: str = Field(..., description="Novo estado (em_producao, concluida, cancelada)")

# ──────────────────────────────────────────────
# Dados em memória
# ──────────────────────────────────────────────

# Catálogo de peças que a fábrica produz
catalogo_pecas: list[Peca] = [
    Peca(referencia="CAM-001-AZ-M", descricao="Camisa azul tamanho M", categoria="camisas"),
    Peca(referencia="CAM-002-BR-L", descricao="Camisa branca tamanho L", categoria="camisas"),
    Peca(referencia="CAL-001-PT-M", descricao="Calça preta tamanho M", categoria="calcas"),
    Peca(referencia="CAS-001-CZ-L", descricao="Casaco cinzento tamanho L", categoria="casacos"),
]

# Ordens de produção
ordens: list[OrdemProducao] = []
contador_ordens: int = 0

# Transições de estado válidas
TRANSICOES_VALIDAS: dict[str, list[str]] = {
    "pendente": ["em_producao", "cancelada"],
    "em_producao": ["concluida", "cancelada"],
    "concluida": [],
    "cancelada": [],
}

# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@app.get("/health", tags=["Sistema"])
def health():
    """Verifica o estado do serviço da fábrica."""
    return {"servico": "fabrica", "estado": "online"}


@app.get("/pecas", tags=["Peças"], response_model=list[Peca])
def listar_pecas():
    """Lista o catálogo de peças que a fábrica produz."""
    return catalogo_pecas


@app.post("/ordens", tags=["Ordens"], response_model=OrdemProducao, status_code=201)
def criar_ordem(dados: CriarOrdemRequest):
    """Recebe uma nova ordem de produção."""
    global contador_ordens

    # Verificar se a peça existe no catálogo
    referencias_validas = [p.referencia for p in catalogo_pecas]
    if dados.referencia_peca not in referencias_validas:
        raise HTTPException(
            status_code=404,
            detail=f"Peça '{dados.referencia_peca}' não encontrada no catálogo da fábrica."
        )

    contador_ordens += 1
    ordem = OrdemProducao(
        id=contador_ordens,
        referencia_peca=dados.referencia_peca,
        quantidade=dados.quantidade,
        estado="pendente",
        criada_em=datetime.now(),
        concluida_em=None,
    )
    ordens.append(ordem)
    print(f"[FABRICA] Nova ordem #{ordem.id}: {ordem.quantidade}x {ordem.referencia_peca}")
    return ordem


@app.get("/ordens", tags=["Ordens"], response_model=list[OrdemProducao])
def listar_ordens():
    """Lista todas as ordens de produção."""
    return ordens


@app.get("/ordens/{id}", tags=["Ordens"], response_model=OrdemProducao)
def obter_ordem(id: int):
    """Obtém o detalhe de uma ordem de produção específica."""
    for ordem in ordens:
        if ordem.id == id:
            return ordem
    raise HTTPException(status_code=404, detail=f"Ordem #{id} não encontrada.")


@app.patch("/ordens/{id}/estado", tags=["Ordens"], response_model=OrdemProducao)
def atualizar_estado(id: int, dados: AtualizarEstadoRequest):
    """Atualiza o estado de uma ordem de produção (máquina de estados)."""
    # Encontrar a ordem
    ordem = None
    for o in ordens:
        if o.id == id:
            ordem = o
            break

    if ordem is None:
        raise HTTPException(status_code=404, detail=f"Ordem #{id} não encontrada.")

    # Validar o novo estado
    estados_validos = ["pendente", "em_producao", "concluida", "cancelada"]
    if dados.estado not in estados_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Estado '{dados.estado}' inválido. Estados válidos: {estados_validos}"
        )

    # Verificar transição
    transicoes_permitidas = TRANSICOES_VALIDAS.get(ordem.estado, [])
    if dados.estado not in transicoes_permitidas:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Transição inválida: '{ordem.estado}' → '{dados.estado}'. "
                f"Transições permitidas a partir de '{ordem.estado}': {transicoes_permitidas}"
            )
        )

    # Aplicar transição
    estado_anterior = ordem.estado
    ordem.estado = dados.estado

    # Se concluída, registar data de conclusão
    if dados.estado == "concluida":
        ordem.concluida_em = datetime.now()

    print(f"[FABRICA] Ordem #{ordem.id}: {estado_anterior} -> {ordem.estado}")
    return ordem


@app.get("/stats", tags=["Sistema"])
def estatisticas():
    """Estatísticas do serviço da fábrica."""
    total = len(ordens)
    por_estado = {}
    for ordem in ordens:
        por_estado[ordem.estado] = por_estado.get(ordem.estado, 0) + 1

    return {
        "total_ordens": total,
        "ordens_por_estado": por_estado,
        "ultima_ordem": ordens[-1] if ordens else None,
    }


# ──────────────────────────────────────────────
# Ponto de entrada
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  SERVICO DA FABRICA")
    print("  Porta: 8002")
    print("  Docs: http://localhost:8002/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8002)
