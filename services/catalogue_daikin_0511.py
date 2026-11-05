# -*- coding: utf-8 -*-
"""Fiches DAIKIN du 05/11/2026 (décisions d'Avi) — écriture UNIQUE au démarrage (marque `maj_daikin_0511` par modèle).

* ALTHERMA 4H (10 mono, 8 TRI, 10 TRI, 12 TRI, 14 TRI) : fiche technique refaite avec EXACTEMENT les libellés, l'ordre
  et le format de la 8 kW mono saisie par Avi ; valeurs du référentiel Daikin du CRM
  (hexa-simulateur-2, app/referentiels/pac_daikin_donnees_20261105.json : Keymark, EPREL, catalogue ECPEN26-500,
  manuel 4P773385-1C) ; appoint 4,5 kW mono / 9 kW tri ; valeur absente des sources = ligne vide (Avi la remplit).
  « Référence EPREL » et « Numéro d'agrément » : la valeur déjà en base est reprise telle quelle, jamais écrite ici.
* ALTHERMA 4H 8 kW mono (fiche d'Avi) : seulement −7 °C / 55 °C (7,62 / 6,60), temp. max (70) et dimensions du groupe
  extérieur (1123 × 1330 × 604).
* Les 6 ALTHERMA 4H : puissance de dimensionnement à −7 °C / 55 °C = Pdh Keymark (validée par Avi) et température de
  départ max Daikin (70 °C pour 8 et 10 kW, 75 °C pour 12 et 14 kW).
* ALTHERMA 3H HT 16 mono : seulement la ligne « Référence » (ETBH16EF6V7 / EPRA16DAV37, fiche EPREL 1623957).
Aucun prix, aucun autre champ n'est touché.
"""
MARQUE = "maj_daikin_0511"
LIGNES_INTOUCHABLES = ("Référence EPREL", "Numéro d'agrément")
SOURCE_M7_55 = ("Heat Pump Keymark (DIN CERTCO) : Pdh à Tj = −7 °C, application 55 °C, climat moyen (EN 14825) — "
                "validée par Avi le 05/11/2026")

FICHES_4H = {
'DAI-ALTHERMA-4H-R290-10': [
    ('Marque', 'DAIKIN'),
    ('Gamme', 'ALTHERMA 4 H W'),
    ('Référence', 'EPSK10AV3 / EPBX10A4V'),
    ('Technologie', 'PAC air/eau haute température monobloc'),
    ('Usage', 'Chauffage seul'),
    ('Alimentation', 'Monophasé'),
    ('Classe du régulateur (ErP)', 'VI'),
    ("Contribution à l'efficacité saisonnière (%)", '4'),
    ('Temp. max de départ (°C)', '70'),
    ('Fluide frigorigène', 'R290'),
    ('Classe énergétique chauffage 35°C / 55°C', 'A+++ / A+++'),
    ('Puissance thermique nominale +7/35°C -7°C/55°C (kW)', '8,11 / 7,40'),
    ('ETAS chauffage 35°C / 55°C (%)', '203 / 158'),
    ('SCOP 35°C / 55°C', '5,15 / 4,02'),
    ('COP +7°C/35°C', '4,94'),
    ('Puissance appoint électrique (kW)', '4,50'),
    ('Puissance acoustique ext. (dB(A))', '47'),
    ('Pression sonore ext. à 5 m (dB(A))', '25'),
    ('Poids module intérieur à vide (kg)', '33'),
    ('Poids module ext. en fonction (kg)', '174'),
    ('Dimensions groupe extérieur (HxLxP) (mm)', '1123 × 1330 × 604'),
    ('Dimensions module intérieur (HxLxP) (mm)', '840 x 440 x 390'),
    ('Référence EPREL', ''),
    ("Numéro d'agrément", '')
],
'DAI-ALTHERMA-4H-R290-8 TRI': [
    ('Marque', 'DAIKIN'),
    ('Gamme', 'ALTHERMA 4 H W'),
    ('Référence', 'EPSK08AW1 / EPBX10A9W'),
    ('Technologie', 'PAC air/eau haute température monobloc'),
    ('Usage', 'Chauffage seul'),
    ('Alimentation', 'Triphasé'),
    ('Classe du régulateur (ErP)', 'VI'),
    ("Contribution à l'efficacité saisonnière (%)", '4'),
    ('Temp. max de départ (°C)', '70'),
    ('Fluide frigorigène', 'R290'),
    ('Classe énergétique chauffage 35°C / 55°C', 'A+++ / A+++'),
    ('Puissance thermique nominale +7/35°C -7°C/55°C (kW)', '7,62 / 6,60'),
    ('ETAS chauffage 35°C / 55°C (%)', '202 / 155'),
    ('SCOP 35°C / 55°C', '5,14 / 3,96'),
    ('COP +7°C/35°C', '5,01'),
    ('Puissance appoint électrique (kW)', '9,00'),
    ('Puissance acoustique ext. (dB(A))', '45'),
    ('Pression sonore ext. à 5 m (dB(A))', '23'),
    ('Poids module intérieur à vide (kg)', '33'),
    ('Poids module ext. en fonction (kg)', '178'),
    ('Dimensions groupe extérieur (HxLxP) (mm)', '1123 × 1330 × 604'),
    ('Dimensions module intérieur (HxLxP) (mm)', '840 x 440 x 390'),
    ('Référence EPREL', ''),
    ("Numéro d'agrément", '')
],
'DAI-ALTHERMA-4H-R290-10 TRI': [
    ('Marque', 'DAIKIN'),
    ('Gamme', 'ALTHERMA 4 H W'),
    ('Référence', 'EPSK10AW1 / EPBX10A9W'),
    ('Technologie', 'PAC air/eau haute température monobloc'),
    ('Usage', 'Chauffage seul'),
    ('Alimentation', 'Triphasé'),
    ('Classe du régulateur (ErP)', ''),
    ("Contribution à l'efficacité saisonnière (%)", ''),
    ('Temp. max de départ (°C)', '70'),
    ('Fluide frigorigène', 'R290'),
    ('Classe énergétique chauffage 35°C / 55°C', 'A+++ / A+++'),
    ('Puissance thermique nominale +7/35°C -7°C/55°C (kW)', '8,11 / 7,40'),
    ('ETAS chauffage 35°C / 55°C (%)', '203 / 157'),
    ('SCOP 35°C / 55°C', '5,14 / 4,02'),
    ('COP +7°C/35°C', '4,94'),
    ('Puissance appoint électrique (kW)', '9,00'),
    ('Puissance acoustique ext. (dB(A))', '47'),
    ('Pression sonore ext. à 5 m (dB(A))', ''),
    ('Poids module intérieur à vide (kg)', '33'),
    ('Poids module ext. en fonction (kg)', '178'),
    ('Dimensions groupe extérieur (HxLxP) (mm)', '1123 × 1330 × 604'),
    ('Dimensions module intérieur (HxLxP) (mm)', '840 x 440 x 390'),
    ('Référence EPREL', ''),
    ("Numéro d'agrément", '')
],
'DAI-ALTHERMA-4H-R290-12-TRI': [
    ('Marque', 'DAIKIN'),
    ('Gamme', 'ALTHERMA 4 H W'),
    ('Référence', 'EPSK12AW1 / EPBX14A9W'),
    ('Technologie', 'PAC air/eau haute température monobloc'),
    ('Usage', 'Chauffage seul'),
    ('Alimentation', 'Triphasé'),
    ('Classe du régulateur (ErP)', ''),
    ("Contribution à l'efficacité saisonnière (%)", ''),
    ('Temp. max de départ (°C)', '75'),
    ('Fluide frigorigène', 'R290'),
    ('Classe énergétique chauffage 35°C / 55°C', 'A+++ / A+++'),
    ('Puissance thermique nominale +7/35°C -7°C/55°C (kW)', '10,20 / 9,40'),
    ('ETAS chauffage 35°C / 55°C (%)', '203 / 159'),
    ('SCOP 35°C / 55°C', '5,14 / 4,04'),
    ('COP +7°C/35°C', '5,50'),
    ('Puissance appoint électrique (kW)', '9,00'),
    ('Puissance acoustique ext. (dB(A))', '52'),
    ('Pression sonore ext. à 5 m (dB(A))', ''),
    ('Poids module intérieur à vide (kg)', '34'),
    ('Poids module ext. en fonction (kg)', '191'),
    ('Dimensions groupe extérieur (HxLxP) (mm)', '1123 × 1330 × 604'),
    ('Dimensions module intérieur (HxLxP) (mm)', '840 x 440 x 390'),
    ('Référence EPREL', ''),
    ("Numéro d'agrément", '')
],
'DAI-ALTHERMA-4H-R290-14-TRI': [
    ('Marque', 'DAIKIN'),
    ('Gamme', 'ALTHERMA 4 H W'),
    ('Référence', 'EPSK14AW1 / EPBX14A9W'),
    ('Technologie', 'PAC air/eau haute température monobloc'),
    ('Usage', 'Chauffage seul'),
    ('Alimentation', 'Triphasé'),
    ('Classe du régulateur (ErP)', 'VI'),
    ("Contribution à l'efficacité saisonnière (%)", '4'),
    ('Temp. max de départ (°C)', '75'),
    ('Fluide frigorigène', 'R290'),
    ('Classe énergétique chauffage 35°C / 55°C', 'A+++ / A+++'),
    ('Puissance thermique nominale +7/35°C -7°C/55°C (kW)', '10,20 / 12,40'),
    ('ETAS chauffage 35°C / 55°C (%)', '195 / 150'),
    ('SCOP 35°C / 55°C', '4,96 / 3,84'),
    ('COP +7°C/35°C', '5,50'),
    ('Puissance appoint électrique (kW)', '9,00'),
    ('Puissance acoustique ext. (dB(A))', '52'),
    ('Pression sonore ext. à 5 m (dB(A))', '30'),
    ('Poids module intérieur à vide (kg)', '34'),
    ('Poids module ext. en fonction (kg)', '191'),
    ('Dimensions groupe extérieur (HxLxP) (mm)', '1123 × 1330 × 604'),
    ('Dimensions module intérieur (HxLxP) (mm)', '840 x 440 x 390'),
    ('Référence EPREL', ''),
    ("Numéro d'agrément", '')
],
}

MODELE_8_MONO = "DAI-ALTHERMA-4H-R290-8"
CORRECTIONS_8_MONO = {
    "Puissance thermique nominale +7/35°C -7°C/55°C (kW)": "7,62 / 6,60",
    "Temp. max de départ (°C)": "70",
    "Dimensions groupe extérieur (HxLxP) (mm)": "1123 × 1330 × 604",
}
DIMENSIONNEMENT_4H = {          # réf : (puissance à −7 °C / 55 °C validée, température de départ max)
    "DAI-ALTHERMA-4H-R290-8": (6.6, 70), "DAI-ALTHERMA-4H-R290-10": (7.4, 70),
    "DAI-ALTHERMA-4H-R290-8 TRI": (6.6, 70), "DAI-ALTHERMA-4H-R290-10 TRI": (7.4, 70),
    "DAI-ALTHERMA-4H-R290-12-TRI": (9.4, 75), "DAI-ALTHERMA-4H-R290-14-TRI": (12.4, 75),
}
REFERENCE_3HHT_16_MONO = ("DAI-ALTHERMA-3HHT-R32-16", "ETBH16EF6V7 / EPRA16DAV37")


def _specs(m):
    return [dict(s) for s in (m.get("description_specs") or []) if isinstance(s, dict)]


def migrer_catalogue(catalogue):
    """(catalogue, changé). Idempotent : un modèle déjà marqué n'est plus jamais réécrit."""
    change = False
    for m in catalogue if isinstance(catalogue, list) else []:
        if not isinstance(m, dict) or m.get(MARQUE):
            continue
        ref = str(m.get("ref") or "").strip()
        touche = False
        if ref in FICHES_4H:
            avant = {s.get("champ"): s.get("valeur", "") for s in _specs(m)}
            m["description_specs"] = [{"champ": c, "valeur": (avant.get(c, "") if c in LIGNES_INTOUCHABLES else v)}
                                      for c, v in FICHES_4H[ref]]
            touche = True
        if ref == MODELE_8_MONO:
            specs = _specs(m)
            for s in specs:
                if s.get("champ") in CORRECTIONS_8_MONO:
                    s["valeur"] = CORRECTIONS_8_MONO[s["champ"]]
            m["description_specs"] = specs
            touche = True
        if ref in DIMENSIONNEMENT_4H:
            kw, tmax = DIMENSIONNEMENT_4H[ref]
            m.update(puissance_m7_55_kw=kw, puissance_m7_55_valide=True, puissance_m7_55_source=SOURCE_M7_55,
                     temp_max_depart_c=tmax)
            touche = True
        if ref == REFERENCE_3HHT_16_MONO[0]:
            specs = _specs(m)
            for s in specs:
                if s.get("champ") == "Référence":
                    s["valeur"] = REFERENCE_3HHT_16_MONO[1]
            m["description_specs"] = specs
            touche = True
        if touche:
            m[MARQUE] = True
            change = True
    return catalogue, change
