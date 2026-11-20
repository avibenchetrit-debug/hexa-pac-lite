"""20/11/2026 (Avi — tableau validé) : les descriptifs PAC air-eau du devis pac-lite reprennent EXACTEMENT les lignes du
catalogue du CRM Master (lot PAC air-eau), dans le même ordre. En gras (comme avant) : la ligne du régulateur
(« Installation et paramétrage du régulateur (classe …) ») et la ligne de dépose quand l'énergie est connue."""
from __future__ import annotations

import re
from html import unescape

#: Le catalogue du Master (lot « pac_aireau », production du 20/11/2026).
MASTER = {
    "systeme": [
        "Installation et mise en service d'une pompe à chaleur air-eau"
    ],
    "amenagements": [
        "Mise en place des unités intérieure et extérieure selon configuration",
        "Liaisons hydrauliques et raccordement au réseau de chauffage existant",
        "Liaisons frigorifiques selon technologie de la pompe à chaleur",
        "Câblage électrique, protections adaptées et dispositif de coupure",
        "Épreuve sous azote, contrôle d’étanchéité et tirage au vide si liaison frigorifique",
        "Remplissage, purge et contrôle d’étanchéité du circuit hydraulique",
        "Mise en service, essais et programmation initiale de l’installation",
        "Contrôle de conformité de l'installation électrique (NF C 15-100)",
        "Explications de fonctionnement et conseils d'utilisation au client",
        "Évacuation des déchets en filière agréée"
    ],
    "finition": [
        "Vannes d’arrêt et organes d’isolement",
        "Disconnecteur de remplissage",
        "Pot à boue magnétique",
        "Calorifugeage des réseaux hydrauliques accessibles",
        "Ballon tampon 50 L (réf. STOV20504NW), vase d’expansion 18 L et console de sécurité (manomètre, purgeur, soupape)",
        "Circulateur additionnel selon configuration hydraulique",
        "Vanne d'équilibrage du réseau de chauffage",
        "Supports antivibratiles adaptés : socles type Rubberfoot sur dalle ou support plat existant, sinon équerres murales",
        "Réglage et optimisation des paramètres de fonctionnement"
    ],
    "inclus": [
        "Protection et sécurisation des zones d’intervention",
        "Création ou adaptation des passages techniques",
        "Reprises localisées d'étanchéité et de calfeutrement des traversées de murs",
        "Dépose et évacuation de l'ancien générateur de chauffage (chaudière fioul, gaz ou autre)",
        "Neutralisation et bouchonnage de l'alimentation en combustible (gaz ou fioul) de la chaudière déposée"
    ],
    "non_inclus": [
        "Renforcement ou mise en conformité complète de l’installation électrique",
        "Modification des émetteurs ou réseaux hors descriptif",
        "Travaux de maçonnerie ou de couverture lourde",
        "Prestations de décoration et reprises complètes de finition",
        "Habillage ou coffrage acoustique de l'unité extérieure (sur devis)",
        "Neutralisation, dégazage ou enlèvement de la cuve à fioul (en option)",
        "Désembouage du réseau de chauffage (en option)"
    ]
}


def _bloc(src: str, titre: str) -> list[str]:
    m = re.search(r'<div class="specs-block-title">' + re.escape(titre) + r'</div><ul class="specs-list">(.*?)</ul>', src, re.S)
    assert m, titre
    return [unescape(re.sub(r"<[^>]+>|\{%.*?%\}|\{\{.*?\}\}", "", x)).strip()
            for x in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S)]


def test_lignes_du_master_dans_le_gabarit():
    src = open("templates/devis_pac_template.html", encoding="utf-8").read()
    i = src.index("Installation et mise en service d'une pompe à chaleur air-eau")
    bloc = src[src.rindex('<div class="specs">', 0, i):]
    sys = [x for x in _bloc(bloc, "Système mis en œuvre") if x]
    assert sys == MASTER["systeme"][:1]                      # + la ligne du régulateur (dynamique, en gras)
    assert 'data-ace="regulateur"' in bloc.split("Aménagements")[0]
    assert _bloc(bloc, "Aménagements et sujétions") == MASTER["amenagements"]
    assert _bloc(bloc, "Système de finition") == MASTER["finition"]
    j = src.index('{% else %}<div class="specs"><div class="specs-block"><div class="specs-block-title">Travaux induits</div>', i)
    ind = src[j:]
    inclus = _bloc(ind, "Travaux induits")
    k = next(n for n, x in enumerate(MASTER["inclus"]) if x.startswith("Dépose et évacuation"))
    assert inclus[:k] == MASTER["inclus"][:k] and inclus[k + 1:] == MASTER["inclus"][k + 1:]
    assert 'data-ace="depose"' in ind.split("Non inclus")[0]   # dépose en gras quand l'énergie est connue
    assert _bloc(ind, "Non inclus") == MASTER["non_inclus"]


def test_depose_sans_energie_ligne_du_master():
    from services.service_devis import DEPOSE_SANS_ENERGIE
    assert DEPOSE_SANS_ENERGIE in MASTER["inclus"]


def test_rectificative_d_une_facture_d_avant_garde_ses_lignes():
    """Une facture émise avant le 20/11/2026 (PDF qui porte l'ancienne ligne) : sa rectificative reprend les lignes
    d'origine — elle doit rester identique à l'originale."""
    import main
    src = open("templates/devis_pac_template.html", encoding="utf-8").read()
    assert src.count("{% if descriptifs_avant_2011 %}") == 2
    vieux = src.split("{% if descriptifs_avant_2011 %}")[2].split("{% else %}")[0]
    assert main.SIGNATURE_DESCRIPTIFS_AVANT_2011 in vieux
    assert main._descriptifs_avant_2011({"file": ""}) is False
