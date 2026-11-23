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
docker compose up --build      # primeira vez
docker compose up -d           # depois
docker compose logs -f backend
docker compose down
```

| Serviço | Container | Porta | Imagem | Limite |
|---|---|---|---|---|
| `backend` | `mapa-mg-backend` | 8080 | `golang:1.22-alpine` → `alpine:3.20`, binário estático | `mem_limit: 128m` |
| `frontend` | `mapa-mg-frontend` | 5173 | `node:22-alpine`, `npm run dev -- --host 0.0.0.0` | `mem_limit: 256m` |

Volumes:
- `./data:/data` — o backend lê `/data/violencia_mg.db` (por isso `DB_PATH` é absoluto no container).
- `./frontend/public:/app/public:ro` — malha GeoJSON editável sem rebuild.

`frontend` recebe `VITE_API_TARGET=http://backend:8080` e depende de `backend`.

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
| API responde, mas indicadores antigos depois de importar | processo Go preso ao `-shm` antigo (WAL) | `docker compose restart backend` |
| `bind: address already in use` na 5173 | outro Vite (ex.: projeto anterior) ocupando a porta | `fuser -k 5173/tcp` ou `ss -ltnp \| grep 5173` |
| `403 Forbidden` ao baixar CSV de `dados.mg.gov.br` | UA padrão de `urllib`/`curl` bloqueado | já resolvido em `sync_sejusp_mg.py` (UA de browser) |
| `missing go.sum entry for modernc.org/sqlite` | `go.sum` desatualizado após mudar dependência | `cd backend && go mod tidy` |
| Mapa cinza, todos os municípios `#cbd5e1` | `ano`/`tipo` sem dados (ex.: `violencia_saude` ainda não importado) | escolher indicador com dados ou importar a fonte |
| `Malha de MG não encontrada` no frontend | `public/malhas/*.geojson` ausente | `python3 scripts/sync_ibge_mg.py` |
| `database is locked` na ingestão com API no ar | escrita concorrente | `docker compose stop backend` antes de importar lote grande |

## Checklist de atualização de dados

```bash
python3 scripts/sync_sejusp_mg.py --refresh          # rebaixa tudo
sqlite3 data/violencia_mg.db "PRAGMA wal_checkpoint(TRUNCATE);"
docker compose restart backend
curl -s "localhost:8080/api/mapa?ano=2026&tipo=feminicidio" | head -c 300
```

## Observabilidade atual

- Backend: `log` padrão — uma linha na subida, `log.Fatalf` em falha de banco/servidor.
- Ingestão: contadores por execução (linhas lidas, filtradas, sem match, pares gravados).
- Sem métricas, tracing, healthcheck de container ou alerta. Para uso contínuo:
  adicionar `HEALTHCHECK` no Dockerfile batendo em `/api/health` e exportar
  latência/erro por rota.
