# Mapa da Violência de Gênero — Minas Gerais 

Projeto base local e ultraleve para mapeamento municipal da violência de gênero em **Minas Gerais**, alinhado aos Objetivos de Desenvolvimento Sustentável da ONU:

- **ODS 16 ([Paz, Justiça e Instituições Eficazes](https://www.ipea.gov.br/ods/ods16.html)):** Metas 16.1 (redução de todas as formas de violência), 16.3 (acesso à justiça) e 16.6 (instituições eficazes e transparentes).
- **ODS 5 ([Igualdade de Gênero](https://www.ipea.gov.br/ods/ods5.html)):** Meta 5.2 (eliminar todas as formas de violência contra todas as mulheres e meninas).

## Documentação

Arquitetura completa em [`docs/`](docs/README.md): visão geral, backend (API Go),
frontend (Vite + Leaflet), banco de dados (SQLite), ingestão de dados, operação e
segurança/privacidade (LGPD).

## Stack local (baixo consumo de recursos)

- **Banco de dados:** [SQLite](https://www.sqlite.org/about.html) (`data/violencia_mg.db`, modo [WAL](https://www.sqlite.org/wal.html)).
- **Backend:** Go (`net/http` padrão + [modernc.org/sqlite](https://pkg.go.dev/modernc.org/sqlite), sem CGO).
- **Frontend:** [Vite](https://vite.dev/) + [Leaflet](https://leafletjs.com/examples/geojson/).

## Como rodar localmente

### 1. Inicializar o banco SQLite
```bash
python3 scripts/init_db.py
```

### 2. Baixar os 853 municípios e a malha de MG (API do IBGE)
```bash
python3 scripts/sync_ibge_mg.py
```
Esse comando popula a tabela `municipios` via [API de Localidades do IBGE](https://servicodados.ibge.gov.br/api/docs/localidades) e baixa a malha simplificada para `frontend/public/malhas/mg_municipios.geojson` via [API de Malhas Geográficas do IBGE](https://servicodados.ibge.gov.br/api/docs/malhas?versao=3).

### 3. Importar CSVs oficiais de Minas Gerais

Atalho — baixa e importa os 22 CSVs do dataset SEJUSP-MG (2014–2026) de uma vez:

```bash
python3 scripts/sync_sejusp_mg.py            # baixa o que falta em data/raw/ e importa
python3 scripts/sync_sejusp_mg.py --refresh  # rebaixa todos
```

Depois de importar, reinicie o backend se ele já estava rodando:
`docker compose restart backend` — em modo WAL, o processo Go fica preso ao
`-shm` antigo quando outro processo (o import) fecha a última conexão.

Ou importe CSV a CSV (use `--dry-run` primeiro para validar):

```bash
# SEJUSP-MG — Feminicídio ou Violência Doméstica
python3 scripts/import_indicadores.py \
  --db data/violencia_mg.db \
  --csv data/raw/feminicidio_2025.csv \
  --fonte sejusp_mg \
  --tipo feminicidio \
  --dry-run

# SES-MG — Notificações de Saúde (SINAN)
python3 scripts/import_indicadores.py \
  --db data/violencia_mg.db \
  --csv data/raw/violencia_ses.csv \
  --fonte ses_mg \
  --tipo violencia_saude \
  --dry-run
```

### 4. Subir a API em Go
```bash
cd backend
go mod tidy
go run .
```
A API sobe em `http://localhost:8080`.

### 5. Subir o frontend com Vite
Em outro terminal:
```bash
cd frontend
npm install
npm run dev
```
O Vite sobe em `http://localhost:5173` com proxy automático de `/api` para o backend em Go.

## Fontes oficiais de Minas Gerais

- [SEJUSP-MG — Violência contra Mulher (Feminicídio 2018–2026 e Violência Doméstica 2014–2026)](https://dados.mg.gov.br/dataset/violencia-contra-mulher)
- [SES-MG — Violência contra Mulheres (SINAN estadual)](https://dados.mg.gov.br/dataset/violencia_ses)
- [Centros de Atendimento à Mulher em MG (TRT-3 — DEAMs, CREAS e Defensoria)](https://portal.trt3.jus.br/internet/institucional/violencia-domestica-denuncie)
- [Casa da Mulher Mineira (PCMG)](https://www.agenciaminas.mg.gov.br/noticia/policia-civil-inaugura-casa-da-mulher-mineira-113251)
- [Ligue 180 — Central de Atendimento à Mulher](https://www.gov.br/mulheres/pt-br/ligue180)

## Privacidade e ética

- Exiba apenas agregações municipais e taxas por 100 mil habitantes para evitar reidentificação de vítimas em cidades pequenas (LGPD).
- Mantenha o aviso de subnotificação, o link do Ligue 180 e o botão de **Saída Rápida** (`Esc`).
