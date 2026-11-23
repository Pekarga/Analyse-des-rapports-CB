"""Lecture du décret de création et d'organisation de l'EPN, et confrontation avec le rapport du CB.

Le décret (PDF texte ou scanné, Word ou texte brut) est découpé en articles. On en extrait :
- la référence du texte (numéro et date), la dénomination, le sigle et la catégorie de l'EPN ;
- les tutelles technique et financière, le siège ;
- les missions (article « a pour missions »), les organes, la périodicité des sessions du Conseil de gestion ;
- les ressources de l'établissement.

Ces éléments servent ensuite à vérifier la partie « Introduction » du rapport (texte de création, missions,
mode de financement, organisation) et la partie « Gouvernance » (sessions du Conseil de gestion).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .controles import FicheEPN, Periode, lire_date
from .structure import AnalyseStructure
from .tableaux import Constat, ControleTableaux
from .texte import normaliser

CONFORME, ECART, A_VERIFIER, INFO = "Conforme", "Écart", "À vérifier", "Information"

RE_REFERENCE = re.compile(
    r"\b(decret|loi|ordonnance|arrete)\s*(?:n\s*[°o.]?\s*|numero\s*)?((?:19|20)\d\d\s*-\s*\d+(?:\s*/\s*\w+)?)"
    r"(?:\s*du\s*(\d{1,2}\s*(?:er)?\s+\w+\s+(?:19|20)\d\d|\d{1,2}\s*[/.-]\s*\d{1,2}\s*[/.-]\s*(?:19|20)\d\d))?")
RE_ARTICLE = re.compile(r"^\s*art(?:icle|\.)?\s*[a-rt-z]?\s*(premier|1er|\d+)\s*(?:er)?\s*(?:[:.\-–)]|$)", re.I)
# Décret scanné : l'OCR place souvent « Article 12 : » en fin de ligne (numéro dans la marge gauche).
RE_ARTICLE_FIN = re.compile(r"^(.*\S)\s+art(?:icle|\.)\s*[a-rt-z]?\s*(premier|1er|\d+)\s*(?:er)?\s*:?\s*$", re.I)

# Organes usuels d'un EPN (décret n°2021-677 et textes particuliers)
ORGANES = [
    ("Conseil de gestion", r"conseil de gestion|\bcoges\b"),
    ("Conseil d'administration", r"conseil d.administration"),
    ("Direction / Directeur", r"\bdirect(eur|rice|ion)( general(e)?)?\b"),
    ("Agent comptable", r"agent comptable"),
    ("Contrôleur budgétaire", r"controleur budgetaire"),
    ("Comité de trésorerie", r"comite de tresorerie"),
    ("Conseil scientifique / technique", r"conseil (scientifique|technique|pedagogique)"),
    ("Comité de direction", r"comite de direction"),
    ("Commission consultative", r"commission consultative"),
    ("Conseil de discipline", r"conseil de discipline"),
]

# Catégories de ressources (pour confronter le décret au rapport et au tableau 3)
CATEGORIES_RESSOURCES = [
    ("Subventions / transferts de l'État", r"subvention|dotation|transferts?|budget (general )?de l.etat|concours de l.etat"),
    ("Ressources propres (prestations, produits, redevances)",
     r"prestations?|produits?|redevances?|remuneration|recettes propres|ressources propres|vente|frais|droits|cotisations|"
     r"location|loyers?|honoraires|taxes? parafiscales?|parafiscal"),
    ("Dons et legs", r"\bdons?\b|legs|liberalites"),
    ("Emprunts", r"emprunts?"),
    ("Concours des partenaires / bailleurs", r"partenaires?|bailleurs?|cooperation|(aides?|appuis?) exterieur|"
                                              r"organismes? internationa"),
]

MOTS_VIDES = set("""a au aux avec ce ces cette dans de des du elle en et il ils la le les leur leurs ou par pour
sur un une son sa ses tout tous toute toutes qui que dont est sont etre mettre assurer faire veiller notamment
ainsi autre autres afin meme plus ensemble cadre matiere domaine domaines charge chargee missions mission
politique gouvernement etat national nationale nationaux publics public publique effet titre selon""".split())

NOMBRES = {"une": 1, "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
           "neuf": 9, "dix": 10, "douze": 12}


@dataclass
class Article:
    numero: str
    texte: str
    items: list[str] = field(default_factory=list)
    lignes: list[str] = field(default_factory=list)  # lignes brutes (pour les énumérations en cours d'article)
    premiere: str = ""  # texte porté par la ligne « Article N : … »

    @property
    def norm(self) -> str:
        return normaliser(self.texte + " " + " ".join(self.items))


@dataclass
class Decret:
    chemin: Path
    texte: str
    reference: str = ""
    type_texte: str = ""
    numero: str = ""
    date: date | None = None
    denomination: str = ""
    sigle: str = ""
    categorie: str = ""
    tutelle_technique: str = ""
    tutelle_financiere: str = ""
    siege: str = ""
    antennes: str = ""
    missions: list[str] = field(default_factory=list)
    organes: list[str] = field(default_factory=list)
    sessions_conseil_par_an: int | None = None
    phrase_sessions: str = ""
    ressources: list[str] = field(default_factory=list)
    categories_ressources: list[str] = field(default_factory=list)
    articles: list[Article] = field(default_factory=list)
    ocr: bool = False

    @property
    def nom(self) -> str:
        return self.denomination + (f" ({self.sigle})" if self.sigle and self.sigle not in self.denomination else "")

    def fiche(self) -> FicheEPN:
        return FicheEPN(self.sigle, self.denomination, self.reference,
                        " / ".join(t for t in (self.tutelle_technique, self.tutelle_financiere) if t))


# ------------------------------------------------------------------ lecture
def _texte_document(chemin: Path) -> tuple[str, bool]:
    ext = chemin.suffix.lower()
    if ext in (".txt", ".md"):
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return chemin.read_text(encoding=enc), False
            except UnicodeDecodeError:
                continue
    from .lecture import lire_rapport
    doc = lire_rapport(chemin)
    lignes = []
    for b in doc.blocs:
        if b.type == "p":
            lignes.append(b.texte)
        else:
            lignes.extend(" ".join(c for c in l if c) for l in b.lignes)
    return "\n".join(lignes), doc.ocr


def _decouper_articles(texte: str) -> list[Article]:
    articles: list[Article] = []
    courant: Article | None = None
    from .lecture import RE_PUCE
    precedente = ""
    for brut in texte.splitlines():
        ligne = brut.strip()
        if not ligne:
            continue
        fin = RE_ARTICLE_FIN.match(ligne)
        if fin and not re.search(r"\bl['’]\s*$", fin.group(1), re.I):  # « … de l'article 5 » : simple renvoi
            ligne = f"Article {fin.group(2)} : " + fin.group(1).lstrip(" :")
        m = RE_ARTICLE.match(ligne)
        if m:
            num = m.group(1).lower()
            courant = Article("1" if num in ("premier", "1er") else num, ligne[m.end():].strip(" :"))
            courant.premiere = courant.texte
            articles.append(courant)
            precedente = courant.texte or ":"
            continue
        if courant is None:
            continue
        if re.match(r"^\s*(chapitre|titre|section)\b", ligne, re.I):
            continue
        ligne = ligne.lstrip(": ")
        courant.lignes.append(ligne)
        minuscule = not re.match(r"^[A-ZÉÈÀ0-9«]", ligne)
        if RE_PUCE.match(ligne):
            courant.items.append(RE_PUCE.sub("", ligne).strip(" ;.,:"))
        elif minuscule and re.search(r"[:;]\s*$", precedente):
            courant.items.append(ligne.strip(" ;.,:"))  # énumération sans tiret (« la rémunération … ; »)
        elif courant.items and minuscule:
            courant.items[-1] += " " + ligne.strip(" ;.,")  # suite d'un élément d'énumération
        else:
            courant.texte += " " + ligne
        precedente = ligne
    return articles


def _enumeration_apres(art: Article, motif: str) -> list[str]:
    """Éléments énumérés qui suivent, dans l'article, la phrase correspondant au motif (et s'arrêtent à la
    phrase suivante commençant par une majuscule)."""
    from .lecture import RE_PUCE
    lignes = [art.premiere] + art.lignes
    for k, l in enumerate(lignes):
        if re.search(motif, normaliser(l)):
            items = []
            for suiv in lignes[k + 1:]:
                if RE_PUCE.match(suiv) or re.match(r"^[-_–•]+\s*", suiv):
                    items.append(re.sub(r"^[-_–•\s]+", "", RE_PUCE.sub("", suiv)).strip(" ;.,:"))
                elif not re.match(r"^[A-ZÉÈÀ«]", suiv):
                    items.append(suiv.strip(" ;.,:"))
                else:
                    break
            return [i for i in items if len(i) > 3]
    return []


def _enumeration(art: Article) -> list[str]:
    """Éléments énumérés d'un article : puces, ou à défaut segments séparés par « ; »."""
    if art.items:
        return [i for i in art.items if len(i) > 3]
    apres = re.split(r":\s*", art.texte, maxsplit=1)
    corps = apres[1] if len(apres) > 1 else art.texte
    morceaux = [m.strip(" .,") for m in re.split(r";|\s-\s", corps) if len(m.strip()) > 3]
    return morceaux if len(morceaux) > 1 else []


def lire_decret(chemin: str | Path) -> Decret:
    chemin = Path(chemin)
    texte, ocr = _texte_document(chemin)
    d = Decret(chemin, texte, ocr=ocr)
    n = normaliser(texte)
    d.articles = _decouper_articles(texte)

    # Référence : premier texte cité dans l'intitulé (avant le premier article)
    entete = texte[: texte.find(d.articles[0].texte)] if d.articles else texte[:1500]
    m = RE_REFERENCE.search(normaliser(entete)) or RE_REFERENCE.search(n)
    if m:
        d.type_texte = {"decret": "Décret", "arrete": "Arrêté"}.get(m.group(1), m.group(1).capitalize())
        d.numero = re.sub(r"\s+", "", m.group(2)).upper()
        d.date = lire_date(m.group(3)) if m.group(3) else None
        d.reference = f"{d.type_texte} n°{d.numero}" + (f" du {d.date:%d/%m/%Y}" if d.date else "")

    # Dénomination et sigle
    m = re.search(r"denomme(?:e)?\s*[«\"“]?\s*([^»\"”,;]{5,150}?)\s*[»\"”]?\s*(?:,|;|\.|\s)\s*(?:en abrege|ci-apres|par abreviation|sigle)"
                  r"\s*[«\"“(]?\s*([a-z0-9](?:[a-z0-9\-]|\.\s?(?=[a-z0-9])){1,24})", n)
    if m:
        d.denomination = _retrouver_casse(texte, m.group(1))
        d.sigle = re.sub(r"[.\s]", "", m.group(2)).upper()
    else:
        m = re.search(r"(?:creation|portant [^\n]{0,80}?)\s+(?:de l.|du |de la |d.)\s*([^,\n]{5,150}?)\s*,?\s*"
                      r"(?:en abrege|en sigle|ci-apres denomme)\s*[«\"“(]?\s*([a-z0-9\-]{2,15})", n)
        if m:
            d.denomination = _retrouver_casse(texte, m.group(1))
            d.sigle = m.group(2).upper()
    if not d.denomination:
        m = re.search(r"denomme(?:e)?\s*[«\"“]\s*([^»\"”]{5,150})\s*[»\"”]", n)
        if m:
            d.denomination = _retrouver_casse(texte, m.group(1))
    m = re.search(r"etablissement public[^.;]{0,60}?(administratif|industriel et commercial|a caractere \w+(?: et \w+)?)", n)
    if m:
        d.categorie = "Établissement public national " + _retrouver_casse(texte, m.group(1))
    elif re.search(r"\bepic\b", n):
        d.categorie = "EPIC"
    elif re.search(r"\bepa\b", n):
        d.categorie = "EPA"

    # Tutelles, siège, antennes
    m = re.search(r"tutelle (?:administrative et )?technique (?:du|de la|des)\s+([^.;]{5,120}?)(?:\s+et\s+(?:sous\s+)?(?:la\s+)?tutelle|[.;]|$)", n)
    if m:
        d.tutelle_technique = _retrouver_casse(texte, m.group(1))
    m = re.search(r"tutelle (?:economique et financiere|financiere|economique)\s+(?:du|de la|des)\s+([^.;]{5,120}?)(?:[.;,]|$)", n)
    if m:
        d.tutelle_financiere = _retrouver_casse(texte, m.group(1))
    m = re.search(r"siege[^;]{0,40}?(?:est )?(?:fixe|etabli|situe|installe)\s+a\s+([a-z' \-]{3,40}?)(?:[.;,]|\s+il\b|$)", n)
    if m:
        d.siege = _retrouver_casse(texte, m.group(1)).strip()
    m = re.search(r"[^.]*\b(antennes?|directions? regionales?|delegations? regionales?|representations? regionales?)\b[^.]*\.", n)
    if m:
        d.antennes = _retrouver_casse(texte, m.group(0).strip())

    # Missions
    for k, art in enumerate(d.articles):
        suivant = d.articles[k + 1] if k + 1 < len(d.articles) else None
        if (re.search(r"(a|ont) pour missions?", normaliser(art.texte)) and suivant
                and re.match(r"^\W*(a ce titre|a cet effet|dans ce cadre)", normaliser(suivant.texte))):
            principale = re.split(r"(?:a|à|ont) pour missions?\s*(?:de\s*)?:?", art.texte, maxsplit=1, flags=re.I)[-1]
            items = _enumeration_apres(suivant, r"chargee?|missions?|attributions?") or _enumeration(suivant)
            d.missions = ([principale.strip(" .")] if len(principale.strip()) > 10 else []) + items
            break
    for art in d.articles if not d.missions else []:
        if re.search(r"(a|ont) pour (missions?|attributions?|objet)|est charge(e)? de|missions? (de l|du|suivantes)|"
                     r"attributions suivantes", normaliser(art.texte)):
            items = _enumeration(art)
            if items:
                d.missions = items
                break
            phrase = re.split(r"(?:a|ont) pour (?:missions?|attributions?|objet)\s*(?:de\s*)?:?|est chargee? de\s*:?",
                              art.texte, maxsplit=1, flags=re.I)
            if len(phrase) > 1 and len(phrase[1].strip()) > 10:
                d.missions = [phrase[1].strip(" .")]
                break

    # Organes et périodicité des sessions du Conseil de gestion
    zone_organes = next((a.norm for a in d.articles if re.search(r"organes?", a.norm[:120])), "")
    for libelle, motif in ORGANES:
        if re.search(motif, zone_organes or n):
            d.organes.append(libelle)
    if zone_organes:  # organes financiers cités ailleurs dans le décret
        for libelle, motif in ORGANES:
            if libelle not in d.organes and libelle in ("Agent comptable", "Contrôleur budgétaire") and re.search(motif, n):
                d.organes.append(libelle)
    d.sessions_conseil_par_an, d.phrase_sessions = _periodicite(texte)

    # Ressources
    motif_res = r"(ressources|recettes)[^:]{0,60}?(comprennent|sont constituees|se composent|proviennent)"
    for art in d.articles:
        if re.search(motif_res, art.norm):
            d.ressources = _enumeration_apres(art, motif_res) or _enumeration(art) or [art.texte.strip()]
            break
    zone = normaliser(" ".join(d.ressources))
    d.categories_ressources = [lib for lib, motif in CATEGORIES_RESSOURCES if re.search(motif, zone)]
    return d


def _retrouver_casse(original: str, norm: str) -> str:
    """Retrouve le passage d'origine (accents, majuscules) correspondant à un extrait normalisé."""
    mots = norm.split()
    if not mots:
        return norm
    motif = r"\W+".join(re.escape(m) for m in mots)
    # Texte normalisé caractère par caractère, avec la position d'origine de chaque caractère produit
    # (« œ » donne deux caractères, les accents disparaissent).
    produits, positions = [], []
    for i, c in enumerate(original):
        nc = normaliser(c) if c.strip() else " "
        for x in nc or " ":
            produits.append(x)
            positions.append(i)
    m = re.search(motif, "".join(produits))
    if not m:
        return norm
    extrait = original[positions[m.start()]:positions[m.end() - 1] + 1]
    return re.sub(r"\s+", " ", extrait).strip(" «»\"“”")


def _periodicite(texte: str) -> tuple[int | None, str]:
    """Nombre minimal de sessions annuelles du Conseil de gestion prévu par le décret."""
    for phrase in re.split(r"(?<=[.;])\s+", texte.replace("\n", " ")):
        p = normaliser(phrase)
        if not re.search(r"(se reunit|session|convoque)", p):
            continue
        if not re.search(r"conseil|coges|il se reunit|ordinaire", p):
            continue
        m = re.search(r"(\w+)\s+fois\s+par\s+(an|annee|semestre|trimestre|mois)", p)
        if m:
            nb = NOMBRES.get(m.group(1)) or (int(m.group(1)) if m.group(1).isdigit() else 1)
            mult = {"an": 1, "annee": 1, "semestre": 2, "trimestre": 4, "mois": 12}[m.group(2)]
            return nb * mult, phrase.strip()
        m = re.search(r"(chaque|une fois par|tous les)\s+(semestre|trimestre|mois|an)", p)
        if m:
            return {"an": 1, "semestre": 2, "trimestre": 4, "mois": 12}[m.group(2)], phrase.strip()
        m = re.search(r"(\w+)\s+sessions?\s+(?:ordinaires?\s+)?par\s+an", p)
        if m:
            nb = NOMBRES.get(m.group(1)) or (int(m.group(1)) if m.group(1).isdigit() else None)
            if nb:
                return nb, phrase.strip()
    return None, ""


# ------------------------------------------------------------------ choix du décret d'un EPN
def correspond(decret: Decret, nom_epn: str, fiche: FicheEPN | None, texte_debut: str = "") -> bool:
    cibles = [normaliser(x) for x in (nom_epn, fiche.denomination if fiche else "", texte_debut) if x]
    if decret.sigle:
        motif = r"\b" + re.escape(normaliser(decret.sigle)) + r"\b"
        if any(re.search(motif, c) for c in cibles) or (fiche and normaliser(fiche.sigle) == normaliser(decret.sigle)):
            return True
    den = normaliser(decret.denomination)
    return bool(den) and any(den in c or (len(c) > 8 and c in den) for c in cibles)


def choisir_decret(decrets: list[Decret], nom_epn: str, fiche: FicheEPN | None, texte_debut: str = "",
                   unique: bool = False) -> Decret | None:
    for d in decrets:
        if correspond(d, nom_epn, fiche, texte_debut):
            return d
    return decrets[0] if unique and len(decrets) == 1 else None


# ------------------------------------------------------------------ confrontation avec le rapport
@dataclass
class PointDecret:
    theme: str
    rubrique: str  # code de la rubrique du canevas concernée
    disposition: str  # ce que prévoit le décret
    constat: str  # ce que dit le rapport
    statut: str  # Conforme, Écart, À vérifier, Information


def _mots_cles(texte: str, exclus: set[str] = frozenset()) -> list[str]:
    mots = re.findall(r"[a-z]{4,}", normaliser(texte))
    out = []
    for m in mots:
        racine = m[:7]
        if m not in MOTS_VIDES and racine not in exclus and racine not in out:
            out.append(racine)
    return out


def _couverture(element: str, zone: str, exclus: set[str] = frozenset()) -> float:
    mots = _mots_cles(element, exclus)
    if not mots:
        return 1.0
    racines_zone = set(m[:7] for m in re.findall(r"[a-z]{4,}", zone))
    return sum(1 for m in mots if m in racines_zone) / len(mots)


def _sessions_citees(texte: str) -> int | None:
    n = normaliser(texte)
    m = re.search(r"(?:conseil de gestion|coges|conseil d.administration)[^.]{0,120}?"
                  r"(?:reuni|tenu|organise|siege)[^.]{0,30}?\b(\w+)\s+(?:fois|sessions?|reunions?)", n) \
        or re.search(r"\b(\w+)\s+(?:sessions?|reunions?)\s+(?:ordinaires?\s+|extraordinaires?\s+)?(?:du|de son)\s+"
                     r"(?:conseil de gestion|coges|conseil d.administration)", n)
    if m:
        v = m.group(1)
        return NOMBRES.get(v) or (int(v) if v.isdigit() else None)
    if re.search(r"(?:conseil de gestion|coges)[^.]{0,100}(?:ne s.est pas reuni|aucune (session|reunion))", n):
        return 0
    return None


class ConfrontationDecret:
    """Points de contrôle du rapport au regard du décret de création et d'organisation."""

    def __init__(self, decret: Decret, structure: AnalyseStructure, tableaux: ControleTableaux, periode: Periode):
        self.decret, self.s, self.t, self.periode = decret, structure, tableaux, periode
        self.points: list[PointDecret] = []
        self.constats: list[Constat] = []
        intro = self.s.texte_section("introduction") or ""
        self.zone_intro = normaliser(intro + "\n" + self.s["texte_creation"].texte + "\n" + self.s["missions"].texte)
        self._texte_creation()
        self._missions()
        self._financement()
        self._organisation()
        self._tutelle_siege()
        self._sessions_conseil()

    def _point(self, theme, rubrique, disposition, constat, statut, gravite=None, controle="", nature="coherence"):
        self.points.append(PointDecret(theme, rubrique, disposition, constat, statut))
        if statut == ECART and gravite:
            self.constats.append(Constat(rubrique, controle or f"Conformité au décret : {theme.lower()}",
                                         f"{constat} (décret : {disposition})", gravite, nature,
                                         attendu=disposition[:120], constate=constat[:120]))

    def statut(self, rubrique: str) -> str | None:
        """Synthèse des points du décret pour une rubrique : Conforme, Écart ou None (non vérifié)."""
        pts = [p for p in self.points if p.rubrique == rubrique and p.statut in (CONFORME, ECART)]
        if not pts:
            return None
        return ECART if any(p.statut == ECART for p in pts) else CONFORME

    def commentaire(self, rubrique: str) -> str:
        return " ".join(f"{p.theme} : {p.constat}" for p in self.points
                        if p.rubrique == rubrique and p.statut in (CONFORME, ECART, A_VERIFIER))

    # -- texte de création
    def _texte_creation(self) -> None:
        d = self.decret
        if not d.numero:
            self._point("Référence du texte de création", "texte_creation", "Référence non lue dans le décret",
                        "Vérification impossible", A_VERIFIER)
            return
        zone = re.sub(r"\s*-\s*", "-", self.zone_intro)
        num = normaliser(d.numero).replace(" ", "")
        # Phrase(s) qui présentent le texte de création (« créée par décret n°… ») : le numéro y est vérifié
        # en priorité, car le bon numéro peut figurer ailleurs (ex. renvoi aux articles du décret).
        phrases = [p for p in re.split(r"(?<=[.;])\s+", zone)
                   if re.search(r"\b(cree|creee|creation|institue|instituee|erige|erigee)\b", p) and RE_REFERENCE.search(p)]
        cites_creation = sorted(set(re.sub(r"\s", "", m.group(2)) for p in phrases for m in RE_REFERENCE.finditer(p)))
        if cites_creation and num not in cites_creation:
            ailleurs = num in zone.replace(" ", "")
            constat = (f"Le rapport présente comme texte de création le n°{', '.join(cites_creation)}, alors que le décret "
                       f"de création est le n°{d.numero}"
                       + (" (ce numéro n'apparaît qu'ailleurs dans le rapport : erreur de saisie probable)." if ailleurs else "."))
            self._point("Référence du texte de création", "texte_creation", d.reference, constat, ECART, "Majeure",
                        "Texte de création conforme au décret", "fiabilite")
            return
        if num not in zone.replace(" ", ""):
            cites = sorted(set(re.sub(r"\s", "", m.group(2)) for m in RE_REFERENCE.finditer(zone)
                               if not re.match(r"2021-677|2020-627", re.sub(r"\s", "", m.group(2)))))
            constat = ("Le texte de création n'est pas cité dans l'introduction." if not cites else
                       f"Texte(s) cité(s) dans le rapport : {', '.join(cites)} – ne correspond(ent) pas au décret.")
            self._point("Référence du texte de création", "texte_creation", d.reference, constat, ECART, "Majeure",
                        "Texte de création conforme au décret", "fiabilite")
            return
        constat = f"Le rapport cite bien le {d.type_texte.lower()} n°{d.numero}"
        statut = CONFORME
        if d.date:
            dates = [lire_date(m.group(0)) for m in re.finditer(
                r"\d{1,2}\s*(?:er)?\s+[a-z]+\s+(?:19|20)\d\d|\d{1,2}\s*/\s*\d{1,2}\s*/\s*(?:19|20)\d\d", zone)]
            if d.date in dates:
                constat += f" du {d.date:%d/%m/%Y}."
            else:
                constat += f", mais la date du {d.date:%d/%m/%Y} n'est pas retrouvée (absente ou erronée)."
                statut = ECART
        else:
            constat += "."
        self._point("Référence du texte de création", "texte_creation", d.reference, constat, statut, "Mineure",
                    "Date du texte de création conforme au décret", "fiabilite")

    # -- missions
    def _missions(self) -> None:
        d = self.decret
        if not d.missions:
            self._point("Missions", "missions", "Missions non lues dans le décret", "Vérification impossible", A_VERIFIER)
            return
        zone = self.zone_intro
        # Les mots de la dénomination de l'EPN (ex. « exemple ») figurent partout : ils ne prouvent rien.
        exclus = {m[:7] for m in re.findall(r"[a-z]{4,}", normaliser(d.denomination))}
        reprises = [m for m in d.missions if _couverture(m, zone, exclus) >= 0.6]
        taux = len(reprises) / len(d.missions)
        manquantes = [m for m in d.missions if m not in reprises]
        constat = f"{len(reprises)} mission(s) sur {len(d.missions)} rappelée(s) dans le rapport ({taux:.0%})."
        if manquantes:
            constat += " Non retrouvées : " + " ; ".join(_court(m, 90) for m in manquantes[:5]) + ("…" if len(manquantes) > 5 else "")
        statut = CONFORME if taux >= 0.75 else ECART
        disposition = f"{len(d.missions)} mission(s) : " + " ; ".join(_court(m, 70) for m in d.missions[:6])
        self._point("Missions", "missions", disposition, constat, statut, "Mineure" if taux >= 0.4 else "Majeure",
                    "Missions conformes au décret")

    # -- financement
    def _financement(self) -> None:
        d = self.decret
        if not d.categories_ressources:
            if d.ressources:
                self._point("Ressources", "financement", "; ".join(_court(r, 60) for r in d.ressources[:5]),
                            "Catégories de ressources non reconnues : vérifier manuellement.", A_VERIFIER)
            return
        zone = normaliser(self.s.texte_section("introduction") + " " + self.s["financement"].texte)
        cites = [lib for lib, motif in CATEGORIES_RESSOURCES if lib in d.categories_ressources and re.search(motif, zone)]
        principales = [c for c in d.categories_ressources if c.startswith(("Subventions", "Ressources propres"))]
        manque = [c for c in principales if c not in cites]
        disposition = "Ressources prévues : " + " ; ".join(d.categories_ressources)
        if manque:
            self._point("Mode de financement", "financement", disposition,
                        "Le rapport ne mentionne pas : " + " ; ".join(manque) + ".", ECART, "Mineure",
                        "Mode de financement conforme au décret")
        else:
            self._point("Mode de financement", "financement", disposition,
                        "Sources de financement citées : " + (" ; ".join(cites) or "aucune") + ".", CONFORME)
        # Ressources budgétées (tableau 3 / 5) non prévues par le décret
        tab = self.t.par_code.get("T3") or self.t.par_code.get("T5")
        if tab:
            libelles = normaliser(" ".join(l.libelle for l in tab.lignes if l.type in ("ligne", "groupe")))
            hors = [lib for lib, motif in CATEGORIES_RESSOURCES[2:]
                    if lib not in d.categories_ressources and re.search(motif, libelles)]
            if hors:
                self._point("Ressources budgétées", "pres_ressources", disposition,
                            f"Le {tab.nom} comporte des ressources non prévues par le décret : " + " ; ".join(hors) + ".",
                            ECART, "Mineure", "Ressources budgétées prévues par le décret")

    # -- organes / organisation
    def _organisation(self) -> None:
        d = self.decret
        if not d.organes:
            return
        zone = normaliser(" ".join(self.s.texte_section(c) for c in ("introduction", "gouvernance", "coges",
                                                                      "comite_tresorerie", "organisation")))
        motifs = dict(ORGANES)
        absents = [o for o in d.organes if o not in ("Contrôleur budgétaire",) and not re.search(motifs[o], zone)]
        disposition = "Organes : " + " ; ".join(d.organes)
        if absents:
            self._point("Organes de l'EPN", "organisation", disposition,
                        "Organes prévus par le décret non évoqués : " + " ; ".join(absents) + ".",
                        ECART if "Conseil de gestion" in absents or "Conseil d'administration" in absents else A_VERIFIER,
                        "Mineure", "Organisation conforme au décret")
        else:
            self._point("Organes de l'EPN", "organisation", disposition, "Tous les organes prévus sont évoqués.", CONFORME)

    # -- tutelle et siège (information)
    def _tutelle_siege(self) -> None:
        d = self.decret
        texte = normaliser(self.s.texte_section("introduction"))
        if d.tutelle_technique:
            mots = _mots_cles(d.tutelle_technique)
            vu = "tutelle" in texte and (not mots or _couverture(d.tutelle_technique, texte) >= 0.5)
            self.points.append(PointDecret("Tutelle technique", "introduction", d.tutelle_technique,
                                           "Mentionnée dans l'introduction." if vu else "Non mentionnée dans l'introduction.",
                                           CONFORME if vu else INFO))
        if d.siege:
            vu = normaliser(d.siege) in texte
            self.points.append(PointDecret("Siège", "antennes", d.siege, "Mentionné." if vu else "Non mentionné.",
                                           CONFORME if vu else INFO))
        if d.antennes:
            det = self.s["antennes"]
            self.points.append(PointDecret("Antennes / implantations", "antennes", _court(d.antennes, 160),
                                           "Évoquées dans le rapport." if det.trouvee else
                                           "Le décret prévoit des implantations : le rapport n'en fait pas état.",
                                           CONFORME if det.trouvee else A_VERIFIER))

    # -- sessions du Conseil de gestion
    def _sessions_conseil(self) -> None:
        d = self.decret
        if not d.sessions_conseil_par_an:
            return
        mois = {"etape": 6, "trimestriel": 3, "annuel": 12}.get(self.periode.type, 12)
        if self.periode.type == "trimestriel" and self.periode.trimestre:
            mois = 3 * self.periode.trimestre  # cumul depuis le début de l'exercice
        attendu = math.floor(d.sessions_conseil_par_an * mois / 12 + 1e-9)
        texte = self.s.texte_section("coges") or self.s.texte_section("gouvernance")
        cite = _sessions_citees(texte) if texte else None
        disposition = f"{d.sessions_conseil_par_an} session(s) ordinaire(s) par an au minimum – « {_court(d.phrase_sessions, 140)} »"
        if cite is None:
            self._point("Sessions du Conseil de gestion", "coges", disposition,
                        f"Nombre de sessions non précisé par le rapport (attendu sur la période : {attendu} au moins).",
                        A_VERIFIER)
        elif cite < attendu:
            self._point("Sessions du Conseil de gestion", "coges", disposition,
                        f"{cite} session(s) rapportée(s) pour {attendu} attendue(s) sur la période : périodicité non "
                        "respectée (à commenter par le CB).", ECART, "Mineure", "Périodicité des sessions du Conseil de gestion")
        else:
            self._point("Sessions du Conseil de gestion", "coges", disposition,
                        f"{cite} session(s) rapportée(s) (≥ {attendu} attendue(s) sur la période).", CONFORME)


def _court(t: str, n: int) -> str:
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"
