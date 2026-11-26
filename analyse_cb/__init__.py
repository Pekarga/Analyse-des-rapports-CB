"""Analyse automatisée des rapports des Contrôleurs Budgétaires (CB) auprès des EPN.

Usage rapide :
    from analyse_cb import analyser, remplir_modele
    res = analyser("rapport.docx")
    remplir_modele(res, "analyse.xlsx")
"""
from .analyse import InfosRapport, ResultatAnalyse, analyser, charger_parametres
from .excel import remplir_modele, tableau_de_bord

__all__ = ["analyser", "remplir_modele", "tableau_de_bord", "InfosRapport", "ResultatAnalyse", "charger_parametres"]
__version__ = "3.6.0"
