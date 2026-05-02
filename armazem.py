"""
Serviço do Armazém — porta 8001
Gere o inventário de peças e implementa a lógica JIT.
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
import httpx

app = FastAPI(
    title="Serviço do Armazém",
    description="Gere o inventário e implementa a lógica JIT.",
    version="1.0.0",
)
FABRICA_URL = "http://localhost:8002"

# ── Modelos ──
class PecaInventario(BaseModel):
    referencia: str
    descricao: str
    categoria: str
    quantidade_actual: int = Field(..., ge=0)
    stock_minimo: int = Field(..., ge=0)
    stock_reposicao: int = Field(..., gt=0)

class CriarPecaRequest(BaseModel):
    referencia: str
    descricao: str
    categoria: str
    quantidade_actual: int = Field(default=0, ge=0)
    stock_minimo: int = Field(..., ge=0)
    stock_reposicao: int = Field(..., gt=0)

class AtualizarQuantidadeRequest(BaseModel):
    quantidade_actual: int = Field(..., ge=0)

class EntradaStockRequest(BaseModel):
    quantidade: int = Field(..., gt=0)
    motivo: str = "Reposição da fábrica"

class SaidaStockRequest(BaseModel):
    quantidade: int = Field(..., gt=0)
    motivo: str = "Venda à loja"

class MovimentoStock(BaseModel):
    referencia: str
    tipo: str
    quantidade: int
    data: datetime = Field(default_factory=datetime.now)
    motivo: str

# ── Dados em memória ──
inventario: dict[str, PecaInventario] = {}
movimentos: list[MovimentoStock] = []
alertas_jit: list[dict] = []
ordens_jit_enviadas: int = 0

def popular_inventario_inicial():
    pecas = [
        PecaInventario(referencia="CAM-001-AZ-M", descricao="Camisa azul tamanho M",
                       categoria="camisas", quantidade_actual=5, stock_minimo=3, stock_reposicao=10),
        PecaInventario(referencia="CAM-002-BR-L", descricao="Camisa branca tamanho L",
                       categoria="camisas", quantidade_actual=8, stock_minimo=3, stock_reposicao=10),
        PecaInventario(referencia="CAL-001-PT-M", descricao="Calça preta tamanho M",
                       categoria="calcas", quantidade_actual=4, stock_minimo=2, stock_reposicao=8),
        PecaInventario(referencia="CAS-001-CZ-L", descricao="Casaco cinzento tamanho L",
                       categoria="casacos", quantidade_actual=6, stock_minimo=3, stock_reposicao=12),
    ]
    for p in pecas:
        inventario[p.referencia] = p

popular_inventario_inicial()

# ── Lógica JIT ──
async def verificar_jit(peca: PecaInventario):
    global ordens_jit_enviadas
    if peca.quantidade_actual < peca.stock_minimo:
        print(f"[ARMAZEM] ALERTA JIT: {peca.referencia} stock={peca.quantidade_actual} (min={peca.stock_minimo})")
        alertas_jit.append({
            "referencia": peca.referencia, "descricao": peca.descricao,
            "quantidade_actual": peca.quantidade_actual, "stock_minimo": peca.stock_minimo,
            "stock_reposicao": peca.stock_reposicao, "data": datetime.now().isoformat(),
        })
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(f"{FABRICA_URL}/ordens", json={
                    "referencia_peca": peca.referencia, "quantidade": peca.stock_reposicao,
                })
                if resp.status_code == 201:
                    ordem = resp.json()
                    ordens_jit_enviadas += 1
                    print(f"[ARMAZEM] Ordem #{ordem['id']} enviada: {peca.stock_reposicao}x {peca.referencia}")
                else:
                    print(f"[ARMAZEM] Erro fabrica: {resp.status_code}")
        except httpx.ConnectError:
            print(f"[ARMAZEM] Fabrica offline -- ordem para {peca.referencia} nao enviada.")
        except httpx.TimeoutException:
            print(f"[ARMAZEM] Timeout fabrica -- ordem para {peca.referencia} nao enviada.")
        except Exception as e:
            print(f"[ARMAZEM] Erro: {e}")

# ── Endpoints ──
@app.get("/health", tags=["Sistema"])
def health():
    return {"servico": "armazem", "estado": "online"}

@app.get("/inventario", tags=["Inventário"], response_model=list[PecaInventario])
def listar_inventario():
    return list(inventario.values())

@app.get("/inventario/{referencia}", tags=["Inventário"], response_model=PecaInventario)
def obter_peca(referencia: str):
    if referencia not in inventario:
        raise HTTPException(status_code=404, detail=f"Peça '{referencia}' não encontrada.")
    return inventario[referencia]

@app.post("/inventario", tags=["Inventário"], response_model=PecaInventario, status_code=201)
def adicionar_peca(dados: CriarPecaRequest):
    if dados.referencia in inventario:
        raise HTTPException(status_code=409, detail=f"Peça '{dados.referencia}' já existe.")
    peca = PecaInventario(**dados.model_dump())
    inventario[dados.referencia] = peca
    print(f"[ARMAZEM] Nova peca: {peca.referencia}")
    return peca

@app.patch("/inventario/{referencia}", tags=["Inventário"], response_model=PecaInventario)
def atualizar_quantidade(referencia: str, dados: AtualizarQuantidadeRequest):
    if referencia not in inventario:
        raise HTTPException(status_code=404, detail=f"Peça '{referencia}' não encontrada.")
    inventario[referencia].quantidade_actual = dados.quantidade_actual
    return inventario[referencia]

@app.post("/inventario/{referencia}/entrada", tags=["Movimentos"], response_model=PecaInventario)
async def entrada_stock(referencia: str, dados: EntradaStockRequest):
    if referencia not in inventario:
        raise HTTPException(status_code=404, detail=f"Peça '{referencia}' não encontrada.")
    peca = inventario[referencia]
    peca.quantidade_actual += dados.quantidade
    movimentos.append(MovimentoStock(
        referencia=referencia, tipo="entrada", quantidade=dados.quantidade,
        data=datetime.now(), motivo=dados.motivo,
    ))
    print(f"[ARMAZEM] Entrada: +{dados.quantidade} {referencia} (stock={peca.quantidade_actual})")
    return peca

@app.post("/inventario/{referencia}/saida", tags=["Movimentos"], response_model=PecaInventario)
async def saida_stock(referencia: str, dados: SaidaStockRequest):
    if referencia not in inventario:
        raise HTTPException(status_code=404, detail=f"Peça '{referencia}' não encontrada.")
    peca = inventario[referencia]
    if dados.quantidade > peca.quantidade_actual:
        raise HTTPException(status_code=400,
            detail=f"Stock insuficiente para '{referencia}'. Disponível: {peca.quantidade_actual}, solicitado: {dados.quantidade}.")
    peca.quantidade_actual -= dados.quantidade
    movimentos.append(MovimentoStock(
        referencia=referencia, tipo="saida", quantidade=dados.quantidade,
        data=datetime.now(), motivo=dados.motivo,
    ))
    print(f"[ARMAZEM] Saida: -{dados.quantidade} {referencia} (stock={peca.quantidade_actual})")
    await verificar_jit(peca)
    return peca

@app.get("/alertas", tags=["JIT"])
def listar_alertas():
    actuais = []
    for p in inventario.values():
        if p.quantidade_actual < p.stock_minimo:
            actuais.append({"referencia": p.referencia, "descricao": p.descricao,
                "quantidade_actual": p.quantidade_actual, "stock_minimo": p.stock_minimo,
                "deficit": p.stock_minimo - p.quantidade_actual})
    return {"alertas_actuais": actuais, "historico_alertas": alertas_jit, "total_alertas_gerados": len(alertas_jit)}

@app.get("/movimentos", tags=["Movimentos"], response_model=list[MovimentoStock])
def listar_movimentos():
    return movimentos

@app.get("/stats", tags=["Sistema"])
def estatisticas():
    return {
        "total_pecas_inventario": len(inventario),
        "total_movimentos": len(movimentos),
        "total_entradas": sum(1 for m in movimentos if m.tipo == "entrada"),
        "total_saidas": sum(1 for m in movimentos if m.tipo == "saida"),
        "total_alertas_jit": len(alertas_jit),
        "total_ordens_jit_enviadas": ordens_jit_enviadas,
        "pecas_abaixo_minimo": sum(1 for p in inventario.values() if p.quantidade_actual < p.stock_minimo),
    }

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  SERVICO DO ARMAZEM -- Porta 8001")
    print("  Docs: http://localhost:8001/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8001)
