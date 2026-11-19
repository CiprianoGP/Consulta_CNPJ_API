"""
Automação de consulta de CNPJ via API (BrasilAPI) com persistência em MySQL
e geração de relatório.

Fluxo: ler CSV -> validar CNPJ -> consultar API -> tratar JSON -> gravar no
banco (upsert) -> gerar relatório CSV + resumo no terminal.

Camadas:
    main.py -> regras de negócio e integração com a API externa
    db.py   -> acesso ao banco (todo o SQL fica lá)
    api.py  -> rotas web (FastAPI)

Uso:
    python main.py                      # usa cnpjs.csv
    python main.py --entrada meus.csv   # outro arquivo de entrada
"""

import argparse
import csv
import logging
import time
from datetime import datetime

import requests

import db

API_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
RELATORIO_PATH = "relatorio_empresas.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("execucao.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("cnpj")


class ErroApi(Exception):
    """Falha ao consultar a API depois de todas as tentativas."""


# ---------------------------------------------------------------- validação
def limpar_cnpj(valor: str) -> str:
    return "".join(c for c in valor if c.isdigit())


def validar_cnpj(cnpj: str) -> bool:
    """Valida tamanho e dígitos verificadores do CNPJ."""
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    def digito(base: str, pesos: list[int]) -> str:
        soma = sum(int(n) * p for n, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    d1 = digito(cnpj[:12], pesos1)
    d2 = digito(cnpj[:12] + d1, pesos2)
    return cnpj[-2:] == d1 + d2


# ---------------------------------------------------------------------- API
def consultar_cnpj(sessao: requests.Session, cnpj: str, tentativas: int = 3) -> dict | None:
    """
    Consulta o CNPJ na API.
    Retorna o JSON, ou None se o CNPJ não existir (404).
    Faz novas tentativas em caso de erro temporário (429 / 5xx / rede).
    """
    url = API_URL.format(cnpj=cnpj)
    for tentativa in range(1, tentativas + 1):
        try:
            resp = sessao.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.RequestException(f"HTTP {resp.status_code}")
            raise ErroApi(f"HTTP {resp.status_code} para {cnpj}")
        except requests.RequestException as exc:
            espera = 2 ** tentativa
            log.warning("Tentativa %d/%d falhou para %s (%s). Aguardando %ds.",
                        tentativa, tentativas, cnpj, exc, espera)
            time.sleep(espera)
    raise ErroApi(f"Sem resposta da API para {cnpj} após {tentativas} tentativas")


def extrair_campos(dados: dict) -> dict:
    """Seleciona e normaliza só o que interessa do JSON da API."""
    return {
        "cnpj": dados.get("cnpj"),
        "razao_social": dados.get("razao_social"),
        "nome_fantasia": dados.get("nome_fantasia") or "",
        "situacao": dados.get("descricao_situacao_cadastral"),
        "cnae": dados.get("cnae_fiscal_descricao"),
        "municipio": dados.get("municipio"),
        "uf": dados.get("uf"),
        "capital_social": float(dados.get("capital_social") or 0),
        "data_inicio_atividade": dados.get("data_inicio_atividade") or None,
        "consultado_em": datetime.now().replace(microsecond=0),
    }


# ---------------------------------------------------------------- relatório
def gerar_relatorio(conn) -> None:
    linhas = db.dados_do_relatorio(conn)

    with open(RELATORIO_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["CNPJ", "Razão social", "Situação", "Município", "UF", "Capital social"])
        for l in linhas:
            w.writerow([l["cnpj"], l["razao_social"], l["situacao"],
                        l["municipio"], l["uf"], l["capital_social"]])

    r = db.resumo(conn)
    print("\n=== RESUMO ===")
    print(f"Empresas no banco: {r['total']}")
    print(f"Empresas ativas:   {r['ativas']}")
    print("Por UF:", ", ".join(f"{uf}: {qtd}" for uf, qtd in r["por_uf"].items()))
    print(f"Relatório salvo em: {RELATORIO_PATH}")


# --------------------------------------------------------------------- main
def ler_cnpjs(caminho: str) -> list[str]:
    """Lê a coluna 'cnpj' do CSV, remove formatação e duplicados."""
    vistos, resultado = set(), []
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        for linha in csv.DictReader(f):
            cnpj = limpar_cnpj(linha.get("cnpj", ""))
            if cnpj and cnpj not in vistos:
                vistos.add(cnpj)
                resultado.append(cnpj)
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description="Consulta CNPJs na BrasilAPI e grava no MySQL.")
    parser.add_argument("--entrada", default="cnpjs.csv", help="CSV com coluna 'cnpj'")
    args = parser.parse_args()

    cnpjs = ler_cnpjs(args.entrada)
    log.info("%d CNPJ(s) lido(s) de %s", len(cnpjs), args.entrada)

    ok = invalidos = nao_encontrados = falhas = 0

    # A conexão fica em uma transação: se algo grave acontecer, volta tudo (ROLLBACK).
    with db.conexao() as conn, requests.Session() as sessao:
        db.criar_banco(conn)
        for cnpj in cnpjs:
            if not validar_cnpj(cnpj):
                log.error("CNPJ inválido (dígito verificador): %s", cnpj)
                invalidos += 1
                continue
            try:
                dados = consultar_cnpj(sessao, cnpj)
            except ErroApi as exc:
                log.error("%s", exc)
                falhas += 1
                continue
            if dados is None:
                log.warning("CNPJ não encontrado na base: %s", cnpj)
                nao_encontrados += 1
                continue
            db.salvar_empresa(conn, extrair_campos(dados))
            log.info("Salvo: %s", dados.get("razao_social"))
            ok += 1
            time.sleep(0.5)  # respeita o limite de requisições da API

        log.info("Concluído: %d ok, %d inválidos, %d não encontrados, %d falhas",
                 ok, invalidos, nao_encontrados, falhas)
        gerar_relatorio(conn)


if __name__ == "__main__":
    main()
