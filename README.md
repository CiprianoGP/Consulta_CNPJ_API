# Consulta de CNPJ com API, MySQL e API própria (FastAPI)

Projeto de integração de sistemas em Python: lê uma lista de CNPJs, valida, consulta a **BrasilAPI**, grava os dados em **MySQL**, gera um **relatório** e expõe tudo por uma **API própria** com documentação Swagger. Cenário próximo da rotina de contabilidade e BPO (cadastro e conferência de clientes e fornecedores).

## Arquitetura em camadas

```
Cliente / Swagger
      |
   api.py      -> camada web: rotas, códigos HTTP, validação de entrada
      |
   main.py     -> regras de negócio e integração: validar CNPJ, consultar a BrasilAPI,
      |           tratar erros e tentar de novo
   db.py       -> camada de dados: todo o SQL fica aqui
      |
    MySQL
```

Por que separar: se o banco mudar, só o `db.py` muda. As regras e as rotas continuam iguais, e cada parte pode ser testada sozinha.

## O que o projeto demonstra

- Consumo de API REST (`requests`, JSON, status codes, timeout, nova tentativa com espera crescente)
- API própria com FastAPI (filtros, paginação, códigos de retorno corretos)
- SQL com MySQL: tabela com chave primária e índices, upsert com `ON DUPLICATE KEY UPDATE`, `GROUP BY`
- Transações: tudo dentro de uma conexão é confirmado (`COMMIT`) ou desfeito (`ROLLBACK`) se der erro
- Segurança básica: configuração por variáveis de ambiente, usuário do banco com poucas permissões, SQL parametrizado (sem concatenar texto)

## Como executar

### 1. Instale o MySQL
- **MySQL Community Server** com o MySQL Installer (Windows) e, se quiser, o MySQL Workbench; ou
- **XAMPP**, que traz o MariaDB (compatível com este projeto).

Anote a senha do usuário `root` definida na instalação.

### 2. Crie o banco
Abra o `schema.sql`, **troque `TroqueEstaSenha` por uma senha sua** e rode no Workbench (ou no terminal: `mysql -u root -p < schema.sql`). Ele cria o banco `empresas_db`, o usuário `cnpj_app` e a tabela.

### 3. Configure o `.env`
Copie `.env.example` para `.env` e coloque a mesma senha que você usou no passo 2. O `.env` não vai para o GitHub.

### 4. Instale as dependências e rode
```bash
python -m pip install -r requirements.txt
python main.py
```
O script lê o `cnpjs.csv`, consulta a BrasilAPI, grava no MySQL e gera `relatorio_empresas.csv` e `execucao.log`. Troque os CNPJs do arquivo por CNPJs reais para ver o resultado de verdade. Para usar outro arquivo: `python main.py --entrada meus_cnpjs.csv` (precisa ter a coluna `cnpj`).

### 5. Suba a API
```bash
python -m uvicorn api:app --reload
```
Abra http://127.0.0.1:8000/docs para testar pelo Swagger.

| Método | Rota | Função |
|---|---|---|
| GET | `/saude` | Health check |
| GET | `/empresas?uf=DF&situacao=ATIVA&limite=50&offset=0` | Lista com filtros e paginação |
| GET | `/empresas/resumo` | Totais por situação e por UF |
| GET | `/empresas/{cnpj}` | Busca no banco; se não achar, consulta a BrasilAPI e grava (cache) |
| DELETE | `/empresas/{cnpj}` | Remove do banco local |

Envie o CNPJ só com dígitos (ex.: `/empresas/00000000000191`). Códigos de retorno: 200 ok, 204 removido, 404 não encontrado, 422 CNPJ inválido, 502 falha na API externa.

## Problemas comuns

| Mensagem | Causa provável | Solução |
|---|---|---|
| `Access denied for user` | Senha ou usuário do `.env` diferentes dos do `schema.sql` | Conferir o `.env` e a senha usada no `schema.sql` |
| `Can't connect to MySQL server` | Serviço do MySQL parado | Iniciar o serviço (ou o MySQL no XAMPP) |
| `Unknown database 'empresas_db'` | O `schema.sql` não foi executado | Rodar o passo 2 |
| `uvicorn` não é reconhecido | A pasta de scripts do Python não está no PATH | Usar `python -m uvicorn api:app --reload` |
| Erro citando `cryptography` | Falta o pacote (o MySQL 8 exige para a senha) | `python -m pip install cryptography` |

## Sobre os testes desta versão

Foi testada com MariaDB 10.11 (compatível com MySQL) e com a BrasilAPI simulada: carga em lote, upsert sem duplicar, rollback, e todos os endpoints. Ainda não foi testada com um MySQL 8 de verdade nem com a BrasilAPI real, então confira isso no seu computador.

## Evoluções possíveis

- Testes automatizados com `pytest` e `unittest.mock` (simulando a API externa)
- Autenticação na API (API key)
- Agendar a execução diária (Agendador de Tarefas do Windows)
- Classificação de chamados com IA gravando no mesmo banco

## Roteiro para explicar na entrevista

- **Problema:** conferir cadastro de empresas manualmente é lento e sujeito a erro.
- **Solução:** automação que integra uma API pública a um banco MySQL, gera relatório e expõe uma API própria.
- **Decisões:** validar o CNPJ antes de chamar a API, nova tentativa para falhas temporárias, upsert para não duplicar, transação para não deixar dado pela metade, camada de dados separada, senha fora do código.
- **Próximo passo:** testes automatizados e autenticação na API.
