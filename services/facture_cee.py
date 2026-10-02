# -*- coding: utf-8 -*-
"""Lot 11 — facture CEE au délégataire (ACE ; ECAIR pour PICOTY), série FA-CEE-AAAA-NNNN, distincte des factures
client. Mise en page identique à FA-CEE-2026-0001 (émise hors application, d'où le premier numéro 0002).

Montants (par opération, puis × quote-part) :
  valorisation = volume précaire (MWhc) × prix précaire + volume classique (MWhc) × prix classique
  prime bénéficiaire HT = prime CEE du devis signé — hors champ de la TVA (BOI-TVA-BASE-10-10-40 20120912 n°10 et 20)
  commission HT = valorisation − prime — TVA 20 % (BOI-TVA-BASE-10-10-10-20121115 n°210)
Ce module ne lit ni n'écrit aucun fichier : il calcule et met en forme."""
from datetime import date, datetime, timedelta

SERIE = "FA-CEE"
# Factures de la série déjà émises HORS application (FA-CEE-2026-0001, ACE, GALEA) : la numérotation continue après.
DEJA_EMISES = {"2026": 1}

EMETTEUR = {
    "nom": "HEXA RÉNOV'",
    "lignes": ["SAS à associé unique au capital de 1 000,00 €", "Siège social et adresse de facturation :",
               "58 rue de la Sablière, 92600 Asnières-sur-Seine", "RCS Nanterre 845 229 152 · SIRET 845 229 152 00028",
               "N° TVA intracommunautaire : FR89 845 229 152", "info@hexa-renov.fr · 09 70 70 25 11"],
}
RIB = {"titulaire": "HEXA RENOV'", "iban": "FR76 2823 3000 0177 4777 4829 976", "bic": "REVOFRP2",
       "banque": "Revolut Bank UAB — 10 avenue Kléber, 75116 Paris"}
PIED = ("SAS HEXA RÉNOV' au capital de 1 000,00 € · 58 rue de la Sablière, 92600 Asnières-sur-Seine · RCS Nanterre "
        "845 229 152 · SIRET 845 229 152 00028 · TVA FR89 845 229 152")
MENTION_TVA = ["La PRIME BÉNÉFICIAIRE est nette de taxe (exonération de TVA selon BOI-TVA-BASE-10-10-40 20120912 n°10 et 20).",
               "COMMISSION assujettie à la TVA selon BOI-TVA-BASE-10-10-10-20121115 n°210."]
CATEGORIE = "catégorie de l'opération : prestation de services"
FICHE = "BAR-TH-171"
FICHE_LIBELLE = "Pompe à chaleur de type air/eau"
TAUX_TVA_COMMISSION = 20.0
ECHEANCE_JOURS = 7

# Coordonnées de facturation par délégataire (Admin → CEE → Délégataires, modifiables). Quote-parts : « 60/40 » =
# acompte 60 % puis solde 40 % ; « 100 » = une seule facture.
FACTURATION_DEFAUT = {
    "ACE": {"raison_sociale": "ACE ENERGIE", "forme": "SAS", "nom_commercial": "", "adresse": "24 rue Marbeuf, 75008 Paris",
            "immatriculation": "SIREN 848 595 336", "tva": "FR68 848 595 336", "mandataire": "",
            "contrat": "HXR-CTT00002", "quote_parts": "60/40", "quote_parts_express": "", "mention_express": ""},
    "PICOTY": {"raison_sociale": "MRA GROUPE", "forme": "SAS", "nom_commercial": "ECAIR",
               "adresse": "5 rue Pleyel, 93200 Saint-Denis", "immatriculation": "RCS Bobigny 952 862 670",
               "tva": "FR59 952 862 670", "mandataire": "Mandataire de PICOTY",
               "contrat": "Contrat de valorisation CEE ECAIR", "quote_parts": "100", "quote_parts_express": "40/60",
               "mention_express": "Option Traitement Express : 200 € HT par dossier, facturée par ECAIR"},
}
CHAMPS_FACTURATION = tuple(FACTURATION_DEFAUT["ACE"])
CHAMPS_DESTINATAIRE = ("raison_sociale", "forme", "nom_commercial", "adresse", "immatriculation", "tva", "mandataire")

TITRES = {"acompte": "FACTURE D'ACOMPTE", "solde": "FACTURE DE SOLDE", "totalite": "FACTURE"}
TYPES = tuple(TITRES)


def cle_delegataire(nom) -> str:
    n = str(nom or "").strip().upper()
    return "PICOTY" if n.startswith("PICOTY") else ("ACE" if n.startswith("ACE") else n)


def facturation_par_defaut(nom) -> dict:
    return dict(FACTURATION_DEFAUT.get(cle_delegataire(nom)) or {k: "" for k in CHAMPS_FACTURATION})


def parts(texte) -> list:
    """« 60/40 » -> [60.0, 40.0] ; « 100 » -> [100.0] ; illisible -> [100.0]."""
    out = []
    for p in str(texte or "").replace(",", ".").replace("%", "").split("/"):
        try:
            v = float(p.strip())
        except ValueError:
            return [100.0]
        if v > 0:
            out.append(v)
    return out or [100.0]


def type_et_pourcentage(quote_parts, deja: list) -> tuple:
    """Type et % proposés : 1re facture = acompte (ou totalité si une seule part) ; ensuite le solde restant.
    `deja` = factures déjà émises pour l'opération (types et %)."""
    p = parts(quote_parts)
    if len(p) == 1:
        return "totalite", p[0]
    acomptes = [float(f.get("quote_part") or 0) for f in deja if f.get("type") == "acompte"]
    if not acomptes:
        return "acompte", p[0]
    return "solde", round(max(0.0, 100.0 - sum(acomptes)), 2)


def _f(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(" ", "").replace(" ", "").replace(" ", "").replace("€", "").replace(",", "."))


def calculer(f: dict) -> dict:
    """Montants de la facture. Arrondis au centime à chaque ligne, comme sur FA-CEE-2026-0001."""
    pct = _f(f.get("quote_part"))
    vol_p, vol_c = _f(f.get("volume_precaire_mwh")), _f(f.get("volume_classique_mwh"))
    prix_p, prix_c = _f(f.get("prix_precaire")), _f(f.get("prix_classique"))
    prime_op = round(_f(f.get("prime_operation")), 2)
    valorisation = round(vol_p * prix_p + vol_c * prix_c, 2)
    if str(f.get("commission_operation") if f.get("commission_operation") is not None else "").strip() == "":
        commission_op = round(valorisation - prime_op, 2)
    else:
        commission_op = round(_f(f.get("commission_operation")), 2)
    taux = _f(f.get("taux_tva")) if str(f.get("taux_tva") or "").strip() else TAUX_TVA_COMMISSION
    prime_ht = round(prime_op * pct / 100, 2)
    commission_ht = round(commission_op * pct / 100, 2)
    tva = round(commission_ht * taux / 100, 2)
    total_ht = round(prime_ht + commission_ht, 2)
    return {"quote_part": pct, "valorisation": valorisation, "prime_operation": prime_op, "commission_operation": commission_op,
            "prime_ht": prime_ht, "commission_ht": commission_ht, "taux_tva": taux, "tva_commission": tva,
            "prime_ttc": prime_ht, "commission_ttc": round(commission_ht + tva, 2),
            "total_ht": total_ht, "total_tva": tva, "total_ttc": round(total_ht + tva, 2), "net_a_payer": round(total_ht + tva, 2)}


def erreurs(f: dict, pour_emettre: bool) -> list:
    """Contrôles avant aperçu / émission (messages lisibles)."""
    out = []
    try:
        c = calculer(f)
    except (TypeError, ValueError):
        return ["Un montant, un volume ou un pourcentage n'est pas un nombre."]
    if f.get("type") not in TYPES:
        out.append("Type de facture inconnu (acompte, solde ou totalité).")
    if not 0 < c["quote_part"] <= 100:
        out.append("La quote-part doit être comprise entre 0 et 100 %.")
    if c["prime_operation"] < 0 or c["commission_operation"] < 0:
        out.append("La prime et la commission ne peuvent pas être négatives (valorisation inférieure à la prime ?).")
    if pour_emettre:
        for k, lib in (("ref_appel", "la référence de l'appel à facturation"), ("ref_operation", "la référence de l'opération"),
                       ("date_facture", "la date de facture"), ("beneficiaire", "le bénéficiaire")):
            if not str(f.get(k) or "").strip():
                out.append(f"Renseignez {lib}.")
        if not str((f.get("destinataire") or {}).get("raison_sociale") or "").strip():
            out.append("Renseignez la raison sociale du destinataire.")
        if c["total_ttc"] <= 0:
            out.append("Le montant de la facture est nul.")
    return out


def date_iso(v) -> date:
    try:
        return datetime.strptime(str(v or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def echeance(date_facture, jours=ECHEANCE_JOURS) -> str:
    return (date_iso(date_facture) + timedelta(days=int(jours or ECHEANCE_JOURS))).isoformat()


def euros(v) -> str:
    """4218 -> « 4 218,00 € » (espace insécable)."""
    return f"{_f(v):,.2f}".replace(",", " ").replace(".", ",") + " €"


def pourcent(v, decimales=0) -> str:
    v = _f(v)
    s = f"{v:.{decimales}f}" if decimales or v != int(v) else str(int(v))
    if not decimales and v != int(v):
        s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",") + " %"


def mwh(v) -> str:
    return f"{_f(v):,.3f}".replace(",", " ").replace(".", ",")


def prix(v) -> str:
    return f"{_f(v):,.2f}".replace(",", " ").replace(".", ",")


def contexte(f: dict, numero_facture: str) -> dict:
    """Contexte du modèle templates/facture_cee.html (numero_facture vide = APERÇU)."""
    c = calculer(f)
    t = f.get("type") if f.get("type") in TYPES else "totalite"
    pct = pourcent(c["quote_part"])
    dest = dict(f.get("destinataire") or {})
    op = str(f.get("ref_operation") or "").strip()
    if t == "acompte":
        nature, sous = f"Acompte de {pct} sur opération CEE — {CATEGORIE}", "Acompte sur"
    elif t == "solde":
        nature, sous = f"Solde de {pct} sur opération CEE — {CATEGORIE}", "Solde sur"
    else:
        nature, sous = f"Totalité ({pct}) de l'opération CEE — {CATEGORIE}", ""
    lib_prime = (f"{sous} prime CEE" if sous else "Prime CEE") + (f" — opération {op}" if op else "")
    lib_comm = (f"{sous} commission" if sous else "Commission") + (f" — opération {op}" if op else "")
    vol_p, vol_c = _f(f.get("volume_precaire_mwh")), _f(f.get("volume_classique_mwh"))
    volume = f"{mwh(vol_p)} MWh cumac précaire · {mwh(vol_c)} MWh cumac classique"
    if vol_p or not vol_c:
        volume += f" · Prix unitaire précaire {prix(f.get('prix_precaire'))} €/MWhc"
    if vol_c:
        volume += f" · Prix unitaire classique {prix(f.get('prix_classique'))} €/MWhc"
    ref_appel = str(f.get("ref_appel") or "").strip()
    client = dest.get("nom_commercial") or dest.get("raison_sociale") or ""
    jours = int(_f(f.get("echeance_jours")) or ECHEANCE_JOURS)
    lignes_client = []
    if dest.get("forme") or dest.get("nom_commercial"):
        lignes_client.append(" — ".join(x for x in (dest.get("forme"), f"nom commercial {dest['nom_commercial']}"
                                                   if dest.get("nom_commercial") else "") if x))
    for k in ("adresse", "immatriculation"):
        if dest.get(k):
            lignes_client.append(dest[k])
    if dest.get("tva"):
        lignes_client.append(f"N° TVA intracommunautaire : {dest['tva']}")
    if dest.get("mandataire"):
        lignes_client.append(dest["mandataire"])
    numero_aff = numero_facture or "APERÇU — sans numéro"
    beneficiaire = " — ".join(x for x in (str(f.get("beneficiaire") or "").strip(), str(f.get("adresse_travaux") or "").strip()) if x)
    notes_bas = [x for x in (str(f.get("mention_solde") or "").strip(),
                             str(f.get("mention_express") or "").strip() if f.get("option_express") else "") if x]
    return {
        "apercu": not numero_facture, "titre": TITRES[t], "numero": numero_aff, "emetteur": EMETTEUR, "rib": RIB,
        "client_nom": dest.get("raison_sociale") or "", "client_lignes": lignes_client,
        "date_facture": date_iso(f.get("date_facture")).strftime("%d/%m/%Y"),
        "echeance": f"{jours} jours à réception", "ref_appel": ref_appel or "—", "ref_contrat": str(f.get("ref_contrat") or "").strip() or "—",
        "nature": nature, "ref_operation": op or "—",
        "fiche": f"Fiche {str(f.get('fiche') or FICHE).strip()}" + (f" — {f.get('fiche_libelle')}" if f.get("fiche_libelle") else ""),
        "beneficiaire": beneficiaire or "—", "volume": volume,
        "lignes": [
            {"titre": "Prime bénéficiaire", "sous": lib_prime, "total": euros(c["prime_operation"]), "pct": pct,
             "ht": euros(c["prime_ht"]), "tva_taux": "Non applicable", "tva": euros(0), "ttc": euros(c["prime_ttc"])},
            {"titre": "Commission", "sous": lib_comm, "total": euros(c["commission_operation"]), "pct": pct,
             "ht": euros(c["commission_ht"]), "tva_taux": pourcent(c["taux_tva"]), "tva": euros(c["tva_commission"]),
             "ttc": euros(c["commission_ttc"])},
        ],
        "recap": [{"lib": "Prime bénéficiaire", "base": euros(c["prime_ht"]), "taux": "Exonérée", "tva": euros(0)},
                  {"lib": "Commission", "base": euros(c["commission_ht"]), "taux": pourcent(c["taux_tva"], 2), "tva": euros(c["tva_commission"])}],
        "total_ht": euros(c["total_ht"]), "total_tva": euros(c["total_tva"]), "total_ttc": euros(c["total_ttc"]),
        "net_a_payer": euros(c["net_a_payer"]), "mention_tva": MENTION_TVA,
        "conditions": [f"Paiement à {jours} jours à compter de la réception de la présente facture par {client}"
                       + (f", conformément à l'appel à facturation {ref_appel}." if ref_appel else "."),
                       "Pas d'escompte pour paiement anticipé.",
                       "En cas de retard de paiement, pénalités exigibles au taux égal à trois fois le taux d'intérêt légal, "
                       "et indemnité forfaitaire pour frais de recouvrement de 40 € (art. L441-10 et D441-5 du Code de commerce)."],
        "libelle_virement": f"{numero_facture or 'N° de facture'} / {ref_appel or 'réf. appel'}",
        "notes_bas": notes_bas, "pied": PIED, "calcul": c,
    }


def mention_solde_defaut(type_, pct, acompte_numero="") -> str:
    if type_ == "acompte":
        return (f"Le solde de {pourcent(100 - _f(pct))} de l'opération fera l'objet d'une facture distincte à réception "
                f"de l'appel à facturation de solde.")
    if type_ == "solde" and acompte_numero:
        return f"Solde de l'opération après la facture d'acompte {acompte_numero}."
    return ""
