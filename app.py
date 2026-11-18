"""Interface web locale pour les Chargés d'Études.

Lancement :  streamlit run app.py
(le navigateur s'ouvre sur http://localhost:8501 ; aucun document ne quitte le poste.)
"""
from __future__ import annotations

import io
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from analyse_cb import InfosRapport, analyser, remplir_modele, tableau_de_bord
from analyse_cb.analyse import charger_parametres

st.set_page_config(page_title="Analyse des rapports des CB", page_icon="📑", layout="wide")
st.title("Analyse des rapports des Contrôleurs Budgétaires")
st.caption("Contrôle automatique de la forme et du fond selon le canevas DCB de juillet 2023 – "
           "pré-remplissage du fichier d'analyse. Les résultats sont à valider par le Chargé d'Études.")

with st.sidebar:
    st.header("Paramètres")
    charge = st.text_input("Chargé d'Études")
    modele = st.file_uploader("Modèle Excel d'analyse (facultatif)", type=["xlsx"],
                              help="Par défaut : modeles/Fichier_analyse_des_rapports_des_CB.xlsx")
    referentiel = st.file_uploader("Référentiel des EPN (facultatif, CSV ;)", type=["csv"])

fichiers = st.file_uploader("Rapports des CB (.docx ou .pdf)", type=["docx", "pdf"], accept_multiple_files=True)
if not fichiers:
    st.info("Déposez un ou plusieurs rapports pour lancer l'analyse.")
    st.stop()

st.subheader("Informations de réception")
saisie = pd.DataFrame([{"Fichier": f.name, "Date de réception": None, "EPN (si non détecté)": "",
                        "Période (si non détectée)": ""} for f in fichiers])
saisie = st.data_editor(saisie, hide_index=True, use_container_width=True, column_config={
    "Fichier": st.column_config.TextColumn(disabled=True),
    "Date de réception": st.column_config.DateColumn(format="DD/MM/YYYY"),
    "Période (si non détectée)": st.column_config.TextColumn(help="ex. « 1er semestre 2025 » ou « exercice 2024 »"),
})

if not st.button("Lancer l'analyse", type="primary"):
    st.stop()

parametres = charger_parametres()
from analyse_cb import lecture  # noqa: E402

barre = st.empty()


def _progression(page, total):
    barre.progress(page / total, text=f"Document scanné : lecture OCR page {page}/{total}…")


lecture.RAPPEL_PROGRESSION = _progression
with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    chemin_modele = None
    if modele:
        chemin_modele = tmp / "modele.xlsx"
        chemin_modele.write_bytes(modele.getvalue())
    chemin_ref = None
    if referentiel:
        chemin_ref = tmp / "referentiel.csv"
        chemin_ref.write_bytes(referentiel.getvalue())
    resultats = []
    for f, (_, ligne) in zip(fichiers, saisie.iterrows()):
        source = tmp / f.name
        source.write_bytes(f.getvalue())
        reception = ligne["Date de réception"]
        infos = InfosRapport(epn=ligne["EPN (si non détecté)"] or "", charge_etudes=charge,
                             date_reception=reception if isinstance(reception, date) else None,
                             periode=ligne["Période (si non détectée)"] or None)
        try:
            res = analyser(source, infos, parametres, chemin_ref)
            sortie = remplir_modele(res, tmp / f"Analyse_{source.stem}.xlsx", chemin_modele)
        except Exception as exc:
            st.error(f"{f.name} : {exc}")
            continue
        barre.empty()
        resultats.append((res, sortie))

        with st.expander(f"📄 {res.infos.epn} – {res.periode.libelle}", expanded=len(fichiers) == 1):
            for a in res.doc.avertissements:
                st.warning(a)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Conformité de la forme", f"{res.score_forme:.0f} %")
            c1.caption(res.mention(res.score_forme))
            c2.metric("Fiabilité / cohérence", f"{res.score_fond:.0f} %" if res.score_fond is not None else "—")
            c2.caption(res.mention(res.score_fond))
            c3.metric("Anomalies majeures", res.nb_anomalies_majeures)
            c4.metric("Écart / date limite", f"{res.ecart_jours:+d} j" if res.ecart_jours is not None else "—")
            c4.caption(res.appreciation_delai)
            st.markdown("**Forme (partie II)**")
            st.dataframe(pd.DataFrame([{"Rubrique": l.libelle, "Statut": l.statut, "Précision": l.precision}
                                       for l in res.forme]), hide_index=True, use_container_width=True)
            if res.constats:
                st.markdown("**Constats automatiques**")
                st.dataframe(pd.DataFrame([{"Gravité": c.gravite, "Contrôle": c.controle, "Message": c.message}
                                           for c in res.constats]), hide_index=True, use_container_width=True)
            st.download_button("Télécharger le fichier d'analyse (.xlsx)", sortie.read_bytes(), sortie.name,
                               key=f"dl-{f.name}")

    if len(resultats) > 1:
        tdb = tableau_de_bord(resultats, tmp / "Tableau_de_bord_rapports_CB.xlsx")
        st.download_button("Télécharger le tableau de bord consolidé", tdb.read_bytes(), tdb.name, type="primary")
        # Archive de tous les fichiers d'analyse
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for _, s in resultats:
                z.write(s, s.name)
            z.write(tdb, tdb.name)
        st.download_button("Télécharger toutes les analyses (.zip)", buf.getvalue(), "analyses_rapports_CB.zip")
