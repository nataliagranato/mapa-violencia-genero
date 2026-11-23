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

### Via Docker (recomendado)

```bash
docker compose up --build        # 1. migra o banco e sobe API + frontend
docker compose run --rm ingest   # 2. baixa e importa os dados oficiais (só na 1ª vez)
```

- Frontend: <http://localhost:5173>
- API: <http://localhost:8080/api/health>

Dois serviços de ciclo curto cuidam do banco:

| Serviço | Quando roda | O que faz |
|---|---|---|
| `migrate` | a cada `docker compose up` | aplica `data/schema.sql` + `data/seed_fontes_mg.sql` (idempotente); o `backend` só sobe depois que ele termina com sucesso |
| `ingest` | sob demanda (`run --rm ingest`) | `sync_ibge_mg.py` (853 municípios + malha GeoJSON) e depois `sync_sejusp_mg.py` (22 CSVs, 2014–2026) |

A ingestão fica fora do `up` de propósito: são ~133 MB de CSV e ~30 s de import. Rode de novo sempre que quiser atualizar os dados — **pode rodar com a stack no ar**, o backend não precisa de restart.

Nenhum passo manual: não é preciso Python, `go mod tidy` nem `npm install` na máquina.

### Sem Docker (desenvolvimento)

Útil para editar o frontend com HMR nativo ou depurar o Go com `dlv`. Exige Python 3.10+, Go 1.22+ e Node 20+.

```bash
python3 scripts/init_db.py        # schema + seed de fontes
python3 scripts/sync_ibge_mg.py   # 853 municípios (API de Localidades do IBGE) + malha GeoJSON
python3 scripts/sync_sejusp_mg.py # baixa o que falta em data/raw/ e importa os 22 CSVs
```

```bash
# terminal 1 — API
cd backend && go mod tidy && go run .

# terminal 2 — frontend (proxy /api → localhost:8080)
cd frontend && npm install && npm run dev
```

Para importar CSV a CSV (use `--dry-run` primeiro para validar):

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

## Fontes oficiais de Minas Gerais

- [SEJUSP-MG — Violência contra Mulher (Feminicídio 2018–2026 e Violência Doméstica 2014–2026)](https://dados.mg.gov.br/dataset/violencia-contra-mulher)
- [SES-MG — Violência contra Mulheres (SINAN estadual)](https://dados.mg.gov.br/dataset/violencia_ses)
- [Centros de Atendimento à Mulher em MG (TRT-3 — DEAMs, CREAS e Defensoria)](https://portal.trt3.jus.br/internet/institucional/violencia-domestica-denuncie)
- [Casa da Mulher Mineira (PCMG)](https://www.agenciaminas.mg.gov.br/noticia/policia-civil-inaugura-casa-da-mulher-mineira-113251)
- [Ligue 180 — Central de Atendimento à Mulher](https://www.gov.br/mulheres/pt-br/ligue180)

## Privacidade e ética

- Exiba apenas agregações municipais e taxas por 100 mil habitantes para evitar reidentificação de vítimas em cidades pequenas (LGPD).
- Mantenha o aviso de subnotificação, o link do Ligue 180 e o botão de **Saída Rápida** (`Esc`).
