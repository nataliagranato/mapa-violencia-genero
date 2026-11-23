#!/usr/bin/env python3
"""Inicializa o banco SQLite local de Minas Gerais (data/violencia_mg.db)."""

from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "violencia_mg.db"


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        for sql_file in ("schema.sql", "seed_fontes_mg.sql"):
            sql = (DATA_DIR / sql_file).read_text(encoding="utf-8")
            conn.executescript(sql)

        fontes = conn.execute("SELECT COUNT(*) FROM fontes").fetchone()[0]
        municipios = conn.execute("SELECT COUNT(*) FROM municipios").fetchone()[0]
        indicadores = conn.execute("SELECT COUNT(*) FROM indicadores").fetchone()[0]

    print(f"Banco pronto em: {DB_PATH}")
    print(f"Fontes: {fontes} | Municípios de MG: {municipios} | Indicadores: {indicadores}")
    if municipios == 0:
        print("Próximo passo: rode 'python3 scripts/sync_ibge_mg.py' para carregar os 853 municípios e a malha de MG.")


if __name__ == "__main__":
    main()
