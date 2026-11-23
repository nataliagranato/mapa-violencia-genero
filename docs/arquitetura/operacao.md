# Operação

## Pré-requisitos

| Caminho | Requisitos |
|---|---|
| Docker | Docker Engine/Desktop + Compose v2 |
| Nativo | Go 1.22+, Python 3.10+, Node 20+ |

Nenhuma chave de API, nenhum serviço externo em runtime. Rede só na ingestão
(IBGE e dados.mg.gov.br).

## Docker Compose

```bash
docker compose up --build          # primeira vez (migra o banco e sobe a stack)
docker compose up -d               # depois
docker compose run --rm ingest     # baixa e importa os dados oficiais (sob demanda)
docker compose logs -f backend
docker compose down
```

| Serviço | Container | Porta | Imagem | Limite |
|---|---|---|---|---|
| `migrate` | efêmero | — | `python:3.12-alpine` | — |
| `ingest` | efêmero | — | `python:3.12-alpine` | — |
| `backend` | `mapa-mg-backend` | 8080 | `golang:1.22-alpine` → `alpine:3.20`, binário estático | `mem_limit: 128m` |
| `frontend` | `mapa-mg-frontend` | 5173 | `node:22-alpine`, `npm run dev -- --host 0.0.0.0` | `mem_limit: 256m` |

Volumes:
- `./data:/data` — o backend lê `/data/violencia_mg.db` (por isso `DB_PATH` é absoluto no container); `migrate` e `ingest` escrevem no mesmo diretório, montado em `/app/data`.
- `./scripts:/app/scripts:ro` — os scripts Python entram nos containers de banco sem build.
- `./frontend/public:/app/public:ro` (frontend) e `./frontend/public:/app/frontend/public` (ingest, gravável) — a malha GeoJSON é escrita pelo `sync_ibge_mg.py` e lida pelo Vite sem rebuild.

`frontend` depende de `backend`; `backend` depende de `migrate` com
`condition: service_completed_successfully` — a API nunca sobe contra um schema
inexistente. `ingest` está sob `profiles: ["ingest"]`, então não roda no `up`:
são ~133 MB de download e ~30 s de import que não devem acontecer a cada subida.

`migrate` é idempotente (`CREATE TABLE IF NOT EXISTS` + `INSERT OR IGNORE`) e
custa <1 s, por isso pode rodar em toda subida.

Acesso: <http://localhost:5173> (a UI) e <http://localhost:8080/api/health> (a API).

## Execução nativa (sem Docker)

```bash
python3 scripts/init_db.py
python3 scripts/sync_ibge_mg.py
python3 scripts/sync_sejusp_mg.py

# terminal 1
cd backend && go run .            # ADDR=:8080, DB_PATH=../data/violencia_mg.db

# terminal 2
cd frontend && npm install && npm run dev
```

## Ordem de bootstrap (importa)

`init_db.py` → `sync_ibge_mg.py` → `sync_sejusp_mg.py`. O importador **falha de
propósito** se `municipios` estiver vazia, porque sem o de-para de códigos IBGE
todo registro seria descartado como "fora de MG".

## Troubleshooting

| Sintoma | Causa | Correção |
|---|---|---|
| API responde, mas indicadores antigos depois de importar | conexão ociosa com índice WAL obsoleto (WAL) | já mitigado: `db.SetMaxIdleConns(0)` em `main.go`; se voltar, `docker compose restart backend` |
| `bind: address already in use` na 5173 | outro Vite (ex.: projeto anterior) ocupando a porta | `fuser -k 5173/tcp` ou `ss -ltnp \| grep 5173` |
| `403 Forbidden` ao baixar CSV de `dados.mg.gov.br` | UA padrão de `urllib`/`curl` bloqueado | já resolvido em `sync_sejusp_mg.py` (UA de browser) |
| `missing go.sum entry for modernc.org/sqlite` | `go.sum` desatualizado após mudar dependência | `cd backend && go mod tidy` |
| Mapa cinza, todos os municípios `#cbd5e1` | `ano`/`tipo` sem dados (ex.: `violencia_saude` ainda não importado) | escolher indicador com dados ou importar a fonte |
| `Malha de MG não encontrada` no frontend | `public/malhas/*.geojson` ausente | `python3 scripts/sync_ibge_mg.py` |
| `database is locked` na ingestão com API no ar | escrita concorrente | `docker compose stop backend` antes de importar lote grande |

## Checklist de atualização de dados

```bash
docker compose run --rm ingest                       # ou: sync_sejusp_mg.py --refresh (nativo)
sqlite3 data/violencia_mg.db "PRAGMA wal_checkpoint(TRUNCATE);"
curl -s "localhost:8080/api/mapa?ano=2026&tipo=feminicidio" | head -c 300
```

Não é preciso reiniciar o backend: ele não mantém conexão ociosa (ver
[Concorrência](backend.md#concorrência)), então reabre o banco a cada request.

## Observabilidade atual

- Backend: `log` padrão — uma linha na subida, `log.Fatalf` em falha de banco/servidor.
- Ingestão: contadores por execução (linhas lidas, filtradas, sem match, pares gravados).
- Sem métricas, tracing, healthcheck de container ou alerta. Para uso contínuo:
  adicionar `HEALTHCHECK` no Dockerfile batendo em `/api/health` e exportar
  latência/erro por rota.
