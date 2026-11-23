# Backend — API Go

## Stack e layout

```
backend/
├── main.go      # tudo: modelos, handlers, servidor
├── go.mod       # module mapa-violencia-genero-mg/backend, go 1.22
├── go.sum
└── Dockerfile   # builder golang:1.22-alpine → alpine:3.20, CGO_ENABLED=0
```

Dependência única: `modernc.org/sqlite v1.34.5` (driver SQLite em Go puro, sem CGO).
Roteamento com o `http.ServeMux` do Go 1.22 — padrões `"MÉTODO /rota/{param}"`.

## Configuração

| Variável | Default | Uso |
|---|---|---|
| `ADDR` | `:8080` | Endereço de escuta |
| `DB_PATH` | `../data/violencia_mg.db` | Caminho do SQLite (no Compose: `/data/violencia_mg.db`) |

DSN aplicado na abertura (`main.go:77`):

```
<dbPath>?_pragma=journal_mode(WAL)&_pragma=busy_timeout(5000)&_pragma=foreign_keys(ON)
```

- `journal_mode(WAL)` — leitores não bloqueiam a ingestão que grava em paralelo.
- `busy_timeout(5000)` — espera até 5 s por lock em vez de falhar imediatamente.
- `foreign_keys(ON)` — o SQLite desliga FK por conexão; precisa ser reafirmado.

## Concorrência

`db.SetMaxOpenConns(1)` (`main.go:84`) — **uma** conexão simultânea por processo.
`db.SetMaxIdleConns(0)` logo abaixo — nenhuma conexão fica ociosa entre requests.

Justificativa: o SQLite em WAL aceita N leitores + 1 escritor, mas o escritor aqui é
**outro processo** (`import_indicadores.py` / `sync_sejusp_mg.py`). Limitar a API a
uma conexão elimina contenção interna e torna previsível o comportamento quando a
ingestão roda. Custo: requisições serializam no pool. Para 853 linhas por request e
tráfego local, o throughput é dominado pela serialização JSON, não pelo pool.

O `MaxIdleConns(0)` não é enfeite: quando o import fecha a última conexão, o SQLite
faz checkpoint e recria o `-shm`. Uma conexão ociosa do Go continua apontando para o
índice WAL antigo e **toda query passa a falhar** (`erro ao consultar mapa de MG`)
até o processo reiniciar — sintoma silencioso, sem nada no log. Abrir/fechar por
request custa microssegundos neste workload e elimina a classe inteira de bug, com
a ingestão podendo rodar com a API no ar.

`ponytail:` teto = serialização de leitura + open/close por query. Subir para N
conexões e pool persistente quando houver tráfego concorrente real — e aí a ingestão
precisa deixar de rodar com a API no ar, ou o banco precisa sair do SQLite.

## Endpoints

| Método | Rota | Parâmetros | Retorno |
|---|---|---|---|
| GET | `/api/health` | — | `{"status":"ok","escopo":"MG"}` |
| GET | `/api/fontes` | — | array de fontes cadastradas |
| GET | `/api/mapa` | `tipo` (default `feminicidio`), `ano` (default `2025`), `mesorregiao` (opcional) | `{uf, ano, tipo, itens[]}` com **todos** os 853 municípios |
| GET | `/api/municipio/{codigo}` | código IBGE de 7 dígitos | detalhe + `series[]` + `rede_apoio[]`; `404` se não existir |
| GET | `/api/rede-apoio` | `municipio` (opcional) | array (vazio hoje) |

### Exemplos reais de resposta

`GET /api/health`
```json
{"escopo":"MG","status":"ok"}
```

`GET /api/mapa?ano=2025&tipo=feminicidio` (recorte)
```json
{
  "ano": 2025,
  "itens": [
    {"codigo_ibge":"3100104","nome":"Abadia dos Dourados","mesorregiao":"Triângulo Mineiro/Alto Paranaíba","microrregiao":"Patrocínio","valor_absoluto":null,"taxa_100k":null,"fonte_slug":null},
    {"codigo_ibge":"3100203","nome":"Abaeté","mesorregiao":"Central Mineira","microrregiao":"Três Marias","valor_absoluto":1,"taxa_100k":null,"fonte_slug":"sejusp_mg"}
  ],
  "tipo": "feminicidio",
  "uf": "MG"
}
```

`GET /api/municipio/3106200` (recorte)
```json
{
  "codigo_ibge": "3106200",
  "nome": "Belo Horizonte",
  "microrregiao": "Belo Horizonte",
  "mesorregiao": "Metropolitana de Belo Horizonte",
  "populacao": null,
  "series": [
    {"ano":2026,"tipo":"feminicidio","valor_absoluto":25,"taxa_100k":null,
     "fonte_nome":"Violência contra Mulher — SEJUSP-MG",
     "fonte_url":"https://dados.mg.gov.br/dataset/violencia-contra-mulher"}
  ],
  "rede_apoio": []
}
```

`GET /api/rede-apoio` → `[]` (tabela vazia hoje).

### Contratos

Campos opcionais são ponteiros (`*int`, `*float64`, `*string`) para sair como
`null` em vez de `0`/`""` — importante porque `0` significaria "zero casos" e
`null` significa "sem dado". O frontend distingue os dois.

## Padrões de consulta

`/api/mapa` usa `municipios LEFT JOIN indicadores` **para retornar os 853
municípios mesmo sem indicador no ano/tipo pedido**. Sem o `LEFT JOIN`, o mapa
encolheria silenciosamente em anos com menos registros.

```sql
SELECT m.codigo_ibge, m.nome, m.mesorregiao, m.microrregiao,
       i.valor_absoluto, i.taxa_100k, f.slug
FROM municipios m
LEFT JOIN indicadores i
       ON i.codigo_ibge = m.codigo_ibge AND i.ano = ? AND i.tipo = ?
LEFT JOIN fontes f ON f.id = i.fonte_id
[WHERE m.mesorregiao = ?]
ORDER BY m.nome;
```

Todas as queries usam placeholders (`?`) — nenhuma interpolação de string com
entrada de usuário.

## Erros

Formato único: `{"erro": "mensagem"}`.

| Status | Quando |
|---|---|
| 400 | `ano` não numérico |
| 404 | código IBGE inexistente em `municipios` |
| 500 | falha de query/scan (`erro ao consultar mapa de MG`, etc.) |

Detalhe de infraestrutura não vaza para o cliente; o erro real vai para o log.

## Ciclo de vida

- `ReadHeaderTimeout: 5s` — mitiga slowloris.
- SIGINT/SIGTERM → `srv.Shutdown` com deadline de 5 s.
- `Ping()` na subida: falha rápido se o banco não existir/estiver corrompido.
- Log de linha única na subida com endereço e caminho do SQLite.

## Lacunas conhecidas

1. `tipo` e `ano` não são validados contra uma lista — valor inválido devolve 853
   linhas com `null`, não `400`.
2. Sem paginação, sem `ETag`/`Cache-Control`, sem compressão gzip.
3. Sem CORS: o acesso é esperado via proxy do Vite (mesma origem).
4. Sem métricas/tracing — apenas `log` padrão.
5. Sem testes automatizados (`go test` não cobre handlers).
6. `rede_apoio` não tem endpoint de escrita: é populada por SQL/seed.
