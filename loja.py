"""
Serviço da Loja — porta 8000
Ponto de contacto com o cliente final. Consulta o armazém e efectua encomendas.
"""
import sys
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
import httpx

app = FastAPI(
    title="Serviço da Loja",
    description="Ponto de venda que consulta stock no armazém e efectua encomendas de clientes.",
    version="1.0.0",
)
ARMAZEM_URL = "http://localhost:8001"
FABRICA_URL = "http://localhost:8002"

# ── Modelos ──
class Encomenda(BaseModel):
    id: int
    cliente: str
    referencia_peca: str
    quantidade: int = Field(..., gt=0)
    estado: str = "pendente"
    criada_em: datetime = Field(default_factory=datetime.now)

class CriarEncomendaRequest(BaseModel):
    cliente: str = Field(..., description="Nome do cliente")
    referencia_peca: str = Field(..., description="Referência do produto")
    quantidade: int = Field(..., gt=0, description="Número de unidades")

# ── Dados em memória ──
encomendas: list[Encomenda] = []
contador_encomendas: int = 0

# ── Endpoints ──
@app.get("/health", tags=["Sistema"])
def health():
    return {"servico": "loja", "estado": "online"}

@app.get("/catalogo", tags=["Catálogo"])
async def listar_catalogo():
    """Lista os produtos disponíveis para venda (consulta o armazém em tempo real)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ARMAZEM_URL}/inventario")
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503,
            detail="Serviço do armazém temporariamente indisponível. Tente novamente mais tarde.")
    except httpx.TimeoutException:
        raise HTTPException(status_code=503,
            detail="Timeout ao contactar o armazém. Tente novamente mais tarde.")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro ao contactar o armazém: {str(e)}")

@app.get("/catalogo/{referencia}", tags=["Catálogo"])
async def obter_produto(referencia: str):
    """Consulta a disponibilidade de um produto específico."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ARMAZEM_URL}/inventario/{referencia}")
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Produto '{referencia}' não encontrado.")
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=503,
            detail="Serviço do armazém temporariamente indisponível.")
    except httpx.TimeoutException:
        raise HTTPException(status_code=503,
            detail="Timeout ao contactar o armazém.")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro ao contactar o armazém: {str(e)}")

@app.post("/encomendas", tags=["Encomendas"], status_code=201)
async def criar_encomenda(dados: CriarEncomendaRequest):
    """
    Cria uma nova encomenda de cliente.
    1. Consulta o armazém para verificar disponibilidade
    2. Se houver stock → confirma e solicita saída
    3. Se não houver stock → regista como sem_stock
    """
    global contador_encomendas

    # 1. Consultar armazém
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ARMAZEM_URL}/inventario/{dados.referencia_peca}")
    except (httpx.ConnectError, httpx.TimeoutException):
        raise HTTPException(status_code=503,
            detail="Serviço do armazém temporariamente indisponível. Não é possível processar encomendas.")
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Erro ao contactar o armazém: {str(e)}")

    if resp.status_code == 404:
        raise HTTPException(status_code=404,
            detail=f"Produto '{dados.referencia_peca}' não encontrado no catálogo.")

    peca = resp.json()
    stock_disponivel = peca.get("quantidade_actual", 0)

    # 2. Verificar stock
    if stock_disponivel >= dados.quantidade:
        # Stock suficiente → solicitar saída ao armazém
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp_saida = await client.post(
                    f"{ARMAZEM_URL}/inventario/{dados.referencia_peca}/saida",
                    json={"quantidade": dados.quantidade, "motivo": f"Encomenda do cliente {dados.cliente}"},
                )
                resp_saida.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=503,
                detail=f"Erro ao registar saída de stock no armazém: {str(e)}")

        contador_encomendas += 1
        encomenda = Encomenda(
            id=contador_encomendas, cliente=dados.cliente,
            referencia_peca=dados.referencia_peca, quantidade=dados.quantidade,
            estado="confirmada", criada_em=datetime.now(),
        )
        encomendas.append(encomenda)
        print(f"[LOJA] Encomenda #{encomenda.id} confirmada: {dados.quantidade}x {dados.referencia_peca} para {dados.cliente}")
        return {
            "mensagem": f"Encomenda confirmada com sucesso!",
            "encomenda": encomenda,
        }
    else:
        # 3. Stock insuficiente
        contador_encomendas += 1
        encomenda = Encomenda(
            id=contador_encomendas, cliente=dados.cliente,
            referencia_peca=dados.referencia_peca, quantidade=dados.quantidade,
            estado="sem_stock", criada_em=datetime.now(),
        )
        encomendas.append(encomenda)
        print(f"[LOJA] Encomenda #{encomenda.id} sem stock: {dados.quantidade}x {dados.referencia_peca}")
        return {
            "mensagem": (f"Lamentamos, não há stock suficiente de '{dados.referencia_peca}'. "
                         f"Disponível: {stock_disponivel}, solicitado: {dados.quantidade}. "
                         f"A encomenda foi registada e será processada quando houver reposição."),
            "encomenda": encomenda,
        }

@app.get("/encomendas", tags=["Encomendas"], response_model=list[Encomenda])
def listar_encomendas():
    """Lista todas as encomendas."""
    return encomendas

@app.get("/encomendas/{id}", tags=["Encomendas"], response_model=Encomenda)
def obter_encomenda(id: int):
    """Detalhe de uma encomenda específica."""
    for e in encomendas:
        if e.id == id:
            return e
    raise HTTPException(status_code=404, detail=f"Encomenda #{id} não encontrada.")

@app.get("/sistema/estado", tags=["Sistema"])
async def estado_sistema():
    """Health check agregado de todos os serviços."""
    resultado = {
        "loja": {"estado": "online"},
        "armazem": {"estado": "desconhecido"},
        "fabrica": {"estado": "desconhecido"},
    }
    # Verificar armazém
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{ARMAZEM_URL}/health")
            if resp.status_code == 200:
                resultado["armazem"] = resp.json()
            else:
                resultado["armazem"] = {"estado": "erro", "codigo": resp.status_code}
    except Exception:
        resultado["armazem"] = {"estado": "offline"}

    # Verificar fábrica
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{FABRICA_URL}/health")
            if resp.status_code == 200:
                resultado["fabrica"] = resp.json()
            else:
                resultado["fabrica"] = {"estado": "erro", "codigo": resp.status_code}
    except Exception:
        resultado["fabrica"] = {"estado": "offline"}

    return resultado

@app.get("/stats", tags=["Sistema"])
def estatisticas():
    """Estatísticas do serviço da loja."""
    por_estado = {}
    for e in encomendas:
        por_estado[e.estado] = por_estado.get(e.estado, 0) + 1
    return {
        "total_encomendas": len(encomendas),
        "encomendas_por_estado": por_estado,
        "ultima_encomenda": encomendas[-1] if encomendas else None,
    }

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  SERVICO DA LOJA -- Porta 8000")
    print("  Docs: http://localhost:8000/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
