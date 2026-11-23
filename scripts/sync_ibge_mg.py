#!/usr/bin/env python3
"""Sincroniza os 853 municípios de Minas Gerais e a malha GeoJSON simplificada via API do IBGE."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "violencia_mg.db"
MALHA_PATH = ROOT / "frontend" / "public" / "malhas" / "mg_municipios.geojson"

IBGE_LOCALIDADES_MG = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/31/municipios"
IBGE_MALHA_MG = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/31"
    "?intrarregiao=municipio&qualidade=minima&formato=application/vnd.geo+json"
)


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "mapa-violencia-genero-mg/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Rode 'python3 scripts/init_db.py' primeiro ({DB_PATH} não encontrado).")

    print("1/2 Baixando lista dos 853 municípios de MG (API de Localidades do IBGE)...")
    municipios_raw = json.loads(fetch_bytes(IBGE_LOCALIDADES_MG).decode("utf-8"))

    registros = []
    for item in municipios_raw:
        codigo = str(item["id"])
        nome = item["nome"]
        micro = (item.get("microrregiao") or {}).get("nome")
        meso = ((item.get("microrregiao") or {}).get("mesorregiao") or {}).get("nome")
        registros.append((codigo, nome, micro, meso))

    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO municipios (codigo_ibge, nome, microrregiao, mesorregiao)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (codigo_ibge) DO UPDATE SET
                nome = excluded.nome,
                microrregiao = excluded.microrregiao,
                mesorregiao = excluded.mesorregiao
            """,
            registros,
        )
        conn.commit()
    print(f"    {len(registros)} municípios sincronizados em {DB_PATH}.")

    print("2/2 Baixando malha municipal simplificada de MG (API de Malhas do IBGE)...")
    MALHA_PATH.parent.mkdir(parents=True, exist_ok=True)
    malha_bytes = fetch_bytes(IBGE_MALHA_MG)
    MALHA_PATH.write_bytes(malha_bytes)
    print(f"    Malha salva em {MALHA_PATH} ({len(malha_bytes) / 1024:.1f} KB).")


if __name__ == "__main__":
    main()
