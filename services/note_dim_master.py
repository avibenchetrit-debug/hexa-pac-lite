# -*- coding: utf-8 -*-
"""Lot B (notedim-master, 04/11/2026) — LA NOTE DE DIMENSIONNEMENT DE PAC-LITE = LE DOCUMENT DU MASTER.

Gabarit recopié du Master hexa-simulateur-2 (templates/pdf/note_dimensionnement_pdf.html et ses inclusions, ceux de la
note GIBLAIN ND2026-0009-000106-GI-S001), dans templates/note_dim/. Ce module fabrique le contexte que ce gabarit lit,
avec les mêmes clés que le Master pour le parcours « PAC air-eau seule » (`note_dimensionnement._calcul_paclite`, qui
reprend lui-même le calcul de pac-lite) :

* méthode G × V × ΔT de pac-lite (calcul inchangé, vérifié égal à `calculer_notedim`), température de base de la table
  NF P52-612/CN (décision d'Avi du 04/11 : on garde la table de pac-lite) ;
* titre : NOTE DE PRÉ-DIMENSIONNEMENT avant la visite technique, NOTE DE DIMENSIONNEMENT après (règle du Master) ;
* plage de cohérence 60–130 % (barre sous / cohérent / sur), points de vigilance, méthode, portée et références ;
* pas de section « travaux d'isolation » : pac-lite n'en a pas (la note du Master les masque aussi sans travaux).

AJOUT DEMANDÉ PAR AVI (04/11) : le bloc « Installation proposée » (modèle, quantité, puissance totale, couverture), que
la note du Master ne porte pas (elle reste neutre) — c'est la seule différence de contenu.
"""
from datetime import datetime

from services import dimensionnement_pac as dp

TITRE_DIMENSIONNEMENT = "NOTE DE DIMENSIONNEMENT"
TITRE_PRE_DIMENSIONNEMENT = "NOTE DE PRÉ-DIMENSIONNEMENT"
DISPOSITIF = "BAR-TH-171 + MPR Mono-Geste"          # Master : helpers_categories.PARCOURS_CODES_CEE["pac_aireau_seule"]
PARCOURS_LABEL = "Installation Pompe à Chaleur Air-Eau"
BADGES_REGLEMENTAIRES = ["RT 2012 / RE 2020"]       # Master : SEED_NOTE_DIMENSIONNEMENT["badges_reglementaires"]
RGE = "RGE CertiRénov'"
PHRASE_RESEAU_HT = ("Le réseau de chauffage existant est en HAUTE TEMPÉRATURE (≥ 65 °C). Une pompe à chaleur y "
                    "fonctionnera loin de son rendement nominal : l'économie réelle sera inférieure à l'estimation, "
                    "sauf à reprendre les émetteurs.")
PHRASE_EMETTEURS_INCONNUS = ("Le type d'émetteurs n'a pas pu être caractérisé : la fiche prospect ne distingue ni la "
                             "haute température ni le monotube. À vérifier sur place.")
PHRASE_REGIME_55 = ("Le dimensionnement retient le régime 55 °C : la puissance ci-dessus s'entend à 55 °C d'eau, et "
                    "non à 35 °C.")

SOCIETE = {                                         # identité imprimée par la note pac-lite v5 (inchangée)
    "nom": "Hexa Rénov'", "raison_sociale": "SAS HEXA RÉNOV'",
    "adresse": "58 Rue de la Sablière, 92600 Asnières-sur-Seine",
    "rcs": "RCS Nanterre 845 229 152", "siret": "845 229 152 00028", "tva": "FR 89 845 229 152",
    "rge": RGE, "decennale": "MIC Insurance n° AXE2502159", "decennale_validite": "du 19/03/2026 au 18/03/2027",
    "email": "info@hexa-renov.fr", "telephone": "09 70 70 25 11",
}


def _f(v, d=0.0):
    try:
        if v is None or v == "" or isinstance(v, bool):
            return d
        return float(str(v).replace(" ", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return d


def _fr(x, n=1):
    return f"{x:.{n}f}".replace(".", ",")


def nombre_fr(valeur, max_decimales=4):
    """Filtre `nb` du Master (app.formatage.format_nombre_fr) : virgule, milliers insécables, entier sans décimale."""
    if valeur is None or isinstance(valeur, bool):
        return "—"
    try:
        n = float(valeur)
    except (TypeError, ValueError):
        return "—"
    if n == int(n):
        dec = 0
    else:
        t = f"{abs(n):.{max_decimales}f}".rstrip("0")
        dec = len(t.split(".")[1]) if "." in t else 0
    s = f"{abs(n):,.{dec}f}".replace(",", " ").replace(".", ",")
    return ("−" if n < 0 else "") + s


def lignes_de_formule(texte):
    """Filtre `formule` du Master (pdf_note_dimensionnement.lignes_de_formule) : rôle de chaque ligne."""
    import re
    lignes = str(texte or "").split("\n")
    res = [i for i, l in enumerate(lignes) if re.match(r"^\s+=\s", l)]
    dernier = res[-1] if res else -1
    out = []
    for i, l in enumerate(lignes):
        role = ("commentaire" if l.strip().startswith("#") else "resultat" if i == dernier
                else "valeur" if i in res else "normal")
        out.append({"role": role, "texte": l})
    return out


def date_fr(v):
    if not v:
        return "—"
    try:
        return datetime.fromisoformat(str(v)[:19]).strftime("%d/%m/%Y")
    except ValueError:
        return str(v)


def installer_filtres(env):
    env.filters.setdefault("nb", nombre_fr)
    env.filters.setdefault("formule", lignes_de_formule)
    env.filters.setdefault("date_fr", date_fr)
    env.globals.setdefault("tx", lambda _cle, defaut="": defaut)


def calcul_paclite(prospect, state):
    """Le calcul de pac-lite (identique à `service_devis.calculer_notedim`), avec les clés du Master
    (`notedim_paclite.calculer`) et sa formule en étapes. Température : table NF P52-612/CN de pac-lite."""
    from services.service_devis import _temperature_base_notedim, value
    surface_habitable = _f(value(prospect, "surface_habitable", "surface_logement_m2", default=100), 100)
    sc = _f(value(state, "surface_chauffee", default=0), 0)
    sc_saisie = sc > 0
    if sc <= 0:
        sc = surface_habitable * 0.9
    hsp_brut = _f(value(prospect, "hsp", default=2.5), 2.5)
    h = hsp_brut if hsp_brut > 0 else 2.5
    volume = sc * h
    t = _temperature_base_notedim(prospect)
    t_base = float(t["temperature"])
    delta_t = 20 - t_base
    iso = {k: value(state, k, default=d) for k, d in (("iso_toit", "isole"), ("iso_mur", "isole"),
                                                     ("iso_menuiserie", "double"))}
    coeffs = {"toit": {"tres_bien": 0.00, "bien": 0.10, "isole": 0.20, "peu": 0.35, "non": 0.50},
              "mur": {"tres_bien": 0.00, "bien": 0.15, "isole": 0.30, "peu": 0.55, "non": 0.80},
              "menuiserie": {"double": 0.05, "sur_vitrage": 0.20, "simple": 0.40}}
    libelles = {"tres_bien": "Très bien isolé", "bien": "Bien isolé", "isole": "Isolé", "peu": "Peu isolé",
                "non": "Non isolé", "double": "Double vitrage", "sur_vitrage": "Survitrage", "simple": "Simple vitrage"}
    g_toit = coeffs["toit"].get(iso["iso_toit"], 0.20)
    g_mur = coeffs["mur"].get(iso["iso_mur"], 0.30)
    g_men = coeffs["menuiserie"].get(iso["iso_menuiserie"], 0.05)
    g = min(max(0.75 + g_toit + g_mur + g_men, 0.75), 2.50)
    p_ch = g * volume * delta_t
    service = value(state, "service", default="chauffage_seul")
    ecs = service in ("chauffage_ecs", "chauffage+ecs")
    p_ecs = min(max(p_ch * 0.06, 500), 1000) if ecs else 0
    p_pac_w = p_ch * 1.10 + p_ecs
    kw = int(p_pac_w / 1000 * 10 + 0.5) / 10
    zone = str(t.get("zone") or "").replace("Zone ", "")
    temp_ligne = (f"Zone {zone} (table NF P52-612/CN, {t.get('correction_label')}) : T° de base {_fr(t_base)} °C"
                  if not str(t.get("zone", "")).startswith("Hors") else f"Hors table NF : T° de base {_fr(t_base)} °C")
    details = (
        "# Méthode : NF EN 12831 simplifiée — G × V × ΔT (méthode pac-lite, validée par le délégataire).\n\n"
        f"# Étape 1 — Volume chauffé\nSurface chauffée par la PAC : {_fr(sc)} m²"
        + (f" (sur {_fr(surface_habitable)} m² habitables)" if surface_habitable > 0 else "") + ".\n"
        f"HSP : {_fr(h, 2)} m\nV           = {_fr(volume)} m³\n\n"
        f"# Étape 2 — Écart de température\n{temp_ligne}\nConsigne intérieure : 20 °C\n"
        f"ΔT          = {_fr(delta_t)} °C\n\n"
        f"# Étape 3 — Coefficient G\nG = 0,75 + toiture {_fr(g_toit, 2)} ({libelles.get(iso['iso_toit'])}) + murs "
        f"{_fr(g_mur, 2)} ({libelles.get(iso['iso_mur'])}) + menuiseries {_fr(g_men, 2)} "
        f"({libelles.get(iso['iso_menuiserie'])})\nG           = {_fr(g, 2)} W/m³·°C\n\n"
        f"# Étape 4 — Puissance de chauffage\nP_chauffage = G × V × ΔT = {_fr(p_ch, 0)} W\n\n"
        f"# Étape 5 — Sécurité sur le chauffage, puis ECS\nP_PAC       = P_chauffage × 1,10 + ECS {_fr(p_ecs, 0)} W\n"
        f"            = {_fr(p_pac_w, 0)} W ≈ {_fr(kw)} kW")
    return {
        "methode": "g_v_delta_t", "calculable": True,
        "surface_habitable_m2": surface_habitable, "surface_chauffee_m2": round(sc, 1),
        "surface_chauffee_de_la_fiche": sc_saisie, "hsp_m": h, "hsp_renseignee": hsp_brut > 0,
        "volume_chauffe_m3": round(volume, 1), "altitude_m": t.get("altitude"),
        "zone_climatique": f"Zone {zone}" if zone and not zone.startswith("Hors") else (t.get("zone") or "—"),
        "temperature_base_exterieure": t_base, "temperature_consigne": 20.0, "delta_t_celsius": delta_t,
        "coefficient_g": round(g, 2), "g_base": 0.75, "g_ajuste": round(g, 2),
        # arrondis de pac-lite (calculer_notedim : int(x + 0,5)), pas l'arrondi au pair de round()
        "p_chauffage_w": int(p_ch + 0.5), "p_ecs_w": int(p_ecs + 0.5), "p_total_brute_w": int(p_ch + p_ecs + 0.5),
        "facteur_securite": 1.1, "p_pac_recommandee_w": int(p_pac_w + 0.5), "p_pac_recommandee_kw": kw,
        "details_formule": details, "formule_texte": details, "questionnaire": iso, "methode_paclite": True,
        "mention_deux_zones": t.get("mention_deux_zones") or "", "alertes": [], "controles_classeur": [],
    }


def construire_note(prospect, state, catalogue, admin=None):
    """Le dict `note` du gabarit du Master, pour une PAC air-eau seule de pac-lite."""
    from services.service_devis import find_modele, quantite_pac, select_default_modele, value
    p = prospect or {}
    c = calcul_paclite(p, state or {})
    vt = bool(p.get("vt_validee"))
    emetteur = str(p.get("type_emetteurs") or "").strip()
    regime = "35" if emetteur == "plancher_chauffant" else "55"
    fondement = ("Calcul selon la méthode NF EN 12831 simplifiée (G × V × ΔT) de pac-lite, validée par le délégataire : "
                 "G déduit du questionnaire d'isolation du logement.")
    niveau = {
        "niveau": "dimensionnement" if vt else "pre_dimensionnement",
        "titre": TITRE_DIMENSIONNEMENT if vt else TITRE_PRE_DIMENSIONNEMENT,
        "methode": "g_v_delta_t",
        "methode_texte": "NF EN 12831 simplifiée — G × V × ΔT (méthode pac-lite).",
        "source_coefficient_g": "questionnaire d'isolation (méthode pac-lite)",
        "avec_classeur": False,
        "fondement": fondement,
        "perimetre": "Visite technique réalisée — le logement a été vu" if vt else "En attente de la visite technique",
        "perimetre_le": p.get("vt_validee_le") or p.get("date_vt") if vt else None,
        "reserve": "" if vt else ("Le périmètre des travaux n'est pas encore arrêté : cette puissance est un ORDRE DE "
                                   "GRANDEUR, appelé à changer si les travaux retenus changent."),
    }
    vigilance = []
    if emetteur == "radiateurs_fonte":
        vigilance.append(PHRASE_RESEAU_HT)
    elif not emetteur:
        vigilance.append(PHRASE_EMETTEURS_INCONNUS)
    if regime == "55":
        vigilance.append(PHRASE_REGIME_55)
    habitable, chauffee = _f(p.get("surface_logement_m2")), _f(value(state or {}, "surface_chauffee", default=0))
    if habitable > 0 and chauffee > habitable:
        vigilance.append(f"Surface chauffée supérieure à la surface habitable : vérifie la saisie (surface chauffée "
                         f"{nombre_fr(chauffee)} m² > surface habitable {nombre_fr(habitable)} m²).")
    if c.get("mention_deux_zones"):
        vigilance.append(f"Température de base : {c['mention_deux_zones']}.")

    # Installation proposée (ajout pac-lite) : modèle × quantité, puissance retenue, couverture
    modele = find_modele(catalogue, value(state or {}, "modele_pac_id", "modele_pac")) or select_default_modele(p, catalogue)
    q = quantite_pac(state or {})
    besoin = c["p_pac_recommandee_kw"]
    installation = None
    t_req, _orig = dp.temperature_requise(p, admin or {})
    if modele:
        unitaire, origine = dp.puissance_retenue(modele)
        total = unitaire * q
        installation = {
            "modele": (f"{q} × " if q > 1 else "") + str(modele.get("nom") or modele.get("ref"))
                      + (" (en cascade)" if q > 1 else ""),
            "quantite": q, "unitaire_kw": unitaire, "total_kw": total, "origine": origine,
            "mention": "" if origine == dp.ORIGINE_M7_55 else dp.MENTION_35,
            "coherence": dp.coherence(total, besoin) or {},
            "temp_requise": t_req, "temp_max": dp.temp_max(modele),
            "alerte_temperature": dp.alerte_temperature(modele, t_req, emetteur),
        }
        if installation["alerte_temperature"]:
            vigilance.append(installation["alerte_temperature"] + ".")
    plage = dp.plage(besoin) or {}
    if plage:
        plage.update(temperature_base_c=c["temperature_base_exterieure"], regime=regime)
    return {
        "applicable": True, "niveau": niveau, "perimetre": {"fige": vt, "declencheur": "vt" if vt else None},
        "regime": regime, "rattachement": {}, "plage_coherence": plage, "dispositif": DISPOSITIF,
        "calcul": c, "points_de_vigilance": vigilance, "alertes": [], "installation": installation,
        "ecs_integree": c["p_ecs_w"] > 0, "deperditions": {}, "travaux_non_deduits": False,
        "seuils": {"cop_minimum": 3.0, "scop_minimum": 3.4},
    }


def contexte(prospect, state, catalogue, admin=None, *, reference, maintenant=None, document=None):
    """Le contexte complet du gabarit (mêmes clés que `pdf_note_dimensionnement.generer_pdf_note_dim` du Master)."""
    p = prospect or {}
    now = maintenant or datetime.now()
    note = construire_note(p, state, catalogue, admin)
    if document:
        note["rattachement"] = {"document": document}
    type_log = {"maison": "Maison", "appartement": "Appartement"}.get(str(p.get("type_logement") or "").lower(),
                                                                        p.get("type_logement") or "Maison")
    return {
        "prospect": {
            "numero": p.get("numero", ""), "reference_dossier": p.get("numero_dossier") or p.get("numero", ""),
            "civilite": p.get("civilite", "") or "", "nom": str(p.get("nom", "") or "").upper(),
            "prenom": p.get("prenom", "") or "", "telephone": p.get("telephone", "") or "—",
            "email": str(p.get("email", "") or "—").lower(),
            "adresse": p.get("adresse_chantier") or p.get("adresse") or "—",
            "code_postal": p.get("code_postal_chantier") or p.get("cp_chantier") or "",
            "ville": p.get("ville_chantier") or p.get("ville") or "",
            "surface_habitable_m2": _f(p.get("surface_logement_m2") or p.get("surface_habitable")),
            "zone_climatique": note["calcul"].get("zone_climatique") or "—",
            "dpe": {"classe": p.get("dpe_connu") or p.get("classe_dpe") or None},
            "type_logement": type_log,
        },
        "note": note,
        "reference": reference,
        "parcours_label": PARCOURS_LABEL,
        "date_emission": now.strftime("%d/%m/%Y"),
        "datetime_emission": now.strftime("%d/%m/%Y à %H:%M"),
        "societe": SOCIETE,
        "badges_conformite": ["Estimation par coefficient volumique G", *BADGES_REGLEMENTAIRES, DISPOSITIF, RGE],
        "inter_fontface_css": "",
    }
