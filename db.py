"""
Camada de acesso a dados (MySQL).

Regra do projeto: nenhum SQL fora deste arquivo. As outras camadas (main.py e
api.py) chamam as funções daqui e não sabem qual banco existe por baixo.
Se um dia o banco mudar, só este arquivo muda.

A configuração vem de variáveis de ambiente (arquivo .env), nunca do código.
"""

import os
from contextlib import contextmanager
from decimal import Decimal

import pymysql
from dotenv import load_dotenv
from pymysql.cursors import DictCursor

load_dotenv()

COLUNAS = (
    "cnpj", "razao_social", "nome_fantasia", "situacao", "cnae", "municipio",
    "uf", "capital_social", "data_inicio_atividade", "consultado_em",
)


def _configuracao() -> dict:
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "empresas_db"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }


@contextmanager
def conexao():
    """
    Abre uma conexão dentro de uma transação.
    Saiu sem erro: COMMIT. Deu erro no meio: ROLLBACK (nada fica pela metade).
    """
    conn = pymysql.connect(**_configuracao())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _normalizar(linha: dict | None) -> dict | None:
    """O MySQL devolve DECIMAL como Decimal; convertemos para float."""
    if linha is None:
        return None
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in linha.items()}


def criar_banco(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS empresas (
                cnpj                   CHAR(14)       NOT NULL,
                razao_social           VARCHAR(255)   NOT NULL,
                nome_fantasia          VARCHAR(255),
                situacao               VARCHAR(50),
                cnae                   VARCHAR(255),
                municipio              VARCHAR(100),
                uf                     CHAR(2),
                capital_social         DECIMAL(18, 2),
                data_inicio_atividade  DATE,
                consultado_em          DATETIME,
                PRIMARY KEY (cnpj),
                INDEX idx_empresas_uf (uf),
                INDEX idx_empresas_situacao (situacao)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )


def salvar_empresa(conn, empresa: dict) -> None:
    """
    Insere ou atualiza (upsert): se o CNPJ já existe, atualiza em vez de duplicar.
    Obs.: VALUES(coluna) funciona no MySQL e no MariaDB.
    """
    atualizaveis = [c for c in COLUNAS if c != "cnpj"]
    sql = (
        f"INSERT INTO empresas ({', '.join(COLUNAS)}) "
        f"VALUES ({', '.join('%(' + c + ')s' for c in COLUNAS)}) "
        "ON DUPLICATE KEY UPDATE "
        + ", ".join(f"{c} = VALUES({c})" for c in atualizaveis)
    )
    with conn.cursor() as cur:
        cur.execute(sql, empresa)


def buscar_empresa(conn, cnpj: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM empresas WHERE cnpj = %s", (cnpj,))
        return _normalizar(cur.fetchone())


def listar_empresas(conn, uf: str | None = None, situacao: str | None = None,
                    limite: int = 50, offset: int = 0) -> list[dict]:
    sql = "SELECT * FROM empresas WHERE 1 = 1"
    params: list = []
    if uf:
        sql += " AND UPPER(uf) = %s"
        params.append(uf.upper())
    if situacao:
        sql += " AND UPPER(situacao) = %s"
        params.append(situacao.upper())
    sql += " ORDER BY razao_social LIMIT %s OFFSET %s"
    params += [limite, offset]
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [_normalizar(l) for l in cur.fetchall()]


def remover_empresa(conn, cnpj: str) -> bool:
    """Retorna True se removeu alguém, False se o CNPJ não estava no banco."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM empresas WHERE cnpj = %s", (cnpj,))
        return cur.rowcount > 0


def dados_do_relatorio(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cnpj, razao_social, situacao, municipio, uf, capital_social "
            "FROM empresas ORDER BY razao_social"
        )
        return [_normalizar(l) for l in cur.fetchall()]


def resumo(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM empresas")
        total = cur.fetchone()["total"]
        cur.execute(
            "SELECT COUNT(*) AS ativas FROM empresas WHERE UPPER(situacao) = 'ATIVA'"
        )
        ativas = cur.fetchone()["ativas"]
        cur.execute(
            "SELECT situacao, COUNT(*) AS qtd FROM empresas GROUP BY situacao"
        )
        por_situacao = {l["situacao"]: l["qtd"] for l in cur.fetchall()}
        cur.execute(
            "SELECT uf, COUNT(*) AS qtd FROM empresas GROUP BY uf ORDER BY qtd DESC, uf"
        )
        por_uf = {l["uf"]: l["qtd"] for l in cur.fetchall()}
    return {"total": total, "ativas": ativas, "por_situacao": por_situacao, "por_uf": por_uf}
