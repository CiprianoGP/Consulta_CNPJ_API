"""
API própria (FastAPI) que expõe os dados do MySQL.

Se o CNPJ ainda não estiver no banco, consulta a BrasilAPI, grava e responde
(padrão "cache-aside": o banco funciona como cache da API externa).

Esta camada só cuida de HTTP (rotas, códigos de status, validação de entrada).
Regras de negócio estão em main.py e o SQL está em db.py.

Rodar:
    python -m uvicorn api:app --reload
Documentação interativa:
    http://127.0.0.1:8000/docs
"""

from datetime import date, datetime

import requests
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

import db
import main as regras

app = FastAPI(
    title="API de Empresas (CNPJ)",
    description="Consulta empresas por CNPJ, usando banco MySQL local e BrasilAPI.",
    version="2.0.0",
)


class Empresa(BaseModel):
    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    situacao: str | None = None
    cnae: str | None = None
    municipio: str | None = None
    uf: str | None = None
    capital_social: float | None = None
    data_inicio_atividade: date | None = None
    consultado_em: datetime | None = None


@app.on_event("startup")
def preparar_banco() -> None:
    """Garante que a tabela existe quando a API sobe."""
    with db.conexao() as conn:
        db.criar_banco(conn)


@app.get("/saude")
def saude() -> dict:
    """Health check: usado para saber se a API está no ar."""
    return {"status": "ok"}


@app.get("/empresas", response_model=list[Empresa])
def listar_empresas(
    uf: str | None = Query(None, min_length=2, max_length=2, description="Filtra por UF"),
    situacao: str | None = Query(None, description="Ex.: ATIVA"),
    limite: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Lista empresas do banco, com filtros e paginação."""
    with db.conexao() as conn:
        return db.listar_empresas(conn, uf, situacao, limite, offset)


@app.get("/empresas/resumo")
def resumo() -> dict:
    """Totais por situação e por UF."""
    with db.conexao() as conn:
        return db.resumo(conn)


@app.get("/empresas/{cnpj}", response_model=Empresa)
def obter_empresa(cnpj: str):
    """Busca no banco; se não achar, consulta a BrasilAPI e grava."""
    cnpj = regras.limpar_cnpj(cnpj)
    if not regras.validar_cnpj(cnpj):
        raise HTTPException(status_code=422, detail="CNPJ inválido")

    with db.conexao() as conn:
        empresa = db.buscar_empresa(conn, cnpj)
        if empresa:
            return empresa

        try:
            with requests.Session() as sessao:
                dados = regras.consultar_cnpj(sessao, cnpj)
        except regras.ErroApi as exc:
            raise HTTPException(status_code=502, detail=f"Falha na API externa: {exc}")

        if dados is None:
            raise HTTPException(status_code=404, detail="CNPJ não encontrado")

        empresa = regras.extrair_campos(dados)
        db.salvar_empresa(conn, empresa)
        return empresa


@app.delete("/empresas/{cnpj}", status_code=204)
def remover_empresa(cnpj: str):
    """Remove uma empresa do banco local."""
    cnpj = regras.limpar_cnpj(cnpj)
    with db.conexao() as conn:
        if not db.remover_empresa(conn, cnpj):
            raise HTTPException(status_code=404, detail="Empresa não está no banco")
