-- Script para criar o banco e o usuário da aplicação.
-- Rode no MySQL Workbench (ou no terminal: mysql -u root -p < schema.sql).


CREATE DATABASE IF NOT EXISTS empresas_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- Usuário só com o necessário (boa prática: não usar o root na aplicação).
CREATE USER IF NOT EXISTS 'cnpj_app'@'localhost' IDENTIFIED BY 'TroqueEstaSenha';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX ON empresas_db.* TO 'cnpj_app'@'localhost';
FLUSH PRIVILEGES;

USE empresas_db;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Consultas úteis para treinar:
-- SELECT uf, COUNT(*) AS qtd FROM empresas GROUP BY uf ORDER BY qtd DESC;
-- SELECT razao_social, capital_social FROM empresas WHERE situacao = 'ATIVA' ORDER BY capital_social DESC;
