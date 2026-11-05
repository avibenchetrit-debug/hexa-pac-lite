# -*- coding: utf-8 -*-
"""Numéros EPREL et d'agrément du 05/11/2026 — tableau final vérifié par Avi (numéro EPREL = numéro de fiche ;
sources : bonus-pac.ademe.fr et fiches EPREL), déjà appliqué dans le CRM. Écriture UNIQUE au démarrage (marque
`maj_eprel_0511` par modèle) : seules les lignes « Référence EPREL » et « Numéro d'agrément » de la fiche technique
sont écrites (créées en fin de fiche si elles manquent). Rien d'autre n'est touché ; une valeur corrigée ensuite dans
l'Admin n'est jamais réécrite. THALEOS MONTBLANC DUO et R32 : non agréés bonus-pac, absents de pac-lite."""
MARQUE = "maj_eprel_0511"
CHAMP_EPREL = "Référence EPREL"
CHAMP_AGREMENT = "Numéro d'agrément"
NUMEROS = {
    "THA-MTBL-R290-4": ("2639877", "157-2026-000001"),
    "THA-MTBL-R290-6": ("2639879", "157-2026-000002"),
    "THA-MTBL-R290-8": ("2639880", "157-2026-000003"),
    "THA-MTBL-R290-10": ("2639884", "157-2026-000004"),
    "THA-MTBL-R290-12": ("2639887", "157-2026-000005"),
    "THA-MTBL-R290-14": ("2639914", "157-2026-000006"),
    "THA-MTBL-R290-16": ("2639934", "157-2026-000007"),
    "THA-MTBL-R290-8 TRI": ("2639935", "157-2026-000008"),
    "THA-MTBL-R290-10 TRI": ("2639936", "157-2026-000009"),
    "THA-MTBL-R290-12 TRI": ("2639937", "157-2026-000010"),
    "THA-MTBL-R290-14 TRI": ("2639938", "157-2026-000011"),
    "THA-MTBL-R290-16 TRI": ("2639939", "157-2026-000012"),
    "ATL-EXCELLIA-S-9": ("2216896", "11-2026-000095"),
    "ATL-EXCELLIA-S-12": ("2216897", "11-2026-000096"),
    "ATL-EXCELLIA-S-14": ("2216898", "11-2026-000097"),
    "ATL-EXCELLIA-S-12 TRI": ("2216899", "11-2026-000098"),
    "ATL-EXCELLIA-S-14 TRI": ("2216890", "11-2026-000099"),
    "ATL-EXCELLIA-S-DUO-9": ("2216891", "11-2026-000090"),
    "ATL-EXCELLIA-S-DUO-12": ("2216892", "11-2026-000091"),
    "ATL-EXCELLIA-S-DUO-14": ("2216893", "11-2026-000092"),
    "ATL-EXCELLIA-S-DUO-12 TRI": ("2216894", "11-2026-000093"),
    "ATL-EXCELLIA-S-DUO-14 TRI": ("2216895", "11-2026-000094"),
    "DAI-ALTHERMA-3HHT-R32-14": ("1627026", "36-2026-000248"),
    "DAI-ALTHERMA-3HHT-R32-16": ("1623957", "36-2026-000249"),
    "DAI-ALTHERMA-3HHT-R32-18": ("1626326", "36-2026-000250"),
    "DAI-ALTHERMA-3HHT-R32-14 TRI": ("1626704", "36-2026-000251"),
    "DAI-ALTHERMA-3HHT-R32-16 TRI": ("1629289", "36-2026-000253"),
    "DAI-ALTHERMA-3HHT-R32-18 TRI": ("1622779", "36-2026-000255"),
    "ARI-NIMBUS-NET-R32-8": ("1252273", "6-2026-000003"),
    "ARI-NIMBUS-NET-R32-12": ("1577828", "6-2026-000002"),
    "ARI-NIMBUS-NET-R32-15": ("1577830", "6-2026-000001"),
    "ARI-NIMBUS-NET-R32-12 TRI": ("1577829", "6-2026-000040"),
    "ARI-NIMBUS-NET-R32-15 TRI": ("1577831", "6-2026-000041"),
    "ARI-NIMBUS-NET-R32-DUO-8": ("1252280", "6-2026-000004"),
    "ARI-NIMBUS-NET-R32-DUO-12": ("1598279", "6-2026-000013"),
    "ARI-NIMBUS-NET-R32-DUO-15": ("1598283", "6-2026-000017"),
    "ARI-NIMBUS-NET-R32-DUO-12 TRI": ("1598281", "6-2026-000015"),
    "ARI-NIMBUS-NET-R32-DUO-15 TRI": ("1598285", "6-2026-000019"),
    "DAI-ALTHERMA-4H-R290-8": ("2313553", "36-2026-000281"),
    "DAI-ALTHERMA-4H-R290-10": ("2333802", "36-2026-000280"),
    "DAI-ALTHERMA-4H-R290-8 TRI": ("2333793", "36-2026-000279"),
    "DAI-ALTHERMA-4H-R290-10 TRI": ("2333792", "36-2026-000278"),
    "DAI-ALTHERMA-4H-R290-12-TRI": ("2333805", "36-2026-000283"),
    "DAI-ALTHERMA-4H-R290-14-TRI": ("2333804", "36-2026-000282"),
}


def migrer_catalogue(catalogue):
    """(catalogue, changé). Idempotent."""
    change = False
    for m in catalogue if isinstance(catalogue, list) else []:
        if not isinstance(m, dict) or m.get(MARQUE):
            continue
        ref = str(m.get("ref") or "").strip()
        if ref not in NUMEROS:
            continue
        specs = [dict(s) for s in (m.get("description_specs") or []) if isinstance(s, dict)]
        for champ, valeur in zip((CHAMP_EPREL, CHAMP_AGREMENT), NUMEROS[ref]):
            ligne = next((s for s in specs if s.get("champ") == champ), None)
            if ligne is None:
                specs.append({"champ": champ, "valeur": valeur})
            else:
                ligne["valeur"] = valeur
        m["description_specs"] = specs
        m[MARQUE] = True
        change = True
    return catalogue, change
