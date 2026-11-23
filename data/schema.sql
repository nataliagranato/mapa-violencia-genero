PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS fontes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    slug              TEXT NOT NULL UNIQUE,
    nome              TEXT NOT NULL,
    orgao             TEXT NOT NULL,
    url_oficial       TEXT NOT NULL,
    data_atualizacao  TEXT,
    nota_metodologica TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS municipios (
    codigo_ibge  TEXT PRIMARY KEY,
    nome         TEXT NOT NULL,
    microrregiao TEXT,
    mesorregiao  TEXT,
    populacao    INTEGER
);

CREATE TABLE IF NOT EXISTS indicadores (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_ibge    TEXT NOT NULL REFERENCES municipios(codigo_ibge),
    ano            INTEGER NOT NULL,
    tipo           TEXT NOT NULL,
    valor_absoluto INTEGER NOT NULL,
    taxa_100k      REAL,
    fonte_id       INTEGER NOT NULL REFERENCES fontes(id),
    UNIQUE (codigo_ibge, ano, tipo, fonte_id)
);

CREATE TABLE IF NOT EXISTS rede_apoio (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_ibge TEXT NOT NULL REFERENCES municipios(codigo_ibge),
    nome        TEXT NOT NULL,
    categoria   TEXT NOT NULL,
    endereco    TEXT,
    telefone    TEXT,
    lat         REAL,
    lng         REAL
);

CREATE INDEX IF NOT EXISTS idx_indicadores_filtro
    ON indicadores (tipo, ano, codigo_ibge);

CREATE INDEX IF NOT EXISTS idx_municipios_mesorregiao
    ON municipios (mesorregiao, nome);

CREATE INDEX IF NOT EXISTS idx_rede_apoio_municipio
    ON rede_apoio (codigo_ibge, categoria);
