#!/usr/bin/env python3
"""Importador local (zero dependências) de CSVs municipais de MG (SEJUSP-MG, SES-MG e Ligue 180).

Exemplos de uso:
  # SEJUSP-MG (Feminicídio ou Violência Doméstica)
  python3 scripts/import_indicadores.py \
    --db data/violencia_mg.db \
    --csv data/raw/feminicidio_2025.csv \
    --fonte sejusp_mg \
    --tipo feminicidio \
    --dry-run

  # SES-MG (Notificações SINAN — contagem linha a linha ou coluna de quantidade)
  python3 scripts/import_indicadores.py \
    --db data/violencia_mg.db \
    --csv data/raw/violencia_ses.csv \
    --fonte ses_mg \
    --tipo violencia_saude \
    --dry-run
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
import sqlite3
import sys
import unicodedata


DEFAULT_COLUMNS = {
    "sejusp_mg": {
        "municipio": ["municipio_cod", "municipio_fato", "municipio", "nome_municipio", "cod_ibge", "codigo_ibge", "municipio_codigo"],
        "ano": ["ano", "ano_fato", "data_fato", "data"],
        "valor": ["qtde_vitimas", "registros", "total", "quantidade", "vitimas", "valor"],
        "taxa": ["taxa", "taxa_100k", "taxa_por_100_mil"],
        "filtro": ["natureza", "tipo_crime", "tentado_consumado", "evento", "descricao"],
    },
    "ses_mg": {
        "municipio": ["municipio_residencia", "municipio_ocorrencia", "municipio", "id_mn_resi", "id_municip", "codigo_ibge"],
        "ano": ["ano", "nu_ano", "dt_notific", "dt_ocor", "data"],
        "valor": ["quantidade", "total", "casos", "notificacoes", "valor"],
        "taxa": ["taxa", "taxa_100k"],
        "filtro": ["tipo_violencia", "viol_fisic", "viol_psico", "viol_sexu", "natureza"],
    },
    "ligue180": {
        "municipio": ["municipio", "municipio_vitima", "cidade", "codigo_ibge"],
        "ano": ["ano", "data_de_cadastro", "data_cadastro", "data"],
        "valor": ["quantidade", "total", "denuncias", "atendimentos", "valor"],
        "taxa": ["taxa", "taxa_100k"],
        "filtro": ["violacao", "tipo_violencia", "natureza"],
    },
}


def normalize_text(value: str) -> str:
    cleaned = unicodedata.normalize("NFKD", value or "")
    ascii_only = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    return " ".join(ascii_only.lower().strip().replace("-", " ").replace("/", " ").split())


def normalize_col(name: str) -> str:
    return normalize_text(name).replace(" ", "_")


def parse_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = raw.strip().replace(".", "").replace(" ", "")
    if not text or text in {"-", "na", "n/a", "null", "ni", "nao informado"}:
        return None
    if "," in text:
        text = text.split(",", 1)[0]
    try:
        return int(text)
    except ValueError:
        return None


def parse_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = raw.strip().replace(" ", "")
    if not text or text in {"-", "na", "n/a", "null"}:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_year(raw: str | None, fallback_year: int | None) -> int | None:
    if raw:
        digits = "".join(ch for ch in raw if ch.isdigit())
        for idx in range(0, max(0, len(digits) - 3)):
            chunk = digits[idx : idx + 4]
            if chunk.startswith(("19", "20")):
                return int(chunk)
    return fallback_year


def open_csv_text(csv_path: Path) -> tuple[str, str]:
    raw_bytes = csv_path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Não foi possível decodificar {csv_path}")


def detect_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        return ";" if sample.count(";") >= sample.count(",") else ","


def resolve_column(
    header_map: dict[str, str],
    explicit: str | None,
    candidates: list[str],
    required: bool = False,
    label: str = "",
) -> str | None:
    if explicit:
        key = normalize_col(explicit)
        if key in header_map:
            return header_map[key]
        raise KeyError(
            f"Coluna '{explicit}' não encontrada no CSV. Disponíveis: {list(header_map.values())}"
        )
    for cand in candidates:
        if cand in header_map:
            return header_map[cand]
    if required:
        raise KeyError(
            f"Não foi possível detectar a coluna de {label}. "
            f"Informe via flag (--col-{label}). Disponíveis: {list(header_map.values())}"
        )
    return None


def load_mg_municipios(conn: sqlite3.Connection) -> tuple[dict[str, str], dict[str, int | None]]:
    """Mapeia código IBGE (6 ou 7 dígitos) e nome normalizado -> codigo_ibge (7 dígitos)."""
    lookup: dict[str, str] = {}
    populacoes: dict[str, int | None] = {}
    rows = conn.execute("SELECT codigo_ibge, nome, populacao FROM municipios").fetchall()
    if not rows:
        raise RuntimeError(
            "Tabela 'municipios' vazia. Rode 'python3 scripts/sync_ibge_mg.py' antes de importar."
        )
    for codigo, nome, pop in rows:
        cod_str = str(codigo).strip()
        lookup[cod_str] = cod_str
        if len(cod_str) == 7:
            # SINAN/DATASUS frequentemente usa código IBGE de 6 dígitos (sem dígito verificador)
            lookup[cod_str[:6]] = cod_str
        lookup[normalize_text(nome)] = cod_str
        populacoes[cod_str] = pop
    return lookup, populacoes


def import_csv(args: argparse.Namespace) -> None:
    db_path = Path(args.db)
    csv_path = Path(args.csv)
    if not db_path.exists():
        raise FileNotFoundError(f"Banco SQLite não encontrado: {db_path}")
    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_path}")

    text, encoding = open_csv_text(csv_path)
    delimiter = args.delimiter or detect_delimiter(text[:4096])

    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV sem cabeçalho.")

    header_map = {normalize_col(h): h for h in reader.fieldnames if h}
    defaults = DEFAULT_COLUMNS[args.fonte]

    col_mun = resolve_column(header_map, args.col_municipio, defaults["municipio"], required=True, label="municipio")
    col_ano = resolve_column(header_map, args.col_ano, defaults["ano"], required=args.ano_fixo is None, label="ano")
    col_valor = resolve_column(header_map, args.col_valor, defaults["valor"], required=False, label="valor")
    col_taxa = resolve_column(header_map, args.col_taxa, defaults["taxa"], required=False, label="taxa")
    col_filtro = resolve_column(
        header_map,
        args.filtro_coluna,
        defaults["filtro"],
        required=bool(args.filtro_valor),
        label="filtro",
    )

    filtro_alvo = normalize_text(args.filtro_valor) if args.filtro_valor else None

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        fonte_row = conn.execute(
            "SELECT id, nome FROM fontes WHERE slug = ?", (args.fonte,)
        ).fetchone()
        if not fonte_row:
            raise ValueError(f"Fonte '{args.fonte}' não cadastrada na tabela fontes.")
        fonte_id, fonte_nome = fonte_row

        mun_lookup, populacoes = load_mg_municipios(conn)

        totais: dict[tuple[str, int], int] = defaultdict(int)
        taxas_csv: dict[tuple[str, int], list[float]] = defaultdict(list)
        linhas_lidas = 0
        linhas_filtradas = 0
        sem_municipio = 0

        for row in reader:
            linhas_lidas += 1
            if filtro_alvo and col_filtro:
                if filtro_alvo not in normalize_text(row.get(col_filtro, "")):
                    continue
            linhas_filtradas += 1

            raw_mun = (row.get(col_mun) or "").strip()
            digits_mun = "".join(ch for ch in raw_mun if ch.isdigit())
            codigo_ibge = mun_lookup.get(digits_mun) or mun_lookup.get(normalize_text(raw_mun))
            if not codigo_ibge:
                sem_municipio += 1
                continue

            ano = parse_year(row.get(col_ano) if col_ano else None, args.ano_fixo)
            if not ano:
                continue

            if col_valor:
                val = parse_int(row.get(col_valor))
                if val is None:
                    continue
                totais[(codigo_ibge, ano)] += val
            else:
                totais[(codigo_ibge, ano)] += 1

            if col_taxa:
                taxa = parse_float(row.get(col_taxa))
                if taxa is not None:
                    taxas_csv[(codigo_ibge, ano)].append(taxa)

        print(
            f"CSV lido ({encoding}, delimitador '{delimiter}'): "
            f"{linhas_lidas} linhas | {linhas_filtradas} após filtro | "
            f"{sem_municipio} fora de MG/sem match | {len(totais)} pares (município, ano)"
        )

        registros: list[tuple[str, int, str, int, float | None, int]] = []
        for (codigo_ibge, ano), valor_abs in sorted(totais.items()):
            taxa_final: float | None = None
            if taxas_csv.get((codigo_ibge, ano)):
                vals = taxas_csv[(codigo_ibge, ano)]
                taxa_final = round(sum(vals) / len(vals), 2)
            elif populacoes.get(codigo_ibge):
                pop = populacoes[codigo_ibge]
                if pop and pop > 0:
                    taxa_final = round((valor_abs / pop) * 100_000, 2)
            registros.append((codigo_ibge, ano, args.tipo, valor_abs, taxa_final, fonte_id))

        if args.dry_run:
            print(f"[DRY-RUN] Preview dos primeiros 10 registros para '{fonte_nome}':")
            for rec in registros[:10]:
                print(f"  IBGE={rec[0]} | ano={rec[1]} | tipo={rec[2]} | valor={rec[3]} | taxa_100k={rec[4]}")
            return

        conn.executemany(
            """
            INSERT INTO indicadores (codigo_ibge, ano, tipo, valor_absoluto, taxa_100k, fonte_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (codigo_ibge, ano, tipo, fonte_id)
            DO UPDATE SET
                valor_absoluto = excluded.valor_absoluto,
                taxa_100k = COALESCE(excluded.taxa_100k, indicadores.taxa_100k)
            """,
            registros,
        )
        conn.execute(
            "UPDATE fontes SET data_atualizacao = ? WHERE id = ?",
            (date.today().isoformat(), fonte_id),
        )
        conn.commit()
        print(f"Importação concluída: {len(registros)} registros gravados em {db_path}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Importa CSVs municipais de MG (SEJUSP-MG, SES-MG ou Ligue 180) para SQLite."
    )
    parser.add_argument("--db", default="data/violencia_mg.db", help="Caminho do banco SQLite")
    parser.add_argument("--csv", required=True, help="Caminho do CSV oficial")
    parser.add_argument("--fonte", required=True, choices=["sejusp_mg", "ses_mg", "ligue180"], help="Slug da fonte")
    parser.add_argument("--tipo", required=True, help="Tipo do indicador (ex.: feminicidio, violencia_domestica, violencia_saude)")
    parser.add_argument("--ano-fixo", type=int, default=None, help="Ano fixo caso o CSV não tenha coluna de ano")
    parser.add_argument("--delimiter", default=None, help="Delimitador manual (ex.: ';' ou ',')")
    parser.add_argument("--col-municipio", default=None, help="Nome da coluna de município ou código IBGE")
    parser.add_argument("--col-ano", default=None, help="Nome da coluna de ano ou data")
    parser.add_argument("--col-valor", default=None, help="Nome da coluna de contagem (omitir para contar 1 por linha)")
    parser.add_argument("--col-taxa", default=None, help="Nome da coluna de taxa por 100 mil hab.")
    parser.add_argument("--filtro-coluna", default=None, help="Coluna para filtrar registros")
    parser.add_argument("--filtro-valor", default=None, help="Texto contido na coluna de filtro")
    parser.add_argument("--dry-run", action="store_true", help="Apenas mostra o preview sem gravar no banco")
    return parser


if __name__ == "__main__":
    try:
        import_csv(build_parser().parse_args())
    except Exception as exc:
        print(f"Erro na importação: {exc}", file=sys.stderr)
        sys.exit(1)
