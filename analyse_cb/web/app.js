/* Analyse des rapports des Contrôleurs Budgétaires – application (interface locale, sans dépendance externe) */
"use strict";

const JETON = new URLSearchParams(location.search).get("jeton") || "";
/* Les erreurs de l'interface sont consignées dans le journal de l'application. */
function signaler(message) {
  try { fetch("/api/journal", { method: "POST", headers: { "X-Jeton": JETON, "Content-Type": "application/json" }, body: JSON.stringify({ message: String(message).slice(0, 2000) }) }); } catch (_) { /* sans effet */ }
}
window.addEventListener("error", e => signaler(`${e.message} (${(e.filename || "").split("/").pop()}:${e.lineno}:${e.colno})`));
window.addEventListener("unhandledrejection", e => signaler((e.reason && (e.reason.stack || e.reason.message)) || e.reason));
const etat = { app: null, periode: null, analyse: { rapports: [], decrets: [], situations: [] }, suivi: null };

/* ------------------------------------------------------------------ icônes (24 × 24, trait) */
const ICONES = {
  accueil: "M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z",
  analyse: "M4 20V11M10 20V4M16 20v-8M21 20H3",
  comparaison: "M3 3v18h18M7 15l4-4 3 3 6-7",
  alerte: "M12 3.5 2.5 20h19zM12 10v4.5M12 17.4v.1",
  rapports: "M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8zM14 3v5h5M8.5 13h7M8.5 17h5",
  parametres: "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zM12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1",
  aide: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.3 9.2a2.8 2.8 0 0 1 5.4 1c0 1.9-2.7 2.3-2.7 4.2M12 17.4v.1",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.6v.1",
  utilisateur: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  quitter: "M9 21H5.5A1.5 1.5 0 0 1 4 19.5v-15A1.5 1.5 0 0 1 5.5 3H9M16 17l5-5-5-5M21 12H9",
  actualiser: "M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5",
  calendrier: "M4 6.5A1.5 1.5 0 0 1 5.5 5h13A1.5 1.5 0 0 1 20 6.5v12a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5zM4 10h16M8.5 3v4M15.5 3v4",
  base: "M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6",
  coche: "M5 12.5 9.5 17 19 7",
  pourcent: "M19 5 5 19M7 4.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5zM17 14.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z",
  cloche: "M6 9a6 6 0 1 1 12 0c0 6.5 2.5 8 2.5 8h-17S6 15.5 6 9zM10.2 20.5a2 2 0 0 0 3.6 0",
  ampoule: "M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.7.6 1.1 1.3 1.1 2.2h5c0-.9.4-1.6 1.1-2.2A6 6 0 0 0 12 3z",
  exclamation: "M12 6.5v7M12 17.3v.2",
  tableau: "M3.5 5h17v14h-17zM3.5 10h17M9.5 10v9M15 10v9",
  courbe: "M3 17l6-6 4 4 8-8M15 7h6v6",
  camembert: "M12 3v9h9M20.5 15.5A9 9 0 1 1 8.5 3.7",
  histogramme: "M3 21h18M6.5 17v-6M11.5 17V6M16.5 17v-9",
  depot: "M12 15V4M7.5 8.5 12 4l4.5 4.5M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15",
  fichier: "M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8zM14 3v5h5",
  dossier: "M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2h8.5A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z",
  ouvrir: "M14 3h7v7M21 3l-9 9M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5",
  lecture: "M7 4.5 19.5 12 7 19.5z",
  arret: "M6.5 6.5h11v11h-11z",
  corbeille: "M4 7h16M9.5 7V4h5v3M6 7l1 13.5h10L18 7",
  export: "M12 4v11M7.5 10.5 12 15l4.5-4.5M4 20h16",
  balance: "M12 4v16M5 20h14M4 8h16M7 8l-3 6a3 3 0 0 0 6 0zM17 8l-3 6a3 3 0 0 0 6 0z",
};
function icone(nom, extra = "") {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${extra}><path d="${ICONES[nom] || ""}"/></svg>`;
}

/* ------------------------------------------------------------------ outils */
const nf1 = new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
function esc(t) { return String(t ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function montant(v, u, avecUnite = true) { return v == null ? "—" : nf1.format(v / u.diviseur) + (avecUnite ? " " + u.libelle : ""); }
function pct(v) { return v == null ? "—" : nf1.format(v) + " %"; }
function signe(v, txt) { return (v > 0 ? "+" : v < 0 ? "−" : "") + txt; }
function dateFr(iso) { if (!iso) return "—"; const [a, m, j] = iso.slice(0, 10).split("-"); return `${j}/${m}/${a}`; }
function initiales(nom) { return (nom || "?").split(/\s+/).filter(Boolean).slice(0, 2).map(m => m[0].toUpperCase()).join(""); }

async function api(chemin, options = {}) {
  const r = await fetch(chemin, { ...options, headers: { "X-Jeton": JETON, ...(options.headers || {}) } });
  let d = {};
  try { d = await r.json(); } catch (_) { /* réponse vide */ }
  if (!r.ok || d.erreur) throw new Error(d.erreur || `Erreur ${r.status}`);
  return d;
}
const post = (chemin, data) => api(chemin, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}) });

function toast(message, type = "") {
  const t = document.createElement("div");
  t.className = "toast " + type;
  t.textContent = message;
  document.getElementById("toasts").appendChild(t);
  setTimeout(() => t.remove(), type === "erreur" ? 7000 : 4000);
}
const contenu = () => document.getElementById("contenu");

/* ------------------------------------------------------------------ navigation */
const PAGES = [
  ["tableau", "Tableau de bord", "accueil"],
  ["analyse", "Analyse des rapports", "analyse"],
  ["comparaison", "Comparaison budgétaire", "comparaison"],
  ["ratios", "Analyse des ratios", "pourcent"],
  ["alertes", "Alertes & Anomalies", "alerte"],
  ["rapports", "Rapports détaillés", "rapports"],
  ["parametres", "Paramètres", "parametres"],
  ["aide", "Aide", "aide"],
  ["apropos", "À propos", "utilisateur"],
];
function construireNav() {
  document.getElementById("nav").innerHTML = PAGES.map(([id, lib, ic]) =>
    `<a href="#/${id}" data-page="${id}">${icone(ic)}<span>${lib}</span>${id === "alertes" ? '<span class="badge" id="badge" hidden></span>' : ""}</a>`).join("");
  document.getElementById("quitter").innerHTML = icone("quitter") + "<span>Quitter l'application</span>";
  document.getElementById("quitter").onclick = quitter;
}
function majBadge(n) {
  const b = document.getElementById("badge");
  if (!b) return;
  b.hidden = !n;
  b.textContent = n > 99 ? "99+" : n;
}
async function majEnvironnement() {
  try {
    const e = await api("/api/etat");
    etat.app = e;
    document.getElementById("inst1").textContent = e.institution.ligne1 || "";
    document.getElementById("inst2").textContent = e.institution.ligne2 || "";
    document.getElementById("logo").innerHTML = e.logo
      ? `<img src="/api/logo?jeton=${encodeURIComponent(JETON)}&t=${Date.now()}" alt="Logo de l'institution">`
      : `<div class="logo-defaut">${icone("analyse", 'style="width:40px;height:40px"')}</div>`;
    document.getElementById("profil-nom").textContent = e.utilisateur.nom || "Profil à compléter";
    document.getElementById("profil-role").textContent = e.utilisateur.fonction || "Chargé d'Études";
    document.getElementById("avatar").textContent = e.utilisateur.nom ? initiales(e.utilisateur.nom) : "";
    if (!e.utilisateur.nom) document.getElementById("avatar").innerHTML = icone("utilisateur", 'style="width:20px;height:20px"');
    majBadge(e.badge);
  } catch (err) { toast(err.message, "erreur"); }
}
async function router() {
  const page = (location.hash.replace(/^#\/?/, "") || "tableau").split("?")[0];
  document.querySelectorAll(".nav a").forEach(a => a.classList.toggle("actif", a.dataset.page === page));
  const rendu = { tableau: pageTableau, analyse: pageAnalyse, comparaison: pageComparaison, ratios: pageRatios, alertes: pageAlertes,
    rapports: pageRapports, parametres: pageParametres, aide: pageAide, apropos: pageAPropos }[page] || pageTableau;
  try { await rendu(); } catch (err) { contenu().innerHTML = videHtml("alerte", "Une erreur est survenue", esc(err.message)); }
  contenu().focus();
}
async function quitter() {
  let enCours = false;
  try { enCours = !!(await api("/api/travail")).en_cours; } catch (_) { /* serveur déjà arrêté */ }
  if (enCours && !confirm("Une analyse est en cours. Quitter quand même ?")) return;
  try { await post("/api/quitter"); } catch (_) { /* déjà arrêté */ }
  fermerFenetre();
}

/* ------------------------------------------------------------------ présence de la fenêtre
   L'application reste ouverte tant qu'une fenêtre de l'interface l'est : chaque fenêtre se signale régulièrement et
   prévient de sa fermeture ; elle se ferme si l'application a été quittée. */
const PAGE = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2);
let fermee = false;
function fermerFenetre() {
  if (fermee) return;
  fermee = true;
  document.body.innerHTML = '<div class="vide"><h3>Application fermée</h3><p>Vous pouvez fermer cette fenêtre.</p></div>';
  window.close();
}
async function presence() {
  if (fermee) return;
  try {
    const r = await fetch("/api/presence?page=" + PAGE, { method: "POST", headers: { "X-Jeton": JETON } });
    if ((await r.json()).quitter) fermerFenetre();
  } catch (_) { /* application arrêtée */ }
}
window.addEventListener("pagehide", () => {
  try { navigator.sendBeacon(`/api/fermeture?jeton=${encodeURIComponent(JETON)}&page=${PAGE}`); } catch (_) { /* sans effet */ }
});
window.addEventListener("beforeunload", e => { if (etat.sondage && !fermee) { e.preventDefault(); e.returnValue = ""; } });
/* Navigation sans ajout à l'historique : la fenêtre peut ainsi être fermée par « Quitter l'application ». */
document.addEventListener("click", e => {
  const a = e.target.closest && e.target.closest('a[href^="#/"]');
  if (!a || e.ctrlKey || e.shiftKey || e.metaKey) return;
  e.preventDefault();
  if (location.hash !== a.getAttribute("href")) location.replace(a.getAttribute("href"));
});

/* ------------------------------------------------------------------ éléments communs */
function entete(titre, sous, actions = "") {
  return `<div class="entete"><div><h1>${titre}</h1><div class="sous">${sous}</div></div><div class="actions">${actions}</div></div>`;
}
function choixPeriode(periodes, actuelle, avecToutes = false) {
  const opts = (avecToutes ? [`<option value="">Toutes les périodes</option>`] : [])
    .concat(periodes.map(p => `<option value="${p.cle}" ${p.cle === actuelle ? "selected" : ""}>${esc(p.libelle)}</option>`));
  return `<div class="choix-periode">${icone("calendrier")}<label for="periode">Période :</label><select id="periode">${opts.join("")}</select></div>`;
}
function brancherPeriode(rafraichir) {
  const s = document.getElementById("periode");
  if (s) s.onchange = () => { etat.periode = s.value || null; rafraichir(); };
}
function videHtml(ic, titre, texte, bouton = "") {
  return `<div class="panneau vide">${icone(ic)}<h3>${titre}</h3><p>${texte}</p>${bouton}</div>`;
}
const BOUTON_ANALYSER = `<a class="bouton primaire" href="#/analyse">${icone("depot")}Analyser des rapports</a>`;
function statutHtml(texte, couleur) { return `<span class="statut ${couleur}">${esc(texte)}</span>`; }

/* ------------------------------------------------------------------ graphiques SVG */
/* Chaque graphique est dessiné à la largeur réelle de son panneau (texte lisible), puis redessiné si la fenêtre change de taille. */
const DESSINS = new Map();
function graphique(el, dessin) {
  if (!el) return;
  const rendre = () => { el.innerHTML = dessin(Math.max(300, Math.round(el.clientWidth || 600))); };
  DESSINS.set(el, rendre);
  rendre();
}
window.addEventListener("resize", () => {
  clearTimeout(etat.redimension);
  etat.redimension = setTimeout(() => DESSINS.forEach((rendre, el) => { if (document.body.contains(el)) rendre(); else DESSINS.delete(el); }), 120);
});
function arrondiHaut(v) {
  if (!v || v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v - 1e-9) return m * p;
  return 10 * p;
}
const TXT = 'font-family="Segoe UI, Inter, system-ui, sans-serif"';
function svgBarresCourbe(points, u, L) {
  const H = 270, g = 46, d = 46, h = 18, b = 30, lw = L - g - d, lh = H - h - b;
  const vals = points.map(p => (p.credits || 0) / u.diviseur);
  const max = arrondiHaut(Math.max(...vals, 0) * 1.45);
  const taux = points.map(p => p.taux).filter(t => t != null);
  const tmax = Math.max(100, ...taux.map(t => Math.ceil(t / 20) * 20));
  const y = v => h + lh - (v / max) * lh, yt = t => h + lh - (t / tmax) * lh;
  const bande = lw / Math.max(points.length, 1), lb = Math.min(64, bande * 0.5);
  let s = `<svg viewBox="0 0 ${L} ${H}" width="${L}" height="${H}" ${TXT} role="img" aria-label="Évolution de l'exécution budgétaire">`;
  for (let i = 0; i <= 5; i++) {
    const yy = h + lh - lh * i / 5;
    s += `<line x1="${g}" x2="${L - d}" y1="${yy}" y2="${yy}" stroke="#e8edf3"/>`;
    s += `<text x="${g - 7}" y="${yy + 4}" text-anchor="end" font-size="11.5" fill="#56657a">${nf0.format(max * i / 5)}</text>`;
    s += `<text x="${L - d + 7}" y="${yy + 4}" font-size="11.5" fill="#56657a">${nf0.format(tmax * i / 5)} %</text>`;
  }
  const centres = points.map((p, i) => g + bande * (i + 0.5));
  /* Étiquette du taux au-dessus du point ; si elle masque la valeur de la barre, la valeur passe dans la barre,
     ou l'étiquette passe sous le point. */
  const chevauche = (a, b) => a[0] < b[1] && a[1] > b[0];
  const boites = [];
  points.forEach((p, i) => {
    const cx = centres[i], v = vals[i], top = y(v), haut = h + lh - top;
    const yp = p.taux == null ? null : yt(p.taux);
    let ly = yp == null ? null : Math.max(2, yp - 34), dedans = false;
    const zone = l => [Math.min(l, yp - 8), Math.max(l + 22, yp + 8)];  // étiquette + point
    const dessus = [top - 20, top - 2], dessous = [top + 3, top + 22];
    if (yp != null && chevauche(zone(ly), dessus)) {
      if (haut > 26 && !chevauche(zone(ly), dessous)) dedans = true;
      else {
        ly = yp + 11;
        if (chevauche(zone(ly), dessus) && haut > 26 && !chevauche(zone(ly), dessous)) dedans = true;
      }
    }
    boites.push(ly);
    s += `<rect x="${cx - lb / 2}" y="${top}" width="${lb}" height="${haut}" fill="#1565d8" rx="3"/>`;
    s += dedans ? `<text x="${cx}" y="${top + 17}" text-anchor="middle" font-size="12.5" font-weight="700" fill="#fff">${nf1.format(v)}</text>`
                : `<text x="${cx}" y="${top - 7}" text-anchor="middle" font-size="12.5" font-weight="700" fill="#0f1e36">${nf1.format(v)}</text>`;
    s += `<text x="${cx}" y="${H - 9}" text-anchor="middle" font-size="12.5" fill="#0f1e36">${esc(p.libelle)}</text>`;
  });
  const pts = points.map((p, i) => p.taux == null ? null : [centres[i], yt(p.taux), p.taux, boites[i]]).filter(Boolean);
  if (pts.length > 1) s += `<polyline points="${pts.map(q => q[0] + "," + q[1]).join(" ")}" fill="none" stroke="#1f9d4c" stroke-width="3" stroke-linejoin="round"/>`;
  pts.forEach(([x, yy, t, ly]) => {
    const lab = nf1.format(t) + " %", w = lab.length * 7.4 + 14;
    s += `<rect x="${x - w / 2}" y="${ly}" width="${w}" height="22" rx="6" fill="#1f9d4c"/>`;
    s += `<text x="${x}" y="${ly + 15.5}" text-anchor="middle" font-size="12.5" font-weight="700" fill="#fff">${lab}</text>`;
    s += `<circle cx="${x}" cy="${yy}" r="5.5" fill="#fff" stroke="#1f9d4c" stroke-width="3"/>`;
  });
  return s + "</svg>";
}
const COULEURS = ["#1565d8", "#f59e0b", "#1f9d4c", "#9b59b6", "#a0aec0", "#e03b3b"];
function svgGroupes(donnees, u, L) {
  const H = 260, g = 46, d = 10, h = 22, b = 36, lw = L - g - d, lh = H - h - b;
  const max = arrondiHaut(Math.max(...donnees.flatMap(x => [(x.prevu || 0) / u.diviseur, (x.realise || 0) / u.diviseur]), 0) * 1.15);
  const y = v => h + lh - (v / max) * lh;
  const bande = lw / Math.max(donnees.length, 1), lb = Math.min(40, bande * 0.32);
  const car = Math.max(6, Math.floor(bande / 7.2));
  let s = `<svg viewBox="0 0 ${L} ${H}" width="${L}" height="${H}" ${TXT} role="img" aria-label="Prévu et réalisé">`;
  for (let i = 0; i <= 4; i++) {
    const v = max * i / 4;
    s += `<line x1="${g}" x2="${L - d}" y1="${y(v)}" y2="${y(v)}" stroke="#e8edf3"/><text x="${g - 7}" y="${y(v) + 4}" text-anchor="end" font-size="11.5" fill="#56657a">${nf0.format(v)}</text>`;
  }
  donnees.forEach((x, i) => {
    const cx = g + bande * (i + 0.5);
    [[x.prevu, "#1565d8", -1], [x.realise, "#f59e0b", 1]].forEach(([val, coul, cote]) => {
      const v = (val || 0) / u.diviseur, bx = cx + (cote < 0 ? -lb - 2 : 2);
      s += `<rect x="${bx}" y="${y(v)}" width="${lb}" height="${h + lh - y(v)}" fill="${coul}" rx="2"/>`;
      s += `<text x="${bx + lb / 2}" y="${y(v) - 6}" text-anchor="middle" font-size="11.5" font-weight="700" fill="#0f1e36">${nf1.format(v)}</text>`;
    });
    const lib = x.libelle.length > car ? x.libelle.slice(0, car - 1) + "…" : x.libelle;
    s += `<text x="${cx}" y="${H - 12}" text-anchor="middle" font-size="12" fill="#0f1e36"><title>${esc(x.libelle)}</title>${esc(lib)}</text>`;
  });
  return s + `<line x1="${g}" x2="${L - d}" y1="${h + lh}" y2="${h + lh}" stroke="#9aa6b5"/></svg>`;
}
function svgCourbe(points, L) {
  const H = 220, g = 46, d = 20, h = 26, b = 30, lw = L - g - d, lh = H - h - b;
  const ts = points.map(p => p.taux).filter(t => t != null);
  const max = Math.max(100, ...ts.map(t => Math.ceil(t / 20) * 20));
  const y = t => h + lh - (t / max) * lh, pas = lw / Math.max(points.length, 1);
  let s = `<svg viewBox="0 0 ${L} ${H}" width="${L}" height="${H}" ${TXT} role="img" aria-label="Évolution du taux d'exécution">`;
  for (let i = 0; i <= 4; i++) {
    const v = max * i / 4;
    s += `<line x1="${g}" x2="${L - d}" y1="${y(v)}" y2="${y(v)}" stroke="#e8edf3"/><text x="${g - 7}" y="${y(v) + 4}" text-anchor="end" font-size="11.5" fill="#56657a">${nf0.format(v)} %</text>`;
  }
  const pts = points.map((p, i) => [g + pas * (i + 0.5), p.taux == null ? null : y(p.taux), p]);
  const traces = pts.filter(q => q[1] != null);
  if (traces.length > 1) s += `<polyline points="${traces.map(q => q[0] + "," + q[1]).join(" ")}" fill="none" stroke="#1565d8" stroke-width="3" stroke-linejoin="round"/>`;
  pts.forEach(([x, yy, p]) => {
    s += `<text x="${x}" y="${H - 9}" text-anchor="middle" font-size="12.5" fill="#0f1e36">${esc(p.periode)}</text>`;
    if (yy != null) s += `<circle cx="${x}" cy="${yy}" r="5" fill="#fff" stroke="#1565d8" stroke-width="3"/><text x="${x}" y="${yy - 11}" text-anchor="middle" font-size="12.5" font-weight="700" fill="#0f1e36">${pct(p.taux)}</text>`;
  });
  return s + "</svg>";
}

/* ------------------------------------------------------------------ 1. tableau de bord */
function variationHtml(v, comp, points = false, inverse = false) {
  if (v == null) return `<div class="delta">${comp ? "Sans comparaison" : "Première période analysée"}</div>`;
  const bon = inverse ? v < 0 : v >= 0;
  const fl = v >= 0 ? "↑" : "↓";
  const txt = points ? nf1.format(Math.abs(v)) + " pt" : nf1.format(Math.abs(v)) + " %";
  return `<div class="delta"><span class="${bon ? "hausse" : "baisse"}">${fl} ${signe(v, txt)}</span> ${esc(comp)}</div>`;
}
function carteKpi(ic, fond, libelle, valeur, delta) {
  return `<div class="kpi"><div class="icone ${fond}">${icone(ic)}</div><div style="min-width:0"><div class="libelle">${libelle}</div><div class="valeur">${valeur}</div>${delta}</div></div>`;
}
async function pageTableau() {
  const d = await api("/api/tableau" + (etat.periode ? "?periode=" + encodeURIComponent(etat.periode) : ""));
  if (d.vide) {
    contenu().innerHTML = entete("Tableau de bord", "Analyse des rapports des contrôleurs budgétaires")
      + videHtml("analyse", "Aucun rapport analysé pour le moment", "Analysez les rapports des Contrôleurs Budgétaires : le tableau de bord se remplit automatiquement.", BOUTON_ANALYSER);
    return;
  }
  etat.periode = d.periode.cle;
  majBadge(d.badge);
  const u = d.unite, k = d.kpi, c = d.comparaison;
  const actions = choixPeriode(d.periodes, d.periode.cle)
    + `<button class="bouton" id="exporter">${icone("export")}Exporter</button>`
    + `<button class="bouton primaire" id="actualiser">${icone("actualiser")}Actualiser</button>`;
  const sousExec = d.lignes.filter(l => l.statut === "Sous-exécution" || l.statut === "À surveiller").length;
  const kpis = `<div class="kpis">
    ${carteKpi("base", "fond-bleu", "Crédits budgétaires", montant(k.credits, u), variationHtml(c.credits, c.libelle))}
    ${carteKpi("coche", "fond-vert", "Exécution budgétaire", montant(k.execution, u), variationHtml(c.execution, c.libelle))}
    ${carteKpi("pourcent", "fond-orange", "Taux d'exécution", pct(k.taux), variationHtml(c.taux, c.libelle, true))}
    ${carteKpi("alerte", "fond-rouge", "Écarts à analyser", montant(k.ecarts, u),
      c.ecarts != null ? variationHtml(c.ecarts, c.libelle, false, true) : `<div class="delta">${sousExec} EPN à suivre sur ${k.epn}</div>`)}
  </div>`;

  const evolution = `<div class="panneau"><h2>${icone("histogramme")}Évolution de l'exécution budgétaire</h2>
    <div class="legende"><span><i style="background:#1565d8"></i>Crédits (${esc(u.libelle)})</span><span><i class="rond" style="background:#1f9d4c"></i>Taux d'exécution (%)</span></div>
    <div class="graphique" id="graph-evolution-tdb"></div></div>`;

  const panneauRatios = panneauRatiosHtml(d.ratios);

  const sy = d.synthese;
  const points = sy.points.map(p => {
    const ic = p.niveau === "critique" ? "exclamation" : p.niveau === "attention" ? "alerte" : "info";
    let detail = esc(p.texte || "");
    if (p.valeur != null) detail = `${esc(p.texte)} : ${signe(p.valeur, montant(Math.abs(p.valeur), u))}`;
    if (p.taux != null) detail = `${pct(p.taux)} (objectif ≥ ${nf0.format(p.objectif)} %)`;
    return `<div class="point"><span class="pastille ${p.niveau}">${icone(ic)}</span><div><div class="titre">${esc(p.titre)}</div><div class="detail">${detail}</div></div></div>`;
  }).join("");
  const synthese = `<div class="panneau alertes-panneau"><div class="tete">${icone("cloche")}Synthèse & Alertes</div>${points || '<div class="point"><div class="detail">Aucune alerte pour cette période.</div></div>'}
    <div class="reco">${icone("ampoule")}<div><div class="titre">Recommandation</div><div class="detail">${esc(sy.recommandation)}</div></div></div></div>`;

  const tot = d.kpi;
  const ecartHtml = v => v == null ? "—" : signe(v, nf1.format(Math.abs(v) / u.diviseur));
  const ligneHtml = (l, parEpn) => `<tr ${parEpn ? `class="cliquable" data-id="${l.id}" title="Voir l'analyse du rapport"` : ""}>
      <td class="texte"><b>${esc(parEpn ? l.court : l.libelle)}</b><div class="sous-ligne">${esc(parEpn ? l.tutelle : `${l.epn} EPN`)}</div></td>
      <td>${montant(l.credits, u, false)}</td><td>${montant(l.execution, u, false)}</td>
      <td class="${l.statut === "OK" ? "taux-ok" : l.statut === "Non renseigné" ? "" : "taux-ko"}">${pct(l.taux)}</td>
      <td>${ecartHtml(l.ecart)}</td><td class="centre">${statutHtml(l.statut, l.couleur)}</td></tr>`;
  const ligneTotal = `<tr class="total"><td class="texte">Total</td><td>${montant(tot.credits, u, false)}</td><td>${montant(tot.execution, u, false)}</td><td>${pct(tot.taux)}</td><td>${ecartHtml(tot.ecart_net)}</td><td class="centre">–</td></tr>`;
  const sources = [...new Set(d.lignes.map(l => l.source).filter(Boolean))];
  const detail = `<div class="panneau"><h2>${icone("tableau")}<span id="titre-detail">Détail par EPN</span>
      <span class="droite onglets compact" id="onglets-detail"><button data-v="epn" class="actif">EPN</button><button data-v="ministere">Ministère</button></span></h2>
    <div class="defilant"><table class="donnees"><thead><tr><th id="col-detail">EPN</th><th>Crédits<small>${esc(u.libelle)}</small></th><th>Exécution<small>${esc(u.libelle)}</small></th><th>Taux<small>%</small></th><th>Écart<small>${esc(u.libelle)}</small></th><th>Statut</th></tr></thead>
    <tbody id="corps-detail"></tbody></table></div>
    <p class="aide" style="margin:10px 0 0">Source des montants : ${esc(sources.join(" ; ") || "—")}. Taux attendu à la fin de la période : ${nf0.format(d.attendu)} % (statut « OK » à partir de ${nf0.format(d.objectif)} %).</p></div>`;

  const graph = `<div class="panneau"><h2>${icone("courbe")}Graphique d'analyse</h2>
    <div class="onglets" id="onglets-graph"><button data-g="epn" class="actif">Par EPN</button><button data-g="nature">Par nature de dépense</button></div>
    <div class="legende" style="justify-content:flex-end"><span><i style="background:#1565d8"></i>Prévu</span><span><i style="background:#f59e0b"></i>Réalisé</span></div>
    <div class="graphique" id="graph-analyse"></div></div>`;

  contenu().innerHTML = entete("Tableau de bord", "Analyse des rapports des contrôleurs budgétaires", actions)
    + kpis + `<div class="grille-3">${evolution}${panneauRatios}${synthese}</div>` + `<div class="grille-2">${detail}${graph}</div>`
    + panneauDifficultesHtml(d.difficultes);
  brancherDifficultes();

  const dessiner = cle => {
    const donnees = d.graphiques[cle] || [];
    const el = document.getElementById("graph-analyse");
    if (donnees.length) graphique(el, L => svgGroupes(donnees, u, L));
    else { DESSINS.delete(el); el.innerHTML = `<p class="aide">Données non disponibles pour cette vue.</p>`; }
    document.querySelectorAll("#onglets-graph button").forEach(b => b.classList.toggle("actif", b.dataset.g === cle));
  };
  graphique(document.getElementById("graph-evolution-tdb"), L => svgBarresCourbe(d.evolution, u, L));
  dessiner("epn");
  document.querySelectorAll("#onglets-graph button").forEach(b => b.onclick = () => dessiner(b.dataset.g));
  const vueDetail = v => {
    const parEpn = v === "epn";
    document.getElementById("corps-detail").innerHTML = (parEpn ? d.lignes : d.ministeres).map(l => ligneHtml(l, parEpn)).join("") + ligneTotal;
    document.getElementById("titre-detail").textContent = parEpn ? "Détail par EPN" : "Détail par ministère";
    document.getElementById("col-detail").textContent = parEpn ? "EPN" : "Ministère de tutelle";
    document.querySelectorAll("#onglets-detail button").forEach(b => b.classList.toggle("actif", b.dataset.v === v));
    document.querySelectorAll("#corps-detail tr.cliquable").forEach(tr => tr.onclick = () => ouvrirRapport(+tr.dataset.id));
  };
  vueDetail("epn");
  document.querySelectorAll("#onglets-detail button").forEach(b => b.onclick = () => vueDetail(b.dataset.v));
  brancherPeriode(pageTableau);
  document.getElementById("actualiser").onclick = async () => { await majEnvironnement(); await pageTableau(); toast("Tableau de bord actualisé."); };
  document.getElementById("exporter").onclick = async () => {
    try { const r = await post("/api/exporter", { periode: etat.periode }); toast("Tableau de bord exporté : " + r.chemin); }
    catch (err) { toast(err.message, "erreur"); }
  };
}

/* ------------------------------------------------------------------ ratios de gestion */
const COUL_RATIOS = { RRP: "#1f9d4c", RDP: "#9b59b6", RDF: "#f59e0b", RDI: "#1565d8", RDA: "#a0aec0" };
const FOND_RATIOS = { RRP: "fond-vert", RDP: "fond-violet", RDF: "fond-orange", RDI: "fond-bleu", RDA: "fond-gris" };
const COUL_CATEGORIES = { personnel: "#9b59b6", biens_services: "#f59e0b", transferts: "#14a3a3", investissement: "#1565d8", autres: "#a0aec0" };
function pluriel(n, mot) { return `${n} ${mot}${n > 1 ? "s" : ""}`; }
function variationPoints(v) {
  return v == null ? "" : `<small class="neutre">${v >= 0 ? "↑" : "↓"} ${signe(v, nf1.format(Math.abs(v)) + " pt")}</small>`;
}
function jaugesRatios(liste) {
  return liste.map(x => `<div class="ratio" title="${esc(x.libelle)} : ${esc(x.formule)}">
      <div class="ratio-tete"><span><b>${x.code}</b> ${esc(x.court)}</span>
        <span class="ratio-val">${x.valeur == null ? '<span class="nc">non calculable</span>' : pct(x.valeur)} ${variationPoints(x.variation)}</span></div>
      <div class="jauge"><i style="width:${Math.max(0, Math.min(100, x.valeur || 0))}%;background:${COUL_RATIOS[x.code]}"></i></div></div>`).join("");
}
function citationsHtml(c) {
  if (!c || !c.rapports) return "";
  const parts = [];
  if (c.concordants) parts.push(`<span><i class="puce-c vert"></i>${pluriel(c.concordants, "concordant")}</span>`);
  if (c.discordants) parts.push(`<span><i class="puce-c rouge"></i>${pluriel(c.discordants, "discordant")}</span>`);
  if (c.non_verifiables) parts.push(`<span><i class="puce-c gris"></i>${pluriel(c.non_verifiables, "non vérifiable")}</span>`);
  if (c.rapports_sans_ratio) parts.push(`<span><i class="puce-c orange"></i>${c.rapports_sans_ratio === c.rapports && c.rapports === 1 ? "aucun ratio cité" : `${pluriel(c.rapports_sans_ratio, "rapport")} sans ratio cité`}</span>`);
  return `<div class="citations"><div class="titre">Ratios cités par les CB</div><div class="ligne">${parts.join("")}</div></div>`;
}
function panneauRatiosHtml(r) {
  const tete = `<h2>${icone("pourcent")}Analyse des ratios<a class="droite lien-detail" href="#/ratios">Voir le détail</a></h2>`;
  if (!r || !r.disponibles) {
    return `<div class="panneau">${tete}<p class="aide" style="margin:0">Ratios non disponibles pour cette période : relancez l'analyse des rapports avec cette version de l'application.</p></div>`;
  }
  const manque = r.rapports - r.disponibles;
  return `<div class="panneau">${tete}${jaugesRatios(r.agreges.filter(x => x.code !== "RDA" || x.valeur != null))}${citationsHtml(r.citations)}
    <p class="aide pied">Ensemble des EPN, pondéré par les montants. Base : ${esc(r.bases.join(", "))} ; source : ${esc(r.sources.join(", "))}.${manque ? ` ${pluriel(manque, "rapport")} à réanalyser.` : ""}</p></div>`;
}
function svgStructure(lignes, L) {
  const rows = lignes.filter(l => l.structure.length);
  const h0 = 24, hb = 24, ecart = 16, g = Math.min(150, Math.round(L * 0.26)), d = 14, lw = L - g - d;
  const H = h0 + rows.length * (hb + ecart);
  let s = `<svg viewBox="0 0 ${L} ${H}" width="${L}" height="${H}" ${TXT} role="img" aria-label="Structure des dépenses">`;
  [0, 25, 50, 75, 100].forEach(t => {
    const x = g + lw * t / 100;
    s += `<line x1="${x}" x2="${x}" y1="${h0 - 4}" y2="${H - ecart + 4}" stroke="#e8edf3"/><text x="${x}" y="${h0 - 9}" text-anchor="middle" font-size="11" fill="#56657a">${t} %</text>`;
  });
  const car = Math.max(8, Math.floor(g / 7.5));
  rows.forEach((l, i) => {
    const y = h0 + i * (hb + ecart);
    const nom = l.court.length > car ? l.court.slice(0, car - 1) + "…" : l.court;
    s += `<text x="${g - 8}" y="${y + hb / 2 + 4}" text-anchor="end" font-size="12.5" font-weight="600" fill="#0f1e36"><title>${esc(l.epn)}</title>${esc(nom)}</text>`;
    let x = g;
    l.structure.forEach(seg => {
      const w = Math.max(0, lw * seg.part / 100);
      s += `<rect x="${x}" y="${y}" width="${w}" height="${hb}" fill="${COUL_CATEGORIES[seg.cle] || "#a0aec0"}"><title>${esc(seg.libelle)} : ${pct(seg.part)}</title></rect>`;
      if (w > 38) s += `<text x="${x + w / 2}" y="${y + hb / 2 + 4}" text-anchor="middle" font-size="11.5" font-weight="700" fill="#fff">${nf0.format(seg.part)} %</text>`;
      x += w;
    });
  });
  return s + "</svg>";
}
function svgCourbes(points, codes, L) {
  const H = 240, g = 46, d = 18, h = 18, b = 30, lw = L - g - d, lh = H - h - b;
  const y = v => h + lh - (v / 100) * lh, pas = lw / Math.max(points.length, 1);
  let s = `<svg viewBox="0 0 ${L} ${H}" width="${L}" height="${H}" ${TXT} role="img" aria-label="Évolution des ratios">`;
  for (let i = 0; i <= 4; i++) {
    const v = 25 * i;
    s += `<line x1="${g}" x2="${L - d}" y1="${y(v)}" y2="${y(v)}" stroke="#e8edf3"/><text x="${g - 7}" y="${y(v) + 4}" text-anchor="end" font-size="11.5" fill="#56657a">${v} %</text>`;
  }
  points.forEach((p, i) => { s += `<text x="${g + pas * (i + 0.5)}" y="${H - 9}" text-anchor="middle" font-size="12.5" fill="#0f1e36">${esc(p.periode)}</text>`; });
  const etiquettes = [];
  codes.forEach(code => {
    const pts = points.map((p, i) => p[code] == null ? null : [g + pas * (i + 0.5), y(p[code]), p[code]]).filter(Boolean);
    if (pts.length > 1) s += `<polyline points="${pts.map(q => q[0] + "," + q[1]).join(" ")}" fill="none" stroke="${COUL_RATIOS[code]}" stroke-width="2.5" stroke-linejoin="round"/>`;
    pts.forEach(([x, yy, v]) => { s += `<circle cx="${x}" cy="${yy}" r="4.5" fill="#fff" stroke="${COUL_RATIOS[code]}" stroke-width="2.5"><title>${code} : ${pct(v)}</title></circle>`; });
    const dernier = pts[pts.length - 1];
    if (dernier) etiquettes.push({ code, x: dernier[0] + 9, y: dernier[1] + 4 });
  });
  etiquettes.sort((a, b) => a.y - b.y);  // étiquettes espacées d'au moins 13 px
  for (let i = 1; i < etiquettes.length; i++) if (etiquettes[i].y - etiquettes[i - 1].y < 13) etiquettes[i].y = etiquettes[i - 1].y + 13;
  etiquettes.forEach(e => { s += `<text x="${e.x}" y="${e.y}" font-size="11.5" font-weight="700" fill="${COUL_RATIOS[e.code]}">${e.code}</text>`; });
  return s + "</svg>";
}
function insecable(t) { return esc(t).replace(/ (%|FCFA|:|;|\?|!)/g, "\u00a0$1").replace(/(n°) /g, "$1\u00a0"); }
function celluleRatio(x) {
  if (!x) return `<td class="centre">—</td>`;
  let html = x.valeur == null ? '<span class="nc">—</span>' : `<b>${pct(x.valeur)}</b>`;
  if (x.cite != null) {
    const [cls, lib] = x.coherent === true ? ["ok", "concordant"] : x.coherent === false ? ["ko", "discordant"] : ["nv", "non vérifiable"];
    html += `<div class="cite ${cls}" title="${esc(x.phrase || "")}">cité ${pct(x.cite)} · ${lib}</div>`;
  }
  if (x.rapport != null && x.valeur != null && Math.abs(x.rapport - x.valeur) >= 0.5) html += `<div class="cite nv">tableaux : ${pct(x.rapport)}</div>`;
  return `<td class="centre">${html}</td>`;
}

/* ------------------------------------------------------------------ difficultés et suggestions */
const CATEGORIES_DS = [{ code: "execution", libelle: "Exécution du budget" }, { code: "controle", libelle: "Contrôle de l'exécution du budget" },
  { code: "gestion", libelle: "Gestion de l'établissement" }];
function tronquer(t, n) { t = String(t || ""); return t.length > n ? t.slice(0, n - 1).replace(/\s+\S*$/, "") + "…" : t; }
function listeDsHtml(elements, categories, avecEpn) {
  return categories.map(cat => ({ ...cat, items: elements.filter(e => e.categorie === cat.code) })).filter(g => g.items.length)
    .map(g => `<div class="groupe-ds"><div class="cat-ds">${esc(g.libelle)} <span>(${g.items.length})</span></div><ul>${g.items.map((e, i) =>
      `<li class="${i >= 3 && avecEpn ? "masque" : ""}" ${avecEpn ? `data-id="${e.id}" title="Voir l'analyse du rapport"` : ""}><span class="texte-ds">${insecable(avecEpn ? tronquer(e.texte, 280) : e.texte)}</span>${avecEpn ? `<span class="epn-ds">${esc(e.court)}</span>` : ""}</li>`).join("")}</ul>
      ${avecEpn && g.items.length > 3 ? `<button class="lien voir-plus" type="button">${g.items.length === 4 ? "Voir le quatrième" : `Voir les ${g.items.length - 3} autres`}</button>` : ""}</div>`).join("");
}
function panneauDifficultesHtml(ds) {
  const n = ds ? ds.difficultes.length : 0, m = ds ? ds.suggestions.length : 0;
  const resume = ds && ds.rapports ? `${pluriel(n, "difficulté")} · ${pluriel(m, "suggestion")} · ${pluriel(ds.rapports, "rapport")}` : "";
  const tete = `<h2>${icone("ampoule")}Difficultés et suggestions des Contrôleurs Budgétaires<span class="droite aide" style="margin:0">${resume}</span></h2>`;
  if (!ds || !ds.rapports) {
    return `<div class="panneau ds">${tete}<p class="aide" style="margin:0">Non disponibles pour cette période : relancez l'analyse des rapports avec cette version de l'application.</p></div>`;
  }
  const colonne = (cle, titre, vide) => `<div class="colonne-ds ${cle}"><h3>${titre} <span class="compteur">${ds[cle].length}</span></h3>
    ${ds[cle].length ? listeDsHtml(ds[cle], ds.categories, true) : `<p class="aide" style="margin:0">${vide}</p>`}</div>`;
  const notes = [];
  if (ds.sans_difficultes.length && n) notes.push(`Aucune difficulté signalée : ${esc(ds.sans_difficultes.join(", "))}.`);
  if (ds.sans_suggestions.length && m) notes.push(`Aucune suggestion formulée : ${esc(ds.sans_suggestions.join(", "))}.`);
  if (ds.a_reanalyser) notes.push(`${pluriel(ds.a_reanalyser, "rapport")} analysé${ds.a_reanalyser > 1 ? "s" : ""} avec une version antérieure : relancez l'analyse pour l'inclure.`);
  return `<div class="panneau ds">${tete}<div class="grille-ds">
      ${colonne("difficultes", "Difficultés", "Aucune difficulté signalée par les Contrôleurs Budgétaires.")}
      ${colonne("suggestions", "Suggestions", "Aucune suggestion formulée par les Contrôleurs Budgétaires.")}</div>
    ${notes.length ? `<p class="aide pied">${notes.join(" ")}</p>` : ""}</div>`;
}
function brancherDifficultes() {
  document.querySelectorAll(".ds li[data-id]").forEach(li => li.onclick = () => ouvrirRapport(+li.dataset.id));
  document.querySelectorAll(".ds .voir-plus").forEach(b => b.onclick = () => {
    b.parentElement.querySelectorAll("li.masque").forEach(li => li.classList.remove("masque"));
    b.remove();
  });
}

/* ------------------------------------------------------------------ analyse des ratios */
async function pageRatios() {
  const d = await api("/api/ratios" + (etat.periode ? "?periode=" + encodeURIComponent(etat.periode) : ""));
  if (d.vide) {
    contenu().innerHTML = entete("Analyse des ratios", "Ratios de gestion du canevas") + videHtml("pourcent", "Aucune donnée", "Analysez d'abord des rapports.", BOUTON_ANALYSER);
    return;
  }
  etat.periode = d.periode.cle;
  const r = d.ratios;
  const cartes = `<div class="kpis">${r.agreges.filter(x => x.code !== "RDA").map(x => `<div class="kpi" title="${esc(x.libelle)} : ${esc(x.formule)}">
      <div class="icone ${FOND_RATIOS[x.code]}"><span class="code-ratio">${x.code}</span></div><div style="min-width:0"><div class="libelle">${esc(x.court)}</div>
      <div class="valeur">${x.valeur == null ? "—" : pct(x.valeur)}</div>
      <div class="delta">${x.variation != null ? `${variationPoints(x.variation)} vs ${esc(d.precedente)}` : `${pluriel(x.epn, "EPN")} ${x.epn > 1 ? "pris" : "pris"} en compte`}</div></div></div>`).join("")}</div>`;
  const avec = d.lignes.filter(l => l.ratios.length);
  const tableau = `<div class="panneau"><h2>${icone("tableau")}Ratios par EPN</h2>
    ${avec.length ? `<div class="defilant"><table class="donnees"><thead><tr><th>EPN</th>${d.definitions.map(x => `<th title="${esc(x.libelle)} : ${esc(x.formule)}">${x.code}<small>${esc(x.court)}</small></th>`).join("")}</tr></thead>
      <tbody>${avec.map(l => `<tr class="cliquable" data-id="${l.id}" title="Voir l'analyse du rapport"><td class="texte"><b>${esc(l.court)}</b><div class="sous-ligne">${esc(l.source)} · base : ${esc(l.base)}</div></td>${d.definitions.map(def => celluleRatio(l.ratios.find(x => x.code === def.code))).join("")}</tr>`).join("")}
      ${avec.length > 1 ? `<tr class="total"><td class="texte">Ensemble des EPN</td>${r.agreges.map(x => `<td class="centre">${x.valeur == null ? "—" : pct(x.valeur)}</td>`).join("")}</tr>` : ""}</tbody></table></div>`
      : `<p class="aide" style="margin:0">Ratios non disponibles : relancez l'analyse des rapports de cette période avec cette version de l'application.</p>`}
    <div class="definitions">${d.definitions.map(x => `<div><b>${x.code}</b> ${esc(x.libelle)} : ${esc(x.formule)}.</div>`).join("")}
      <div>La valeur retenue est calculée sur la situation d'exécution (SIGOBE) lorsqu'elle est fournie, sinon sur les tableaux du rapport ; « cité » indique la valeur donnée par le CB et sa concordance avec les tableaux de son rapport. Le RDA n'est pas calculable : les dépenses d'abonnement ne sont isolées ni dans les tableaux du canevas ni dans la situation d'exécution.</div></div></div>`;
  const presentes = new Set(avec.flatMap(l => l.structure.filter(x => x.part > 0.05).map(x => x.cle)));
  const legende = `<div class="legende" style="justify-content:flex-start">${[["personnel", "Personnel"], ["biens_services", "Biens et services"], ["transferts", "Transferts"], ["investissement", "Investissements"], ["autres", "Non classées"]]
    .filter(([c]) => presentes.has(c)).map(([c, l]) => `<span><i style="background:${COUL_CATEGORIES[c]}"></i>${l}</span>`).join("")}</div>`;
  const structure = `<div class="panneau"><h2>${icone("histogramme")}Structure des dépenses</h2>${legende}<div class="graphique" id="graph-structure"></div></div>`;
  const lecture = `<div class="panneau"><h2>${icone("rapports")}Lecture des ratios</h2><div class="lecture">${avec.map(l => `<p><b>${esc(l.court)}.</b> ${insecable(l.lecture)}</p>`).join("") || '<p class="aide">Aucune lecture disponible.</p>'}</div>${citationsHtml(r.citations)}</div>`;
  const options = avec.map((l, i) => `<option value="${i}">${esc(l.epn)}</option>`).join("");
  const evolution = `<div class="panneau" style="margin-top:16px"><h2>${icone("courbe")}Évolution des ratios</h2>
    <div class="champ" style="margin-bottom:10px;max-width:420px"><select id="epn-ratios">${options}</select></div>
    <div class="legende" id="legende-ratios" style="justify-content:flex-start">${["RRP", "RDP", "RDF", "RDI"].map(c => `<span><i class="rond" style="background:${COUL_RATIOS[c]}"></i>${c}</span>`).join("")}</div>
    <div class="graphique" id="graph-ratios"></div></div>`;
  contenu().innerHTML = entete("Analyse des ratios", "Ratios de gestion du canevas, par EPN et pour l'ensemble de la période", choixPeriode(d.periodes, d.periode.cle))
    + cartes + tableau + `<div class="grille-2-egal" style="margin-top:16px">${structure}${lecture}</div>` + (avec.length ? evolution : "");
  const elStructure = document.getElementById("graph-structure");
  if (avec.some(l => l.structure.length)) graphique(elStructure, L => svgStructure(avec, L));
  else elStructure.innerHTML = `<p class="aide">Répartition des dépenses par catégorie non disponible.</p>`;
  const courbe = () => {
    const l = avec[+document.getElementById("epn-ratios").value];
    const pts = d.evolution[l.epn] || [];
    const el = document.getElementById("graph-ratios");
    document.getElementById("legende-ratios").hidden = pts.length < 2;
    if (pts.length > 1) graphique(el, L => svgCourbes(pts, ["RRP", "RDP", "RDF", "RDI"], L));
    else { DESSINS.delete(el); el.innerHTML = `<p class="aide" style="margin:0">Une seule période analysée pour cet EPN : l'évolution s'affichera dès l'analyse du rapport d'une autre période.</p>`; }
  };
  if (avec.length) { courbe(); document.getElementById("epn-ratios").onchange = courbe; }
  document.querySelectorAll("tr.cliquable").forEach(tr => tr.onclick = () => ouvrirRapport(+tr.dataset.id));
  brancherPeriode(pageRatios);
}

/* ------------------------------------------------------------------ 2. analyse des rapports */
function zoneDepot(id, titre, texte, petit = false) {
  return `<div class="depot ${petit ? "petit" : ""}" id="${id}" tabindex="0" role="button">${icone("depot")}<div class="titre">${titre}</div><div>${texte}</div></div>`;
}
function periodesProposees() {
  const a = new Date().getFullYear();
  const l = [["", "Détectée automatiquement"]];
  [a, a - 1].forEach(x => {
    l.push([`1er trimestre ${x}`, `1er trimestre ${x}`], [`2e trimestre ${x}`, `2e trimestre ${x} (rapport d'étape au 30 juin)`],
      [`3e trimestre ${x}`, `3e trimestre ${x}`], [`4e trimestre ${x}`, `4e trimestre ${x}`], [`exercice ${x}`, `Exercice ${x} (rapport annuel)`]);
  });
  return l;
}
const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
function jourMois(jjmm) { const [j, m] = String(jjmm || "").split("/").map(Number); return j && m ? `${j === 1 ? "1er" : j} ${MOIS[m - 1]}` : "—"; }
function dateLimitePeriode(valeur) {
  const d = etat.app && etat.app.delais, an = +((String(valeur || "").match(/(?:19|20)\d\d/) || [0])[0]);
  if (!d || !an) return null;
  const t = /^1er trimestre/.test(valeur) ? 1 : /^2e trimestre|semestre|étape/.test(valeur) ? 2 : /^3e trimestre/.test(valeur) ? 3 : /^4e trimestre/.test(valeur) ? 4 : null;
  const [jj, mm] = d[t ? `trimestre_${t}_date_limite` : "rapport_annuel_date_limite"].split("/").map(Number);
  const annee = t ? (mm < t * 3 ? an + 1 : an) : an + 1;  // 4e trimestre et rapport annuel : l'année suivante
  return new Date(Date.UTC(annee, mm - 1, jj));
}
function delaiHtml(r) {
  const lim = dateLimitePeriode(r.periode);
  if (!lim) return `Date limite : selon la période détectée à l'analyse`;
  let html = `Date limite : ${lim.toLocaleDateString("fr-FR", { timeZone: "UTC" })}`;
  if (r.reception) {
    const ecart = Math.round((Date.parse(r.reception) - lim.getTime()) / 86400000);
    html += ecart > 0 ? ` · <span class="retard">hors délai de ${pluriel(ecart, "jour")}</span>` : ` · <span class="a-temps">dans les délais</span>`;
  }
  return html;
}
function resumeDelais() {
  const d = etat.app && etat.app.delais;
  if (!d) return "";
  return `Dates limites de transmission : 1er trimestre le ${jourMois(d.trimestre_1_date_limite)}, 2e trimestre (rapport d'étape) le ${jourMois(d.trimestre_2_date_limite)}, `
    + `3e trimestre le ${jourMois(d.trimestre_3_date_limite)}, 4e trimestre le ${jourMois(d.trimestre_4_date_limite)} de l'année suivante, `
    + `rapport annuel le ${jourMois(d.rapport_annuel_date_limite)} de l'année suivante.`;
}
async function televerser(fichier, categorie) {
  const r = await fetch("/api/televerser", {
    method: "POST", body: fichier,
    headers: { "X-Jeton": JETON, "X-Nom-Fichier": encodeURIComponent(fichier.name), "X-Categorie": categorie },
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || d.erreur) throw new Error(d.erreur || "Échec de l'envoi du fichier.");
  return d;
}
function brancherDepot(id, categorie, extensions, quandAjoute) {
  const zone = document.getElementById(id);
  const input = document.createElement("input");
  input.type = "file"; input.multiple = categorie !== "logo"; input.accept = extensions.join(",");
  input.style.display = "none";
  zone.after(input);
  const traiter = async fichiers => {
    for (const f of fichiers) {
      if (!extensions.some(e => f.name.toLowerCase().endsWith(e))) { toast(`${f.name} : format non accepté.`, "erreur"); continue; }
      try { const r = await televerser(f, categorie); quandAjoute({ ...r, nom: f.name, taille: f.size }); }
      catch (err) { toast(`${f.name} : ${err.message}`, "erreur"); }
    }
  };
  zone.onclick = () => input.click();
  zone.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } };
  input.onchange = () => { traiter([...input.files]); input.value = ""; };
  zone.ondragover = e => { e.preventDefault(); zone.classList.add("survol"); };
  zone.ondragleave = () => zone.classList.remove("survol");
  zone.ondrop = e => { e.preventDefault(); zone.classList.remove("survol"); traiter([...e.dataTransfer.files]); };
}
function listeFichiersHtml(liste, cle) {
  return `<ul class="fichiers">${liste.map((f, i) => `<li>${icone("fichier")}<span class="nom" title="${esc(f.nom)}">${esc(f.nom)}</span><button class="retirer" data-liste="${cle}" data-i="${i}" title="Retirer">×</button></li>`).join("")}</ul>`;
}
async function pageAnalyse() {
  if (!etat.app) await majEnvironnement();
  const A = etat.analyse;
  const charge = A.charge ?? (etat.app && etat.app.utilisateur.nom) ?? "";
  const sortie = A.sortie ?? (etat.app && etat.app.sortie) ?? "";
  const lignes = A.rapports.map((r, i) => `<tr>
      <td class="texte">${icone("fichier", 'style="width:16px;height:16px;vertical-align:-3px;color:#6b778a"')} ${esc(r.nom)}</td>
      <td><input type="date" data-i="${i}" data-champ="reception" value="${esc(r.reception || "")}" aria-label="Date de réception"></td>
      <td><select data-i="${i}" data-champ="periode" aria-label="Période">${periodesProposees().map(([v, l]) => `<option value="${esc(v)}" ${v === (r.periode || "") ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
        <div class="note-delai" id="delai-${i}">${delaiHtml(r)}</div></td>
      <td class="centre etat-rapport" id="etat-${i}">${celluleEtat(r)}</td>
      <td class="centre"><button class="retirer lien" data-liste="rapports" data-i="${i}" title="Retirer" aria-label="Retirer">×</button></td></tr>`).join("");
  const aTraiter = A.rapports.filter(r => r.etat !== "ok").length;
  const message = aTraiter ? `${aTraiter} rapport${aTraiter > 1 ? "s" : ""} prêt${aTraiter > 1 ? "s" : ""} à analyser.`
    : A.dernier ? (A.dernier.erreur || A.dernier.message) : A.rapports.length ? "Tous les rapports de la liste ont été analysés." : "Ajoutez au moins un rapport.";
  contenu().innerHTML = entete("Analyse des rapports", "Rapports des CB, décrets de création et situations d'exécution")
    + `<div class="panneau"><h2>${icone("rapports")}Rapports des Contrôleurs Budgétaires</h2>
        ${zoneDepot("depot-rapports", "Déposez les rapports ici", "ou cliquez pour les choisir (Word ou PDF, y compris scannés)", A.rapports.length > 0)}
        ${A.rapports.length ? `<div class="defilant" style="margin-top:12px"><table class="donnees table-rapports"><thead><tr><th>Rapport</th><th>Date de réception</th><th>Période et date limite</th><th>État</th><th></th></tr></thead><tbody>${lignes}</tbody></table></div>
        <div class="barre-outils"><span class="aide" style="margin:0">Date de réception commune :</span><input type="date" id="date-commune" aria-label="Date de réception commune">
          <button class="bouton" id="meme-date">${icone("calendrier")}Appliquer à tous</button><button class="bouton" id="vider">${icone("corbeille")}Vider la liste</button></div>` : ""}
        <p class="aide pied">${resumeDelais()} Elles se modifient dans les Paramètres.</p>
      </div>
      <div class="grille-2-egal haut" style="margin-top:16px">
        <div class="panneau"><h2>${icone("balance")}Documents de référence <span class="droite aide" style="margin:0">facultatifs</span></h2>
          <div class="ligne-champs">
            <div>${zoneDepot("depot-decrets", "Décrets de création", "PDF, Word ou texte", true)}${listeFichiersHtml(A.decrets, "decrets")}</div>
            <div>${zoneDepot("depot-situations", "Situations d'exécution", "SIGOBE, Excel, CSV ou PDF", true)}${listeFichiersHtml(A.situations, "situations")}</div>
          </div>
          <p class="aide" style="margin:10px 0 0">Chaque rapport est rapproché du décret et de la situation de son EPN. De préférence, éditez la situation à la date de fin de période.</p>
        </div>
        <div class="panneau"><h2>${icone("lecture")}Lancement</h2>
          <div class="ligne-champs">
            <div class="champ"><label for="charge">Chargé d'Études</label><input id="charge" value="${esc(charge)}"></div>
            <div class="champ"><label for="sortie">Dossier des résultats</label><input id="sortie" value="${esc(sortie)}"></div>
          </div>
          <div style="display:flex;gap:10px;margin-top:14px;align-items:center;flex-wrap:wrap">
            <button class="bouton primaire grand" id="lancer">${icone("lecture")}Lancer l'analyse</button>
            <button class="bouton" id="arreter" disabled>${icone("arret")}Arrêter</button>
            <button class="bouton" id="ouvrir-sortie">${icone("dossier")}Dossier des résultats</button>
          </div>
          <div class="barre-progres"><div id="progres" style="width:${!aTraiter && A.dernier ? 100 : 0}%"></div></div>
          <div class="etat-texte" id="etat-texte">${esc(message)}</div>
        </div>
      </div>
      <div class="panneau" id="resultats" style="margin-top:16px" hidden></div>`;

  brancherDepot("depot-rapports", "rapport", [".docx", ".pdf"], f => { A.rapports.push({ ...f, reception: "", periode: "", etat: "attente" }); pageAnalyse(); });
  brancherDepot("depot-decrets", "decret", [".pdf", ".docx", ".txt"], f => { A.decrets.push(f); pageAnalyse(); });
  brancherDepot("depot-situations", "situation", [".xlsx", ".xlsm", ".csv", ".pdf", ".docx"], f => { A.situations.push(f); pageAnalyse(); });
  document.querySelectorAll("[data-champ]").forEach(el => el.onchange = () => {
    const i = +el.dataset.i;
    A.rapports[i][el.dataset.champ] = el.value;
    document.getElementById("delai-" + i).innerHTML = delaiHtml(A.rapports[i]);
  });
  document.querySelectorAll(".retirer[data-liste]").forEach(b => b.onclick = () => { A[b.dataset.liste].splice(+b.dataset.i, 1); pageAnalyse(); });
  document.getElementById("charge").oninput = e => { A.charge = e.target.value; };
  document.getElementById("sortie").oninput = e => { A.sortie = e.target.value; };
  const md = document.getElementById("meme-date");
  if (md) md.onclick = () => {
    const v = document.getElementById("date-commune").value;
    if (!v) { toast("Choisissez d'abord la date de réception commune.", "erreur"); return; }
    A.rapports.forEach(r => { if (r.etat !== "ok") r.reception = v; });
    pageAnalyse();
  };
  const vd = document.getElementById("vider");
  if (vd) vd.onclick = () => { if (etat.sondage) { toast("Attendez la fin de l'analyse en cours.", "erreur"); return; } A.rapports = []; A.dernier = null; pageAnalyse(); };
  document.getElementById("ouvrir-sortie").onclick = () => post("/api/ouvrir", { quoi: "sortie" }).catch(err => toast(err.message, "erreur"));
  document.getElementById("lancer").onclick = lancerAnalyse;
  document.getElementById("arreter").onclick = () => post("/api/arreter").then(() => toast("L'analyse s'arrêtera après le rapport en cours."));
  if (etat.sondage || (etat.app && etat.app.en_cours)) {
    document.getElementById("lancer").disabled = true;
    document.getElementById("arreter").disabled = false;
    demarrerSuivi();
  } else afficherResultats(A.dernier);
}
function etatRapport(e) {
  return { attente: ["En attente", "gris"], cours: ["En cours…", "bleu"], ok: ["Terminé", "vert"], erreur: ["Erreur", "rouge"], arret: ["Non traité", "gris"] }[e] || ["En attente", "gris"];
}
function celluleEtat(r) {
  return statutHtml(...etatRapport(r.etat)) + (r.erreur ? `<div class="erreur-ligne">${esc(r.erreur)}</div>` : "");
}
async function lancerAnalyse() {
  const A = etat.analyse;
  if (!A.rapports.length) { toast("Ajoutez au moins un rapport à analyser.", "erreur"); return; }
  let choisis = A.rapports.filter(r => r.etat !== "ok");
  if (!choisis.length) {
    if (!confirm("Tous les rapports de la liste ont déjà été analysés. Les analyser de nouveau ?")) return;
    choisis = A.rapports;
  }
  const sans = choisis.filter(r => !r.reception).length;
  if (sans && !confirm(`${sans > 1 ? `${sans} rapports n'ont` : "Un rapport n'a"} pas de date de réception : le délai de transmission ne pourra pas être apprécié. Continuer ?`)) return;
  try {
    await post("/api/analyser", {
      rapports: choisis.map(r => ({ id: r.id, reception: r.reception, periode: r.periode })),
      decrets: A.decrets.map(f => f.id), situations: A.situations.map(f => f.id),
      charge: document.getElementById("charge").value, sortie: document.getElementById("sortie").value,
    });
    choisis.forEach(r => { r.etat = "attente"; r.erreur = ""; });
    document.querySelectorAll(".etat-rapport").forEach((cel, i) => { cel.innerHTML = celluleEtat(A.rapports[i]); });
    document.getElementById("resultats").innerHTML = "";
    document.getElementById("resultats").hidden = true;
    etat.finAttendue = true;
    demarrerSuivi();
  } catch (err) { toast(err.message, "erreur"); }
}
function demarrerSuivi() {
  if (etat.sondage) return;
  etat.sondage = true;
  suivreAnalyse();
}
async function suivreAnalyse() {
  let t;
  try { t = await api("/api/travail"); } catch (err) { etat.sondage = false; toast(err.message, "erreur"); return; }
  const A = etat.analyse;
  (t.rapports || []).forEach(r => {
    const i = A.rapports.findIndex(x => x.id === r.id);
    if (i < 0) return;
    A.rapports[i].etat = r.etat;
    A.rapports[i].erreur = r.erreur;
    const cel = document.getElementById("etat-" + i);
    if (cel) cel.innerHTML = celluleEtat(A.rapports[i]);
  });
  if (document.getElementById("progres")) {
    document.getElementById("progres").style.width = (t.progres || 0) + "%";
    document.getElementById("etat-texte").textContent = t.erreur || t.message || "";
    document.getElementById("lancer").disabled = !!t.en_cours;
    document.getElementById("arreter").disabled = !t.en_cours;
    afficherResultats(t);
  }
  if (t.en_cours) { setTimeout(suivreAnalyse, 700); return; }
  etat.sondage = false;
  if (etat.app) etat.app.en_cours = false;
  if ((t.rapports || []).length) A.dernier = t;
  if (etat.finAttendue) {
    etat.finAttendue = false;
    await majEnvironnement();
    const echecs = (t.rapports || []).filter(r => r.etat === "erreur").length;
    if (t.erreur) toast(t.erreur, "erreur");
    else toast((t.message || "Analyse terminée.") + (echecs ? ` ${echecs} rapport${echecs > 1 ? "s" : ""} en erreur.` : ""), echecs ? "erreur" : "");
  }
}
function afficherResultats(t) {
  const zone = document.getElementById("resultats");
  if (!zone || !t || !(t.resultats || []).length) return;
  zone.hidden = false;
  zone.innerHTML = `<h2>${icone("coche")}Résultats</h2>` + t.resultats.map(r => `<div class="carte-resultat">
      <div><div class="t">${esc(r.epn)}</div><div class="m">${esc(r.periode)} · date limite : ${dateFr(r.date_limite)}${r.date_reception ? ` · reçu le ${dateFr(r.date_reception)} · <span class="${r.ecart_jours > 0 ? "retard" : "a-temps"}">${esc(r.delai)}</span>` : " · date de réception non renseignée"}</div>
        <div class="etiquettes"><span class="etiquette">Forme ${pct(r.forme)}</span><span class="etiquette">Fond ${pct(r.fond)}</span><span class="etiquette">${r.anomalies_majeures} anomalies majeures</span>
        ${statutHtml(r.retour ? "Retour au CB" : "Exploitable", r.retour ? "rouge" : "vert")}</div>
        ${(r.avertissements || []).map(a => `<div class="m" style="margin-top:4px">⚠ ${esc(a)}</div>`).join("")}</div>
      <div class="b"><button class="bouton" data-detail="${r.id}">Voir l'analyse</button><button class="bouton primaire" data-excel="${r.id}">${icone("ouvrir")}Ouvrir l'Excel</button></div></div>`).join("")
    + (t.tableau_de_bord ? `<div style="margin-top:10px"><button class="bouton" id="tdb-excel">${icone("tableau")}Tableau de bord consolidé (Excel)</button></div>` : "");
  zone.querySelectorAll("[data-detail]").forEach(b => b.onclick = () => ouvrirRapport(+b.dataset.detail));
  zone.querySelectorAll("[data-excel]").forEach(b => b.onclick = () => post("/api/ouvrir", { quoi: "fichier", id: +b.dataset.excel }).catch(err => toast(err.message, "erreur")));
  const tdb = document.getElementById("tdb-excel");
  if (tdb) tdb.onclick = () => post("/api/ouvrir", { quoi: "chemin", chemin: t.tableau_de_bord }).catch(err => toast(err.message, "erreur"));
}

/* ------------------------------------------------------------------ 3. comparaison budgétaire */
async function pageComparaison() {
  const d = await api("/api/comparaison" + (etat.periode ? "?periode=" + encodeURIComponent(etat.periode) : ""));
  if (d.vide) {
    contenu().innerHTML = entete("Comparaison budgétaire", "Prévisions et réalisations par EPN") + videHtml("comparaison", "Aucune donnée", "Analysez d'abord des rapports.", BOUTON_ANALYSER);
    return;
  }
  etat.periode = d.periode.cle;
  const u = d.unite;
  const lignes = d.lignes.map(l => {
    const tr = l.recettes_prevues && l.recettes_realisees != null ? l.recettes_realisees / l.recettes_prevues * 100 : null;
    return `<tr><td class="texte"><b>${esc(l.court)}</b><div style="color:#6b778a;font-size:12px">${esc(l.source)}</div></td>
      <td>${montant(l.recettes_prevues, u, false)}</td><td>${montant(l.recettes_realisees, u, false)}</td><td>${pct(tr)}</td>
      <td>${montant(l.credits, u, false)}</td><td>${montant(l.engagements, u, false)}</td><td>${montant(l.execution, u, false)}</td>
      <td class="${l.statut === "OK" ? "taux-ok" : "taux-ko"}">${pct(l.taux)}</td><td class="centre">${statutHtml(l.statut, l.couleur)}</td></tr>`;
  }).join("");
  const options = d.lignes.map((l, i) => `<option value="${i}">${esc(l.epn)}</option>`).join("");
  contenu().innerHTML = entete("Comparaison budgétaire", "Prévisions et réalisations, en recettes et en dépenses", choixPeriode(d.periodes, d.periode.cle))
    + `<div class="panneau"><h2>${icone("tableau")}Exécution par EPN <span class="droite aide" style="margin:0">montants en ${esc(u.libelle)}</span></h2>
      <div class="defilant"><table class="donnees"><thead><tr><th rowspan="2">EPN</th><th colspan="3">Recettes</th><th colspan="4">Dépenses</th><th rowspan="2">Statut</th></tr>
      <tr><th>Prévues</th><th>Réalisées</th><th>Taux</th><th>Crédits</th><th>Engagements</th><th>Ordonnancements</th><th>Taux</th></tr></thead><tbody>${lignes}</tbody></table></div></div>
    <div class="grille-2-egal" style="margin-top:16px">
      <div class="panneau"><h2>${icone("histogramme")}Prévu et réalisé par nature de dépense</h2>
        <div class="champ" style="margin-bottom:10px"><select id="epn-nature">${options}</select></div>
        <div class="legende" style="justify-content:flex-end"><span><i style="background:#1565d8"></i>Prévu</span><span><i style="background:#f59e0b"></i>Réalisé</span></div>
        <div class="graphique" id="graph-nature"></div></div>
      <div class="panneau"><h2>${icone("courbe")}Évolution du taux d'exécution</h2>
        <div class="champ" style="margin-bottom:10px"><select id="epn-evolution">${options}</select></div>
        <div class="graphique" id="graph-evolution"></div></div></div>`;
  const nature = () => {
    const l = d.lignes[+document.getElementById("epn-nature").value];
    const donnees = Object.values(l.natures || {}).filter(n => n.prevu != null || n.realise != null);
    const el = document.getElementById("graph-nature");
    if (donnees.length) graphique(el, L => svgGroupes(donnees, u, L));
    else { DESSINS.delete(el); el.innerHTML = `<p class="aide">Répartition par nature non disponible pour cet EPN.</p>`; }
  };
  const evolution = () => {
    const l = d.lignes[+document.getElementById("epn-evolution").value];
    const pts = d.historiques[l.epn] || [];
    const el = document.getElementById("graph-evolution");
    if (pts.length) graphique(el, L => svgCourbe(pts, L));
    else { DESSINS.delete(el); el.innerHTML = `<p class="aide">Aucune autre période analysée.</p>`; }
  };
  if (d.lignes.length) { nature(); evolution(); }
  document.getElementById("epn-nature").onchange = nature;
  document.getElementById("epn-evolution").onchange = evolution;
  brancherPeriode(pageComparaison);
}

/* ------------------------------------------------------------------ 4. alertes & anomalies */
async function pageAlertes() {
  const d = await api("/api/alertes" + (etat.periode ? "?periode=" + encodeURIComponent(etat.periode) : ""));
  if (d.vide) {
    contenu().innerHTML = entete("Alertes & Anomalies", "Points d'attention issus des analyses") + videHtml("alerte", "Aucune alerte", "Aucune analyse n'a encore été réalisée.", BOUTON_ANALYSER);
    return;
  }
  etat.periode = d.periode.cle;
  const n = niv => d.alertes.filter(a => a.niveau === niv).length;
  majBadge(n("critique") + n("attention"));
  const groupe = (niv, titre) => {
    const liste = d.alertes.filter(a => a.niveau === niv);
    if (!liste.length) return "";
    const ic = niv === "critique" ? "exclamation" : niv === "attention" ? "alerte" : "info";
    return `<div class="panneau"><h2><span class="pastille ${niv}" style="width:26px;height:26px;border-radius:50%;display:grid;place-items:center;color:#fff">${icone(ic, 'style="width:15px;height:15px"')}</span>${titre} (${liste.length})</h2>
      <div class="liste-alertes">${liste.map(a => `<div class="alerte"><span class="puce ${a.niveau}"></span><div><b>${esc(a.titre)}</b> <span class="etiquette">${a.type === "execution" ? "Exécution budgétaire" : "Rapport"}</span>
        <div class="epn">${esc(a.epn || "")}</div><div>${esc(a.detail || "")}${a.valeur != null ? ` (${signe(a.valeur, montant(Math.abs(a.valeur), d.unite))})` : ""}</div></div>
        ${a.id ? `<button class="bouton" data-id="${a.id}">Voir le rapport</button>` : ""}</div>`).join("")}</div></div>`;
  };
  contenu().innerHTML = entete("Alertes & Anomalies", "Points d'attention issus des analyses de la période", choixPeriode(d.periodes, d.periode.cle))
    + `<div class="compteurs">${carteKpi("exclamation", "fond-rouge", "Critiques", n("critique"), "")}${carteKpi("alerte", "fond-orange", "À traiter", n("attention"), "")}${carteKpi("info", "fond-bleu", "Pour information", n("info"), "")}</div>`
    + (d.alertes.length ? `<div class="pile">${groupe("critique", "Alertes critiques")}${groupe("attention", "Points à traiter")}${groupe("info", "Pour information")}</div>`
      : videHtml("coche", "Aucune alerte pour cette période", "Les rapports analysés n'appellent pas d'observation particulière."));
  document.querySelectorAll("[data-id]").forEach(b => b.onclick = () => ouvrirRapport(+b.dataset.id));
  brancherPeriode(pageAlertes);
}

/* ------------------------------------------------------------------ 5. rapports détaillés */
async function pageRapports() {
  const d = await api("/api/rapports");
  if (!d.rapports.length) {
    contenu().innerHTML = entete("Rapports détaillés", "Historique des analyses") + videHtml("rapports", "Aucun rapport analysé", "Les analyses réalisées apparaîtront ici.", BOUTON_ANALYSER);
    return;
  }
  const opts = [`<option value="">Toutes les périodes</option>`].concat(d.periodes.map(p => `<option value="${p.cle}">${esc(p.libelle)}</option>`)).join("");
  contenu().innerHTML = entete("Rapports détaillés", "Historique des analyses : cliquez sur un rapport pour lire son analyse",
    `<div class="choix-periode">${icone("calendrier")}<select id="filtre-periode">${opts}</select></div><div class="choix-periode"><input id="recherche" placeholder="Rechercher un EPN, un CB…" style="border:0;outline:0;min-width:220px"></div>`)
    + `<div class="panneau"><div class="defilant"><table class="donnees" id="table-rapports"><thead><tr><th>EPN</th><th>Période</th><th>Contrôleur Budgétaire</th><th>Date limite</th><th>Réception</th><th>Délai</th><th>Forme</th><th>Fond</th><th>Anomalies majeures</th><th>Suite</th><th>Analysé le</th></tr></thead><tbody></tbody></table></div></div>`;
  const remplir = () => {
    const per = document.getElementById("filtre-periode").value, q = document.getElementById("recherche").value.toLowerCase();
    const rows = d.rapports.filter(r => (!per || r.periode_cle === per) && (!q || `${r.epn} ${r.controleur} ${r.tutelle}`.toLowerCase().includes(q)));
    document.querySelector("#table-rapports tbody").innerHTML = rows.map(r => `<tr class="cliquable" data-id="${r.id}">
      <td class="texte"><b>${esc(r.epn)}</b><div style="color:#6b778a;font-size:12px">${esc(r.tutelle)}</div></td><td class="centre">${esc(r.periode)}</td>
      <td class="texte">${esc(r.controleur || "—")}</td><td class="centre">${dateFr(r.date_limite)}</td><td class="centre">${dateFr(r.date_reception)}</td>
      <td class="centre">${r.ecart_jours == null ? "—" : r.ecart_jours > 0 ? statutHtml(`+${r.ecart_jours} j`, "rouge") : statutHtml("Dans les délais", "vert")}</td>
      <td>${pct(r.score_forme)}</td><td>${pct(r.score_fond)}</td><td class="centre">${r.anomalies_majeures}</td>
      <td class="centre">${statutHtml(r.retour ? "Retour au CB" : "Exploitable", r.retour ? "rouge" : "vert")}</td><td class="centre">${dateFr(r.date_analyse)}</td></tr>`).join("")
      || `<tr><td colspan="11" class="texte" style="text-align:center;color:#6b778a">Aucun rapport ne correspond à la recherche.</td></tr>`;
    document.querySelectorAll("#table-rapports tr.cliquable").forEach(tr => tr.onclick = () => ouvrirRapport(+tr.dataset.id));
  };
  document.getElementById("filtre-periode").onchange = remplir;
  document.getElementById("recherche").oninput = remplir;
  remplir();
}

/* ------------------------------------------------------------------ fiche de détail d'un rapport */
function fermerTiroir() { document.getElementById("tiroir").hidden = true; document.getElementById("voile").hidden = true; }
async function ouvrirRapport(id) {
  let r;
  try { r = await api("/api/rapport?id=" + id); } catch (err) { toast(err.message, "erreur"); return; }
  const D = r.donnees, m = D.montants || {};
  const u = { diviseur: Math.max(m.credits || 0, m.recettes_prevues || 0) >= 1e9 ? 1e9 : 1e6, libelle: Math.max(m.credits || 0, m.recettes_prevues || 0) >= 1e9 ? "Mds FCFA" : "M FCFA" };
  const paragraphes = (D.appreciation || "").split(/\n\s*\n/).map(p => `<p>${insecable(p)}</p>`).join("");
  const t = document.getElementById("tiroir");
  t.innerHTML = `<button class="fermer" title="Fermer" aria-label="Fermer">×</button>
    <h2>${esc(r.epn)}</h2><div class="meta">${esc(r.periode)} · CB : ${esc(r.controleur || "non identifié")} · analysé le ${dateFr(r.date_analyse)}</div>
    <div class="etiquettes" style="margin-bottom:14px"><span class="etiquette">Forme ${pct(r.score_forme)} (${esc((D.mention_forme || "").toLowerCase())})</span>
      <span class="etiquette">Fond ${pct(r.score_fond)}</span><span class="etiquette">${r.anomalies_majeures} anomalies majeures</span><span class="etiquette">${esc(D.delai || "")}</span>
      ${statutHtml(r.retour ? "Retour au CB" : "Exploitable", r.retour ? "rouge" : "vert")}</div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
      <button class="bouton primaire" id="t-excel" ${r.fichier_existe ? "" : "disabled"}>${icone("ouvrir")}Ouvrir le fichier d'analyse</button>
      <button class="bouton" id="t-dossier" ${r.fichier_existe ? "" : "disabled"}>${icone("dossier")}Dossier</button>
      <button class="bouton danger" id="t-supprimer">${icone("corbeille")}Retirer de l'historique</button></div>
    <div class="panneau"><h2>Appréciation générale</h2><div class="prose">${paragraphes || "<p>—</p>"}</div>
      <p style="margin:6px 0 0"><b>${insecable(D.suite || "")}</b></p></div>
    ${(D.alertes || []).length ? `<div class="panneau"><h2>Alertes</h2><ul class="constats">${D.alertes.map(a => `<li><span class="g ${a.niveau === "critique" ? "Majeure" : a.niveau === "attention" ? "Mineure" : "Information"}">${a.niveau === "critique" ? "Critique" : a.niveau === "attention" ? "À traiter" : "Info"}</span><span><b>${esc(a.titre)}</b> – ${esc(a.detail)}</span></li>`).join("")}</ul></div>` : ""}
    ${(D.ratios && D.ratios.liste && D.ratios.liste.length) ? `<div class="panneau"><h2>Ratios de gestion</h2>
      <table class="donnees"><thead><tr><th>Ratio</th><th>Valeur</th><th>Cité par le CB</th></tr></thead><tbody>
      ${D.ratios.liste.map(x => `<tr><td class="texte" title="${esc(x.formule)}"><b>${x.code}</b> ${esc(x.court)}</td><td>${x.valeur == null ? "—" : pct(x.valeur)}</td>
        <td class="centre">${x.cite == null ? '<span class="nc">non cité</span>' : `${pct(x.cite)} <span class="cite ${x.coherent === true ? "ok" : x.coherent === false ? "ko" : "nv"}">${x.coherent === true ? "concordant" : x.coherent === false ? "discordant" : "non vérifiable"}</span>`}</td></tr>`).join("")}</tbody></table>
      <p class="aide" style="margin:8px 0 0">Source : ${esc(D.ratios.source)} ; base : ${esc(D.ratios.base)}.</p>
      ${r.lecture_ratios ? `<p class="lecture" style="margin:8px 0 0">${insecable(r.lecture_ratios)}</p>` : ""}</div>` : ""}
    ${D.difficultes ? `<div class="panneau ds"><h2>Difficultés et suggestions</h2><div class="grille-ds une">
      <div class="colonne-ds difficultes"><h3>Difficultés <span class="compteur">${D.difficultes.difficultes.length}</span></h3>${D.difficultes.difficultes.length ? listeDsHtml(D.difficultes.difficultes, CATEGORIES_DS, false) : '<p class="aide" style="margin:0">Aucune difficulté signalée.</p>'}</div>
      <div class="colonne-ds suggestions"><h3>Suggestions <span class="compteur">${D.difficultes.suggestions.length}</span></h3>${D.difficultes.suggestions.length ? listeDsHtml(D.difficultes.suggestions, CATEGORIES_DS, false) : '<p class="aide" style="margin:0">Aucune suggestion formulée.</p>'}</div></div></div>` : ""}
    <div class="panneau"><h2>Principaux constats</h2><ul class="constats">${(D.constats || []).map(c => `<li><span class="g ${esc(c.gravite)}">${esc(c.gravite)}</span><span>${esc(c.texte)}</span></li>`).join("") || "<li>Aucun constat.</li>"}</ul></div>
    <div class="panneau"><h2>Montants retenus</h2><table class="donnees"><tbody>
      <tr><td class="texte">Crédits (budget actuel)</td><td>${montant(m.credits, u)}</td></tr>
      <tr><td class="texte">Engagements</td><td>${montant(m.engagements, u)}</td></tr>
      <tr><td class="texte">Exécution (ordonnancements)</td><td>${montant(m.execution, u)}</td></tr>
      <tr><td class="texte">Recettes prévues</td><td>${montant(m.recettes_prevues, u)}</td></tr>
      <tr><td class="texte">Recettes réalisées</td><td>${montant(m.recettes_realisees, u)}</td></tr></tbody></table>
      <p class="aide" style="margin:8px 0 0">Source : ${esc(m.source || "—")}.</p>
      ${D.decret ? `<p style="margin:8px 0 0"><b>Décret :</b> ${esc(D.decret)}</p>` : ""}${D.situation ? `<p style="margin:6px 0 0"><b>Situation d'exécution :</b> ${esc(D.situation)}</p>` : ""}</div>`;
  t.hidden = false;
  document.getElementById("voile").hidden = false;
  t.scrollTop = 0;
  t.querySelector(".fermer").onclick = fermerTiroir;
  document.getElementById("t-excel").onclick = () => post("/api/ouvrir", { quoi: "fichier", id }).catch(err => toast(err.message, "erreur"));
  document.getElementById("t-dossier").onclick = () => post("/api/ouvrir", { quoi: "dossier", id }).catch(err => toast(err.message, "erreur"));
  document.getElementById("t-supprimer").onclick = async () => {
    if (!confirm("Retirer cette analyse de l'historique ? Le fichier Excel n'est pas supprimé.")) return;
    await post("/api/supprimer", { id });
    fermerTiroir(); toast("Analyse retirée de l'historique."); await majEnvironnement(); router();
  };
}

/* ------------------------------------------------------------------ 6. paramètres */
async function pageParametres() {
  const p = await api("/api/parametres");
  if (!etat.app) await majEnvironnement();
  const c = (sec, cle, lib, note = "", type = "text") => `<div class="champ"><label for="${sec}-${cle}">${lib}</label><input id="${sec}-${cle}" data-sec="${sec}" data-cle="${cle}" type="${type}" value="${esc((p[sec] || {})[cle] ?? "")}">${note ? `<span class="note">${note}</span>` : ""}</div>`;
  contenu().innerHTML = entete("Paramètres", "Profil, institution, délais et seuils de l'analyse", `<button class="bouton primaire" id="enregistrer">${icone("coche")}Enregistrer</button>`)
    + `<div class="grille-2-egal"><div class="pile">
      <div class="panneau section-param"><h2>${icone("utilisateur")}Profil</h2><div class="ligne-champs">${c("utilisateur", "nom", "Nom et prénoms")}${c("utilisateur", "fonction", "Fonction", "Ex. Chargé d'Études, Analyste budgétaire")}</div></div>
      <div class="panneau section-param"><h2>${icone("accueil")}Institution</h2><div class="ligne-champs">${c("institution", "ligne1", "Ministère / direction")}${c("institution", "ligne2", "Deuxième ligne", "Ex. Côte d'Ivoire")}</div>
        <div style="display:flex;gap:16px;align-items:center;margin-top:14px"><div class="apercu-logo" id="apercu-logo"></div>
        <div><div style="font-weight:600">Logo affiché dans la barre latérale</div><div class="aide" style="margin:2px 0 8px">Image PNG, JPG ou SVG (logo officiel de l'institution).</div>
        <div style="display:flex;gap:8px"><button class="bouton" id="choisir-logo">${icone("depot")}Choisir une image</button><button class="bouton" id="retirer-logo">Retirer</button></div><div id="depot-logo" hidden></div></div></div></div>
      <div class="panneau section-param"><h2>${icone("dossier")}Analyse</h2>
        <div class="champ"><label for="sortie-param">Dossier des résultats</label><input id="sortie-param" value="${esc(p.sortie)}"></div>
        <label class="interrupteur" style="margin-top:12px"><input type="checkbox" id="validation" ${p.analyse.validation_directe ? "checked" : ""}> Produire les fichiers d'analyse sous forme définitive (statuts tranchés)</label></div>
    </div><div class="pile">
      <div class="panneau section-param"><h2>${icone("calendrier")}Délais de transmission</h2><div class="ligne-champs">
        ${c("delais", "trimestre_1_date_limite", "1er trimestre", "Date limite, format jj/mm")}${c("delais", "trimestre_2_date_limite", "2e trimestre (rapport d'étape)", "Date limite, format jj/mm")}
        ${c("delais", "trimestre_3_date_limite", "3e trimestre", "Date limite, format jj/mm")}${c("delais", "trimestre_4_date_limite", "4e trimestre", "Date limite l'année suivante, format jj/mm")}
        ${c("delais", "rapport_annuel_date_limite", "Rapport annuel", "Date limite l'année suivante, format jj/mm")}</div></div>
      <div class="panneau section-param"><h2>${icone("pourcent")}Appréciation des rapports</h2><div class="ligne-champs">
        ${c("appreciation", "tres_bien", "« Très satisfaisant » à partir de (%)", "", "number")}${c("appreciation", "bien", "« Satisfaisant » à partir de (%)", "", "number")}${c("appreciation", "passable", "« Passable » à partir de (%)", "", "number")}
        ${c("appreciation", "retour_cb_si_score_forme_inferieur_a", "Retour au CB si forme inférieure à (%)", "", "number")}${c("appreciation", "retour_cb_si_anomalies_majeures", "Retour au CB à partir de (anomalies majeures)", "", "number")}</div></div>
      <div class="panneau section-param"><h2>${icone("comparaison")}Exécution budgétaire</h2><div class="ligne-champs">
        ${c("execution", "seuil_vigilance", "« À surveiller » au-delà de (points)", "Écart au taux attendu (25 %, 50 %, 75 %, 100 %)", "number")}${c("execution", "seuil_sous_execution", "« Sous-exécution » au-delà de (points)", "", "number")}</div></div>
      <div class="panneau section-param"><h2>${icone("fichier")}Fichiers</h2>
        <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="bouton" data-ouvrir="referentiel">Référentiel des EPN</button><button class="bouton" data-ouvrir="parametres">Fichier des paramètres</button><button class="bouton" data-ouvrir="dossier_parametres">Dossier des paramètres</button><button class="bouton" data-ouvrir="journal">Journal de l'application</button></div>
        <p class="aide" style="margin:10px 0 0">Lecture des documents scannés : ${etat.app && etat.app.ocr.ok ? "disponible" : "indisponible – " + esc(etat.app ? etat.app.ocr.message : "")}.<br>Historique des analyses : ${esc(p.fichiers.historique)}</p></div>
    </div></div>`;
  const majLogo = () => { document.getElementById("apercu-logo").innerHTML = etat.app && etat.app.logo ? `<img src="/api/logo?jeton=${encodeURIComponent(JETON)}&t=${Date.now()}" alt="">` : icone("analyse", 'style="width:40px;height:40px;color:#fff"'); };
  majLogo();
  const depot = document.getElementById("depot-logo");
  depot.className = "depot"; depot.id = "zone-logo";
  brancherDepot("zone-logo", "logo", [".png", ".jpg", ".jpeg", ".gif", ".svg"], async () => { await majEnvironnement(); majLogo(); toast("Logo enregistré."); });
  document.getElementById("choisir-logo").onclick = () => document.getElementById("zone-logo").click();
  document.getElementById("retirer-logo").onclick = async () => { await post("/api/supprimer_logo"); await majEnvironnement(); majLogo(); };
  document.querySelectorAll("[data-ouvrir]").forEach(b => b.onclick = () => post("/api/ouvrir", { quoi: b.dataset.ouvrir }).catch(err => toast(err.message, "erreur")));
  document.getElementById("enregistrer").onclick = async () => {
    const data = { sortie: document.getElementById("sortie-param").value, analyse: { validation_directe: document.getElementById("validation").checked } };
    document.querySelectorAll("[data-sec]").forEach(el => { (data[el.dataset.sec] = data[el.dataset.sec] || {})[el.dataset.cle] = el.value; });
    try { await post("/api/parametres", data); await majEnvironnement(); etat.analyse.charge = undefined; etat.analyse.sortie = undefined; toast("Paramètres enregistrés."); }
    catch (err) { toast(err.message, "erreur"); }
  };
}

/* ------------------------------------------------------------------ 7. aide, 8. à propos */
function pageAide() {
  contenu().innerHTML = entete("Aide", "Mode d'emploi de l'application")
    + `<div class="grille-2-egal"><div class="panneau"><h2>${icone("lecture")}Analyser des rapports</h2><ol class="etapes">
      <li><b>Déposez les rapports</b> des Contrôleurs Budgétaires (Word ou PDF, y compris scannés) dans « Analyse des rapports », puis indiquez leur date de réception à la DCB.</li>
      <li><b>Ajoutez, si vous les avez, les décrets de création</b> des EPN et les <b>situations d'exécution</b> (états SIGOBE recettes et annexe des dépenses, Excel, CSV ou PDF).</li>
      <li><b>Lancez l'analyse.</b> Chaque rapport donne un fichier Excel d'analyse (grille de la DCB rédigée) et alimente le tableau de bord.</li>
      <li><b>Consultez</b> le tableau de bord, les alertes et le détail de chaque rapport ; ouvrez le fichier Excel pour le transmettre.</li></ol></div>
      <div class="panneau"><h2>${icone("aide")}Questions fréquentes</h2>
      <p><b>D'où viennent les montants du tableau de bord ?</b><br>De la situation d'exécution (SIGOBE) lorsqu'elle est fournie, sinon des tableaux du rapport. La source est indiquée sous le détail par EPN.</p>
      <p><b>Quelles sont les dates limites de transmission ?</b><br>${esc(resumeDelais())} Un rapport reçu après sa date limite est signalé « hors délai » (alerte, appréciation générale, fichier d'analyse). Ces dates se modifient dans les Paramètres.</p>
      <p><b>Comment est fixé le statut d'exécution ?</b><br>Le taux d'exécution est comparé au taux attendu en fin de période (25 %, 50 %, 75 %, 100 %). Les seuils se règlent dans les Paramètres.</p>
      <p><b>Un document scanné n'est pas lu.</b><br>Vérifiez dans Paramètres que la lecture des documents scannés est disponible. À défaut, demandez la version Word du rapport.</p>
      <p><b>Où sont conservées les données ?</b><br>Uniquement sur ce poste : les fichiers d'analyse dans le dossier des résultats, l'historique dans le profil de l'utilisateur. Aucune donnée n'est envoyée sur Internet.</p>
      <p><b>L'interface ne s'affiche pas.</b><br>Si Microsoft Edge ne l'affiche pas, l'application l'ouvre d'elle-même dans le navigateur par défaut au bout de 45 secondes. Vous pouvez aussi utiliser le raccourci « Analyse des rapports des CB (dans le navigateur) » du menu Démarrer. Le déroulement est consigné dans le journal (Paramètres, Fichiers).</p></div></div>`;
}
function pageAPropos() {
  const v = etat.app ? etat.app.version : "";
  contenu().innerHTML = entete("À propos", "Analyse des rapports des Contrôleurs Budgétaires")
    + `<div class="panneau" style="max-width:760px"><h2>${icone("info")}Version ${esc(v)}</h2>
      <p>L'application analyse les rapports périodiques des Contrôleurs Budgétaires auprès des EPN au regard du canevas de rédaction institué par la note n°0580/MBPE/DGBF/DCB du 26 juillet 2023 (décret n°2021-677 du 03 novembre 2021), du décret de création de chaque EPN et de la situation d'exécution du budget.</p>
      <p>Pour chaque rapport, elle produit le fichier d'analyse de la DCB (forme, fond, difficultés et suggestions, appréciation générale) et alimente le tableau de bord de suivi de l'exécution budgétaire.</p>
      <p class="aide" style="margin:0">Toutes les données restent sur ce poste.</p></div>`;
}

/* ------------------------------------------------------------------ démarrage */
document.addEventListener("dragover", e => e.preventDefault());
document.addEventListener("drop", e => e.preventDefault());
document.addEventListener("keydown", e => { if (e.key === "Escape") fermerTiroir(); });
document.getElementById("voile").onclick = fermerTiroir;
window.addEventListener("hashchange", router);
construireNav();
presence();
setInterval(presence, 15000);
majEnvironnement().then(router);
