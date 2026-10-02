# -*- coding: utf-8 -*-
"""Lot 8f — PDF via Chromium (Playwright), plus rapide et toujours avec ses polices.

- Un seul Chromium, gardé ouvert par un fil de travail dédié (l'API « sync » de Playwright appartient au fil qui l'a
  créée) ; un contexte partagé (les polices téléchargées restent en cache), une page neuve par PDF.
- Avant d'imprimer : toutes les polices de la page chargées (document.fonts.ready) — sinon Chromium imprimait parfois
  avec une police de secours (largeurs différentes, libellés coupés).
- Cache : clé = empreinte SHA-256 du HTML FINAL rendu + options d'impression. Le moindre changement (fiche, catalogue,
  admin, modèle de document) change le HTML, donc la clé : le PDF est régénéré. Un PDF imprimé sans la police Inter
  n'est jamais mis en cache.
- Repli : si le Chromium réutilisé plante, il est relancé et le PDF refait avec un navigateur neuf.
"""
import atexit
import collections
import concurrent.futures
import hashlib
import queue
import threading

PIED_DE_PAGE = """<div style="width:100%; box-sizing:border-box; padding:0 24px; font-family:'Inter',Helvetica,Arial,sans-serif;"><table style="width:100%; border:0; border-collapse:collapse;"><tr><td style="text-align:left; vertical-align:bottom; font-size:7px; color:#6B7480; line-height:1.45;"><div><strong style="color:#002E5A;">SAS HEXA RÉNOV'</strong> · 58 Rue de la Sablière, 92600 Asnières-sur-Seine · RCS Nanterre 845 229 152 · SIRET 845 229 152 00028 · TVA FR 89 845 229 152</div><div>RGE CertiRénov' n° CR-2025-92-0052 · Assurance Décennale &amp; RC Pro — MIC Insurance n° AXE2502159 · Validité : 19/03/2026 au 18/03/2027</div><div>info@hexa-renov.fr · 09 70 70 25 11</div></td><td style="text-align:right; vertical-align:bottom; white-space:nowrap; font-size:8px; color:#9AA3AE; padding-left:12px;">Page <span class="pageNumber"></span> / <span class="totalPages"></span></td></tr></table></div>"""
OPTIONS = dict(format="A4", print_background=True, display_header_footer=True, header_template="<span></span>",
               footer_template=PIED_DE_PAGE, margin={"top": "0", "bottom": "1.4cm", "left": "0", "right": "0"})
VERSION_RENDU = "8f-1"            # à changer si OPTIONS ou la façon d'imprimer changent : invalide tout le cache

# Attend toutes les polices de la page (et deux images), puis dit si une police Inter est bien chargée.
ATTENDRE_POLICES = """async () => {
  if (document.fonts) {
    await document.fonts.ready;
    await Promise.all([...document.fonts].filter(f => f.status === 'loading').map(f => f.loaded.catch(() => null)));
  }
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  return !!document.fonts && [...document.fonts].some(f => /Inter/.test(f.family) && f.status === 'loaded');
}"""

CACHE_MAX = 64
CACHE_OCTETS_MAX = 150 * 1024 * 1024
_cache = collections.OrderedDict()
_cache_verrou = threading.Lock()
stats = {"generes": 0, "cache": 0, "relances": 0, "sans_inter": 0}


def cle(html: str) -> str:
    return hashlib.sha256((VERSION_RENDU + "\0" + html).encode("utf-8")).hexdigest()


def _du_cache(k):
    with _cache_verrou:
        pdf = _cache.get(k)
        if pdf is not None:
            _cache.move_to_end(k)
        return pdf


def _en_cache(k, pdf):
    with _cache_verrou:
        _cache[k] = pdf
        _cache.move_to_end(k)
        while len(_cache) > CACHE_MAX or sum(len(v) for v in _cache.values()) > CACHE_OCTETS_MAX:
            _cache.popitem(last=False)


def vider_cache():
    with _cache_verrou:
        _cache.clear()


class _Moteur:
    """Fil de travail qui possède Playwright et un Chromium ; les PDF sont faits l'un après l'autre."""

    def __init__(self):
        self._file = queue.Queue()
        self._fil = None
        self._verrou = threading.Lock()

    def _demarrer(self):
        with self._verrou:
            if self._fil is None or not self._fil.is_alive():
                self._fil = threading.Thread(target=self._boucle, name="pdf-chromium", daemon=True)
                self._fil.start()

    def _boucle(self):
        from playwright.sync_api import sync_playwright
        pw = navigateur = contexte = None

        def lancer():
            nonlocal pw, navigateur, contexte
            fermer()
            pw = sync_playwright().start()
            navigateur = pw.chromium.launch(args=["--no-sandbox"])
            contexte = navigateur.new_context()      # partagé : les polices téléchargées restent en cache

        def fermer():
            nonlocal pw, navigateur, contexte
            contexte = None
            for o, m in ((navigateur, "close"), (pw, "stop")):
                try:
                    if o is not None:
                        getattr(o, m)()
                except Exception:  # noqa: BLE001
                    pass
            pw = navigateur = None

        def imprimer(html, options):
            page = contexte.new_page()                # une page par document (rien ne passe de l'un à l'autre)
            try:
                page.set_content(html, wait_until="load")          # feuilles de style et images chargées
                inter = page.evaluate(ATTENDRE_POLICES)            # puis toutes les polices
                return page.pdf(**(options or OPTIONS)), bool(inter)
            finally:
                page.close()

        while True:
            job = self._file.get()
            if job is None:
                fermer()
                return
            html, options, futur = job
            if html is _PANNE:                       # tests : le Chromium réutilisé « plante » (il est fermé)
                try:
                    navigateur.close()
                except Exception:  # noqa: BLE001
                    pass
                futur.set_result(None)
                continue
            try:
                try:
                    if navigateur is None:
                        lancer()
                    elif not navigateur.is_connected():   # le Chromium réutilisé est tombé : un neuf
                        stats["relances"] += 1
                        lancer()
                    res = imprimer(html, options)
                except Exception:  # noqa: BLE001  — navigateur réutilisé en panne : un neuf, une seconde fois
                    stats["relances"] += 1
                    lancer()
                    res = imprimer(html, options)
                futur.set_result(res)
            except BaseException as exc:  # noqa: BLE001
                futur.set_exception(exc)

    def pdf(self, html: str, options=None):
        self._demarrer()
        futur = concurrent.futures.Future()
        self._file.put((html, options, futur))
        return futur.result()

    def arreter(self):
        if self._fil is not None and self._fil.is_alive():
            self._file.put(None)
            self._fil.join(timeout=10)


_PANNE = object()
_moteur = _Moteur()


def simuler_panne():
    """Tests : ferme le Chromium réutilisé comme s'il avait planté (le PDF suivant doit passer par le repli)."""
    _moteur._demarrer()
    futur = concurrent.futures.Future()
    _moteur._file.put((_PANNE, None, futur))
    futur.result()
atexit.register(_moteur.arreter)


# Lot 11 : document à sa propre mise en page (facture délégataire) — pas de pied de page commun, marges du document.
OPTIONS_SANS_PIED = dict(format="A4", print_background=True, prefer_css_page_size=True,
                         margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})


def html_vers_pdf(html: str, options: dict | None = None) -> bytes:
    k = cle(html) if options is None else cle(html + "|options|" + repr(sorted(options.items())))
    pdf = _du_cache(k)
    if pdf is not None:
        stats["cache"] += 1
        return pdf
    pdf, inter = _moteur.pdf(html, options)
    stats["generes"] += 1
    if inter:
        _en_cache(k, pdf)
    else:
        stats["sans_inter"] += 1
    return pdf
