# -*- coding: utf-8 -*-
"""Catalogue PAC air/eau : « Classe du régulateur (ErP) » et « Contribution à l'efficacité saisonnière (%) » dans la
fiche produit (description_specs), au même endroit que sur les fiches Ariston : juste après « Alimentation », dans cet
ordre. Ligne absente ou vide : créée avec la valeur du Master ; ligne remplie : valeur gardée, seulement replacée.
Aucun autre champ touché. Fonction pure, idempotente (la migration au démarrage est dans main.py)."""

CHAMP_ALIMENTATION = "Alimentation"
CHAMP_CLASSE = "Classe du régulateur (ErP)"
CHAMP_CONTRIBUTION = "Contribution à l'efficacité saisonnière (%)"

# Valeurs relevées dans le Master (hexa-simulateur-2, catalogue_pac_aireau.json, copie du 25/09/2026), champ
# `descriptif`. Correspondance par n° EPREL, identique des deux côtés : n° EPREL -> (réf. Master = réf. pac-lite,
# classe, contribution). Les modèles du Master sans n° EPREL (Thaleos Montblanc DUO et R32) n'existent pas dans
# pac-lite : rien n'est déduit pour eux.
VALEURS_MASTER = {
    "520556": ("ATL-EXCELLIA-S-9", "VI", "4"),
    "520557": ("ATL-EXCELLIA-S-12", "VI", "4"),
    "520558": ("ATL-EXCELLIA-S-14", "VI", "4"),
    "520559": ("ATL-EXCELLIA-S-12 TRI", "VI", "4"),
    "520560": ("ATL-EXCELLIA-S-14 TRI", "VI", "4"),
    "520561": ("ATL-EXCELLIA-S-DUO-9", "VI", "4"),
    "520562": ("ATL-EXCELLIA-S-DUO-12", "VI", "4"),
    "520563": ("ATL-EXCELLIA-S-DUO-14", "VI", "4"),
    "520564": ("ATL-EXCELLIA-S-DUO-12 TRI", "VI", "4"),
    "520565": ("ATL-EXCELLIA-S-DUO-14 TRI", "VI", "4"),
    "1627026": ("DAI-ALTHERMA-3HHT-R32-14", "VI", "4"),
    "1623957": ("DAI-ALTHERMA-3HHT-R32-16", "VI", "4"),
    "1626326": ("DAI-ALTHERMA-3HHT-R32-18", "VI", "4"),
    "1626704": ("DAI-ALTHERMA-3HHT-R32-14 TRI", "VI", "4"),
    "1629289": ("DAI-ALTHERMA-3HHT-R32-16 TRI", "VI", "4"),
    "1622779": ("DAI-ALTHERMA-3HHT-R32-18 TRI", "VI", "4"),
    "1252273": ("ARI-NIMBUS-NET-R32-8", "VI", "4"),
    "1577828": ("ARI-NIMBUS-NET-R32-12", "VI", "4"),
    "1577830": ("ARI-NIMBUS-NET-R32-15", "VI", "4"),
    "1577829": ("ARI-NIMBUS-NET-R32-12 TRI", "VI", "4"),
    "1577831": ("ARI-NIMBUS-NET-R32-15 TRI", "VI", "4"),
    "1252280": ("ARI-NIMBUS-NET-R32-DUO-8", "VI", "4"),
    "1598279": ("ARI-NIMBUS-NET-R32-DUO-12", "VI", "4"),
    "1598283": ("ARI-NIMBUS-NET-R32-DUO-15", "VI", "4"),
    "1598281": ("ARI-NIMBUS-NET-R32-DUO-12 TRI", "VI", "4"),
    "1598285": ("ARI-NIMBUS-NET-R32-DUO-15 TRI", "VI", "4"),
    "2639877": ("THA-MTBL-R290-4", "VI", "4"),
    "2639879": ("THA-MTBL-R290-6", "VI", "4"),
    "2639880": ("THA-MTBL-R290-8", "VI", "4"),
    "2639884": ("THA-MTBL-R290-10", "VI", "4"),
    "2639887": ("THA-MTBL-R290-12", "VI", "4"),
    "2639914": ("THA-MTBL-R290-14", "VI", "4"),
    "2639934": ("THA-MTBL-R290-16", "VI", "4"),
    "2639935": ("THA-MTBL-R290-8 TRI", "VI", "4"),
    "2639936": ("THA-MTBL-R290-10 TRI", "VI", "4"),
    "2639937": ("THA-MTBL-R290-12 TRI", "VI", "4"),
    "2639938": ("THA-MTBL-R290-14 TRI", "VI", "4"),
    "2639939": ("THA-MTBL-R290-16 TRI", "VI", "4"),
}


def _txt(v) -> str:
    return str(v if v is not None else "").strip()


def eprel_du_modele(modele: dict) -> str:
    specs = modele.get("description_specs") if isinstance(modele.get("description_specs"), list) else []
    return _txt(modele.get("eprel")) or next(
        (_txt(s.get("valeur")) for s in specs if isinstance(s, dict) and _txt(s.get("champ")) == "Référence EPREL"), "")


def placer_lignes_regulateur(modele: dict) -> tuple[dict, list[str]]:
    """(modèle, champs encore sans valeur). Le modèle rendu est le MÊME objet si rien ne change."""
    specs = modele.get("description_specs")
    if not isinstance(specs, list):
        return modele, [CHAMP_CLASSE, CHAMP_CONTRIBUTION]
    i_alim = next((i for i, s in enumerate(specs) if isinstance(s, dict) and _txt(s.get("champ")) == CHAMP_ALIMENTATION), None)
    master = VALEURS_MASTER.get(eprel_du_modele(modele))
    valeurs_master = {CHAMP_CLASSE: master[1], CHAMP_CONTRIBUTION: master[2]} if master else {}
    if i_alim is None:            # pas de ligne « Alimentation » : on ne sait pas où les mettre, rien n'est touché
        presentes = {_txt(s.get("champ")): _txt(s.get("valeur")) for s in specs if isinstance(s, dict)}
        return modele, [c for c in (CHAMP_CLASSE, CHAMP_CONTRIBUTION) if not presentes.get(c)]
    reste, lignes, manques = [], {}, []
    for s in specs:
        c = _txt(s.get("champ")) if isinstance(s, dict) else ""
        if c in (CHAMP_CLASSE, CHAMP_CONTRIBUTION):
            if c not in lignes or (not _txt(lignes[c].get("valeur")) and _txt(s.get("valeur"))):
                lignes[c] = s     # la première ligne remplie fait foi (un doublon vide disparaît)
            continue
        reste.append(s)
    a_inserer = []
    for c in (CHAMP_CLASSE, CHAMP_CONTRIBUTION):
        ligne = lignes.get(c)
        if ligne is not None and _txt(ligne.get("valeur")):
            a_inserer.append(ligne)                                       # remplie : gardée telle quelle
        elif valeurs_master.get(c):
            a_inserer.append({"champ": c, "valeur": valeurs_master[c]})   # absente ou vide : valeur du Master
        else:
            manques.append(c)
            if ligne is not None:
                a_inserer.append(ligne)                                   # vide, sans valeur certaine : replacée
    i = next(i for i, s in enumerate(reste) if isinstance(s, dict) and _txt(s.get("champ")) == CHAMP_ALIMENTATION)
    nouvelles = reste[:i + 1] + a_inserer + reste[i + 1:]
    if nouvelles == specs:
        return modele, manques
    return dict(modele, description_specs=nouvelles), manques


def migrer_catalogue(catalogue: list) -> tuple[list, bool, dict]:
    """(catalogue, modifié ?, {réf: champs sans valeur})."""
    sortie, change, manques = [], False, {}
    for m in catalogue if isinstance(catalogue, list) else []:
        if not isinstance(m, dict):
            sortie.append(m)
            continue
        neuf, sans = placer_lignes_regulateur(m)
        change = change or neuf is not m
        if sans:
            manques[_txt(m.get("ref"))] = sans
        sortie.append(neuf)
    return sortie, change, manques
