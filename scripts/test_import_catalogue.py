"""Test manuel de l'import catalogue Excel (aucune écriture dans le catalogue).

Usage :  python scripts/test_import_catalogue.py <chemin/vers/fichier.xlsx>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.import_catalogue_pac import parse_catalogue_xlsx_report


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_import_catalogue.py <fichier.xlsx>")
        raise SystemExit(2)
    path = sys.argv[1]
    models, warnings = parse_catalogue_xlsx_report(path)

    print(f"=== {len(models)} modèle(s) produit(s) ===")
    for m in models:
        print(f"- {m['ref']} | {m['nom']} | {m['usage']} | {m['alim']} | "
              f"puiss35={m['puiss35']} etas35={m['etas35']} etas55={m['etas55']} "
              f"achat={m['achat']} ttc={m['ttc']} | {len(m['description_specs'])} specs")

    if warnings:
        print(f"\n=== {len(warnings)} avertissement(s) ===")
        for w in warnings:
            print("  ! " + w)

    if models:
        print("\n=== 1er modèle (JSON complet) ===")
        print(json.dumps(models[0], ensure_ascii=False, indent=2))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "import_preview.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(models, f, ensure_ascii=False, indent=2)
    print(f"\nAperçu complet écrit dans : {out}")


if __name__ == "__main__":
    main()
