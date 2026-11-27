"""Repérage des rubriques du canevas dans le rapport et découpage en sections."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .canevas import RUBRIQUES, Rubrique
from .lecture import RE_LEGENDE, Bloc, DocumentRapport
from .texte import extrait, nb_mots, normaliser

RE_NUMEROTATION = re.compile(r"^\s*(([IVXLivxl1]{1,5}|\d{1,2}|[A-H])(\.\d[\d.]*\s*[-.)]?\s*|[.\-)]\s*)|[-•●▪➢•*]\s*)+")


# Parties dont le titre peut nommer une sous-partie traitée dans son texte, sans sous-titre propre.
VIA_PARENT = {"dispositifs_controle": ("controle_interne", "controle_gestion"),
              "difficultes_suggestions": ("difficultes", "suggestions"),
              "gouvernance": ("coges", "comite_tresorerie")}


@dataclass
class Detection:
    rubrique: Rubrique
    mode: str | None = None  # "titre", "texte" ou None (absente)
    titre: str = ""
    debut: int | None = None  # index du bloc de titre (ou du premier paragraphe trouvé)
    fin: int | None = None
    texte: str = ""
    nb_mots: int = 0
    paragraphes: list[int] = field(default_factory=list)
    via_parent: str = ""  # sous-partie traitée sous le titre de sa partie (titre de la partie)

    @property
    def trouvee(self) -> bool:
        return self.mode is not None

    @property
    def extrait(self) -> str:
        return extrait(self.texte)


def _sans_numero(texte: str) -> str:
    return RE_NUMEROTATION.sub("", texte).strip()


def _est_titre_principal(b: Bloc) -> bool:
    t = b.texte.strip()
    if b.niveau_titre == 1:
        return True
    if re.match(r"^\s*[IVX]{1,5}\s*[.\-)]\s*\D", t) and not re.match(r"^\s*[IVX]{1,5}\s*[.\-]\s*\d", t):
        return True
    return t.isupper()


class AnalyseStructure:
    def __init__(self, doc: DocumentRapport):
        self.doc = doc
        self.titres = [b for b in doc.paragraphes
                       if b.candidat_titre and not RE_LEGENDE.match(b.texte)
                       and not normaliser(b.texte).startswith("source")]
        self.detections: dict[str, Detection] = {}
        self.sommaire_absents: list[str] = []  # entrées du sommaire / plan sans développement (texte d'origine)
        self._analyser()

    # ------------------------------------------------------------------ recherche
    def _chercher_titre(self, rub: Rubrique, debut: int, fin: int, principal: bool) -> Bloc | None:
        candidats = [b for b in self.titres if debut <= b.index < fin]
        for motif in rub.titres:
            trouves = [b for b in candidats if re.search(motif, normaliser(_sans_numero(b.texte)))]
            if not trouves:
                continue
            if principal:
                prioritaires = [b for b in trouves if _est_titre_principal(b)]
                return (prioritaires or trouves)[0]
            return trouves[0]
        return None

    def _chercher_texte(self, rub: Rubrique, debut: int, fin: int) -> list[Bloc]:
        trouves = []
        for b in self.doc.blocs[debut:fin]:
            if b.type != "p" or b.sommaire:
                continue
            n = b.norm
            if any(re.search(m, n) for m in rub.contenu):
                trouves.append(b)
        return trouves

    def _analyser(self) -> None:
        n = len(self.doc.blocs)
        # 1) Parties principales, cherchées dans tout le document.
        principales = [r for r in RUBRIQUES if r.parent is None]
        for rub in principales:
            b = self._chercher_titre(rub, 0, n, principal=True)
            self.detections[rub.code] = Detection(rub, "titre", b.texte, b.index) if b else Detection(rub)
        self._calculer_fins([d for d in self.detections.values() if d.trouvee], 0, n)

        # 2) Sous-parties, cherchées dans la partie parente (ou dans tout le document à défaut).
        for niveau in (2, 3):
            for rub in [r for r in RUBRIQUES if r.parent and r.niveau == niveau]:
                parent = self.detections.get(rub.parent)
                if parent and parent.trouvee:
                    debut, fin = parent.debut + 1, parent.fin
                else:
                    debut, fin = 0, n
                det = Detection(rub)
                b = self._chercher_titre(rub, debut, fin, principal=False) if rub.titres else None
                if b is not None:
                    det.mode, det.titre, det.debut = "titre", b.texte, b.index
                elif rub.contenu:
                    trouves = self._chercher_texte(rub, debut, fin)
                    if trouves:
                        det.mode, det.debut = "texte", trouves[0].index
                        det.paragraphes = [t.index for t in trouves]
                self.detections[rub.code] = det
            # bornes des sous-parties dans chaque partie parente
            for parent_code in {r.parent for r in RUBRIQUES if r.niveau == niveau and r.parent}:
                parent = self.detections.get(parent_code)
                filles = [d for d in self.detections.values()
                          if d.rubrique.parent == parent_code and d.mode == "titre"]
                if parent and parent.trouvee:
                    self._calculer_fins(filles, parent.debut, parent.fin)
                else:
                    self._calculer_fins(filles, 0, n)

        # 2 bis) Sous-partie nommée dans le titre de sa partie (« Évaluation du dispositif de contrôle interne
        #    budgétaire », « Difficultés rencontrées et suggestions ») : traitée dans le texte de la partie.
        for parent_code, filles in VIA_PARENT.items():
            parent = self.detections.get(parent_code)
            if not parent or parent.mode != "titre":
                continue
            titre = normaliser(_sans_numero(parent.titre))
            sous_titres = [d.debut for d in self.detections.values() if d.mode == "titre" and d.rubrique.parent == parent_code]
            fin_corps = min(sous_titres) if sous_titres else parent.fin
            corps = [b.index for b in self.doc.blocs[parent.debut + 1:fin_corps] if b.type == "p" and not b.sommaire]
            for code in filles:
                det = self.detections.get(code)
                if det is None or det.trouvee or not corps:
                    continue
                if any(re.search(m, titre) for m in det.rubrique.titres):
                    det.mode, det.debut, det.paragraphes, det.via_parent = "texte", corps[0], corps, parent.titre.strip()

        # 3) Texte et volume de chaque rubrique (les titres des sous-parties ne comptent pas comme contenu :
        #    une partie dont toutes les sous-parties sont vides est elle-même vide)
        titres_detectes = {d.debut for d in self.detections.values() if d.mode == "titre"}
        for det in self.detections.values():
            if det.mode == "titre":
                det.texte = "\n".join(b.texte for b in self.doc.blocs[det.debut + 1:det.fin]
                                      if b.type == "p" and not b.sommaire and b.index not in titres_detectes
                                      and not (b.type == "p" and b.candidat_titre and len(b.texte) < 80))
            elif det.mode == "texte":
                det.texte = "\n".join(self.doc.blocs[i].texte for i in det.paragraphes)
                det.fin = det.paragraphes[-1] + 1
            det.nb_mots = nb_mots(det.texte)

    def _calculer_fins(self, detections: list[Detection], debut: int, fin: int) -> None:
        """La fin d'une section = le prochain titre détecté (toutes rubriques confondues) ou la fin du parent."""
        tous_titres = sorted({d.debut for d in self.detections.values() if d.mode == "titre"})
        for det in detections:
            suivants = [i for i in tous_titres if i > det.debut and i <= fin]
            if det.rubrique.niveau == 1:
                suivants = [d.debut for d in self.detections.values()
                            if d.mode == "titre" and d.rubrique.niveau == 1 and d.debut > det.debut]
            det.fin = min(suivants) if suivants else fin

    # ------------------------------------------------------------------ accès
    def __getitem__(self, code: str) -> Detection:
        return self.detections[code]

    def texte_section(self, code: str, avec_tableaux: bool = False) -> str:
        d = self.detections.get(code)
        if not d or not d.trouvee:
            return ""
        if d.mode == "texte":
            return d.texte
        return self.doc.texte(d.debut + 1, d.fin, avec_tableaux)

    def section_du_bloc(self, index: int) -> str | None:
        """Rubrique la plus fine contenant le bloc donné."""
        meilleure = None
        for d in self.detections.values():
            if d.mode == "titre" and d.debut <= index < (d.fin or 0):
                if meilleure is None or d.rubrique.niveau >= meilleure.rubrique.niveau:
                    meilleure = d
        return meilleure.rubrique.code if meilleure else None

    # ------------------------------------------------------------------ sommaire
    def controle_sommaire(self) -> tuple[str, str]:
        """Cohérence entre la table des matières et les titres effectivement présents."""
        entrees = []
        originaux: dict[str, str] = {}
        for b in self.doc.paragraphes:
            if not b.sommaire:
                continue
            t = re.split(r"\s*(?:[.…_]{2,}[.…_,/ ]{2,}|\t)", b.texte)[0]  # points de conduite (y compris OCR)
            t = re.sub(r"(\.{3,}|…+|_{3,}|\t)+\s*\d{1,3}\s*$", "", t)
            t = re.sub(r"\s+\d{1,3}\s*$", "", t)
            t = normaliser(_sans_numero(t))
            if re.match(r"^\d{6,}", t):
                continue  # ligne de compte (annexe) prise à tort pour une entrée de sommaire
            if t and t not in ("table des matieres", "sommaire", "liste des tableaux", "plan du rapport", "plan",
                               "plan de redaction") \
                    and not t.startswith("tableau") and len(t) > 2:
                entrees.append(t)
                brut = re.split(r"\s*(?:[.…_]{2,}[.…_,/ ]{2,}|\t)", b.texte)[0]
                brut = re.sub(r"(\.{3,}|…+|_{3,})\s*\d{1,3}\s*$", "", brut).strip()
                originaux[t] = _sans_numero(brut).strip(" -–:")
        if not entrees:
            return "Non conforme", "Aucune table des matières (sommaire) n'a été détectée dans le rapport."
        titres_corps = [normaliser(_sans_numero(b.texte)) for b in self.titres]
        absents = []
        for e in entrees:
            # Les points de conduite mal lus par l'OCR laissent du « bruit » après le titre : on compare aussi
            # le titre du corps au début de l'entrée du sommaire.
            ok = any(e == t or e in t or (t and t in e and len(t) > 5)
                     or difflib.SequenceMatcher(None, e, t).ratio() >= 0.8
                     or (len(t) >= 8 and difflib.SequenceMatcher(None, e[:len(t) + 2], t).ratio() >= 0.8)
                     for t in titres_corps)
            if not ok:
                absents.append(e)
        self.sommaire_absents = [originaux.get(e, e) for e in absents]
        if not absents:
            return "Conforme", f"Les {len(entrees)} entrées du sommaire correspondent aux titres du rapport."
        taux = len(absents) / len(entrees)
        statut = "Non conforme" if taux > 0.25 else "À vérifier"
        liste = "; ".join(absents[:8]) + (" …" if len(absents) > 8 else "")
        return statut, (f"{len(absents)} entrée(s) du sommaire sur {len(entrees)} sans titre correspondant "
                        f"dans le corps du rapport : {liste}. Vérifier aussi la pagination.")
