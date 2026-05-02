"""
main.py — Script principal que lanca os 3 servicos e demonstra o fluxo JIT completo.

Uso: python main.py
"""
import subprocess
import sys
import time
import httpx
import os

# Forcar UTF-8 no stdout para suportar caracteres especiais
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Configuracao ──
SERVICOS = [
    {"nome": "Fabrica",  "ficheiro": "fabrica.py", "porta": 8002, "emoji": "[FAB]"},
    {"nome": "Armazem",  "ficheiro": "armazem.py", "porta": 8001, "emoji": "[ARM]"},
    {"nome": "Loja",     "ficheiro": "loja.py",    "porta": 8000, "emoji": "[LOJ]"},
]

processos: list[subprocess.Popen] = []


def iniciar_servicos():
    """Inicia cada servico como subprocesso."""
    print("\n" + "=" * 60)
    print("  SISTEMA DISTRIBUIDO JIT -- INDUSTRIA TEXTIL")
    print("=" * 60)
    print("\n>>> A iniciar servicos...\n")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    for svc in SERVICOS:
        print(f"  {svc['emoji']}  A iniciar {svc['nome']} na porta {svc['porta']}...")
        proc = subprocess.Popen(
            [sys.executable, svc["ficheiro"]],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        processos.append(proc)

    print()


def aguardar_servicos(timeout=15):
    """Aguarda que todos os servicos fiquem operacionais."""
    print(">>> A aguardar que os servicos fiquem online...\n")
    inicio = time.time()

    for svc in SERVICOS:
        url = f"http://localhost:{svc['porta']}/health"
        while True:
            if time.time() - inicio > timeout:
                print(f"  [ERRO] Timeout ao esperar por {svc['nome']}!")
                parar_servicos()
                sys.exit(1)
            try:
                resp = httpx.get(url, timeout=2.0)
                if resp.status_code == 200:
                    print(f"  [OK] {svc['emoji']}  {svc['nome']} online -- http://localhost:{svc['porta']}/docs")
                    break
            except Exception:
                time.sleep(0.5)

    print("\n>>> Todos os servicos estao operacionais!\n")


def demonstrar_jit():
    """Executa o cenario de demonstracao JIT completo."""
    print("=" * 60)
    print("  DEMONSTRACAO DO FLUXO JIT")
    print("=" * 60)

    base_armazem = "http://localhost:8001"
    base_loja = "http://localhost:8000"
    base_fabrica = "http://localhost:8002"

    with httpx.Client(timeout=10.0) as client:
        # 1. Estado do sistema
        print("\n-- 1. Estado do sistema --")
        resp = client.get(f"{base_loja}/sistema/estado")
        estado = resp.json()
        for svc, info in estado.items():
            status = info.get("estado", "?")
            print(f"  {svc}: {status}")

        # 2. Inventario inicial
        print("\n-- 2. Inventario inicial do armazem --")
        resp = client.get(f"{base_armazem}/inventario")
        for peca in resp.json():
            print(f"  {peca['referencia']}: {peca['quantidade_actual']} un. "
                  f"(min: {peca['stock_minimo']}, repos: {peca['stock_reposicao']})")

        # 3. Catalogo da fabrica
        print("\n-- 3. Catalogo da fabrica --")
        resp = client.get(f"{base_fabrica}/pecas")
        for peca in resp.json():
            print(f"  {peca['referencia']}: {peca['descricao']} [{peca['categoria']}]")

        # 4. Ordens antes da encomenda
        print("\n-- 4. Ordens de producao (antes) --")
        resp = client.get(f"{base_fabrica}/ordens")
        ordens_antes = resp.json()
        print(f"  Total: {len(ordens_antes)} ordens")

        # 5. Criar encomenda JIT
        print("\n-- 5. [ENCOMENDA] Criar encomenda: 3x Camisa azul M --")
        resp = client.post(f"{base_loja}/encomendas", json={
            "cliente": "Maria Silva",
            "referencia_peca": "CAM-001-AZ-M",
            "quantidade": 3,
        })
        resultado = resp.json()
        enc = resultado.get("encomenda", {})
        print(f"  Estado: {enc.get('estado', '?')}")
        print(f"  Mensagem: {resultado.get('mensagem', '')}")

        # Aguardar processamento JIT
        time.sleep(0.5)

        # 6. Inventario apos encomenda
        print("\n-- 6. Inventario apos encomenda --")
        resp = client.get(f"{base_armazem}/inventario/CAM-001-AZ-M")
        peca = resp.json()
        print(f"  CAM-001-AZ-M: {peca['quantidade_actual']} un. (era 5, sairam 3)")

        # 7. Ordens apos JIT
        print("\n-- 7. Ordens de producao (apos JIT) --")
        resp = client.get(f"{base_fabrica}/ordens")
        ordens_depois = resp.json()
        print(f"  Total: {len(ordens_depois)} ordens")
        for ordem in ordens_depois:
            print(f"  Ordem #{ordem['id']}: {ordem['quantidade']}x {ordem['referencia_peca']} -- {ordem['estado']}")

        # 8. Alertas JIT
        print("\n-- 8. Alertas JIT --")
        resp = client.get(f"{base_armazem}/alertas")
        alertas = resp.json()
        print(f"  Alertas actuais: {len(alertas.get('alertas_actuais', []))}")
        for a in alertas.get("alertas_actuais", []):
            print(f"    {a['referencia']}: stock={a['quantidade_actual']} (min={a['stock_minimo']})")

        # 9. Movimentos de stock
        print("\n-- 9. Historico de movimentos --")
        resp = client.get(f"{base_armazem}/movimentos")
        for m in resp.json():
            print(f"  [{m['tipo'].upper()}] {m['quantidade']}x {m['referencia']} -- {m['motivo']}")

        # 10. Estatisticas
        print("\n-- 10. Estatisticas --")
        for nome, url in [("Loja", base_loja), ("Armazem", base_armazem), ("Fabrica", base_fabrica)]:
            resp = client.get(f"{url}/stats")
            print(f"  {nome}: {resp.json()}")

    print("\n" + "=" * 60)
    print("  DEMONSTRACAO CONCLUIDA COM SUCESSO!")
    print("=" * 60)
    print("\n  Documentacao interactiva:")
    print("   Loja:    http://localhost:8000/docs")
    print("   Armazem: http://localhost:8001/docs")
    print("   Fabrica: http://localhost:8002/docs")
    print("\n  Prima Ctrl+C para parar todos os servicos.\n")


def parar_servicos():
    """Para todos os subprocessos."""
    print("\n>>> A parar servicos...")
    for proc in processos:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    print("   Todos os servicos foram parados.\n")


def main():
    try:
        iniciar_servicos()
        aguardar_servicos()
        demonstrar_jit()

        # Manter activo ate Ctrl+C
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        parar_servicos()


if __name__ == "__main__":
    main()
