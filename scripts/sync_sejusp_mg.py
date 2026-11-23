#!/usr/bin/env python3
"""Baixa todos os CSVs do dataset "Violência contra Mulher" (SEJUSP-MG) e importa no SQLite.

  python3 scripts/sync_sejusp_mg.py            # baixa o que falta em data/raw/ e importa tudo
  python3 scripts/sync_sejusp_mg.py --refresh  # rebaixa todos os CSVs
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_indicadores import import_csv  # noqa: E402  (reusa o importador existente)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "violencia_mg.db"
DATASET = "https://dados.mg.gov.br/api/3/action/package_show?id=violencia-contra-mulher"
# o portal responde 403 para o User-Agent padrão do urllib/curl
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"}


def get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="rebaixa CSVs já presentes")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    resources = json.loads(get(DATASET))["result"]["resources"]

    for res in resources:
        if res.get("format") != "CSV":
            continue
        nome = res["name"].lower()
        tipo = "feminicidio" if "feminicidio" in nome else "violencia_domestica"
        destino = RAW / Path(res["url"]).name

        if args.refresh or not destino.exists():
            destino.write_bytes(get(res["url"]))
            print(f"baixado {destino.name} ({destino.stat().st_size // 1024} kB)")

        import_csv(
            argparse.Namespace(
                db=str(DB), csv=str(destino), fonte="sejusp_mg", tipo=tipo,
                ano_fixo=None, delimiter=None, col_municipio=None, col_ano=None,
                col_valor=None, col_taxa=None, filtro_coluna=None, filtro_valor=None,
                dry_run=False,
            )
        )


if __name__ == "__main__":
    main()
