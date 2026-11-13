"""Le mur de l'enquêteur · le jeu.

    pip install -r app/requirements.txt
    python app/app.py                      # puis http://localhost:5000

La base : variable DATABASE_URL, par défaut postgresql://postgres@localhost:5433/lemur
(le serveur du TD, lancé par serveur/lancer-serveur.bat).

Le joueur a un délai par affaire. Chaque action (interroger, enquête de voisinage, fouiller un lieu,
analyser un scellé) est une ligne de la table actions : c'est la base qui fixe sa durée et qui refuse
de dépasser le délai (trigger avant_action, RG11). L'application ne montre que ce que le joueur a
découvert, et ne lit le coupable qu'après l'accusation, faite par la fonction accuser() (RG12).
"""

import math
import os
import random
from datetime import timedelta

import psycopg
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from psycopg.rows import dict_row

DSN = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost:5433/lemur")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "le-mur-dev")

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
COULEUR_LIEN = {"dette": "rouge", "rivalite": "rouge", "ex": "rouge", "couple": "orange",
                "famille": "noir", "ami": "vert", "collegue": "gris"}
LIBELLE_LIEN = {"dette": "dette", "rivalite": "rivalité", "ex": "ex", "couple": "couple",
                "famille": "famille", "ami": "ami·e", "collegue": "collègue"}


def db():
    return psycopg.connect(DSN, row_factory=dict_row, autocommit=True, options="-c TimeZone=Europe/Paris")


def lire(sql, *params):
    with db() as c:
        return c.execute(sql, params).fetchall()


def un(sql, *params):
    lignes = lire(sql, *params)
    return lignes[0] if lignes else None


def joueur():
    if "joueur_id" not in session:
        return None
    return un("SELECT * FROM joueurs WHERE id = %s", session["joueur_id"])


PEAUX = ["#f3d2b3", "#e8b98f", "#d39a6a", "#b0764a", "#8a5634", "#5e3a22"]
CHEVEUX = ["#1c1a18", "#3b2a1e", "#6b4423", "#a8743f", "#d9b26f", "#8c8c8c", "#e8e2d6", "#7a2b1b"]
VESTES = ["#2b3340", "#4a2f2a", "#33452f", "#5b4b3a", "#28243a", "#6a6a6a", "#7b2c2c", "#1f3b4d"]


@app.template_global()
def portrait(pid):
    """Un portrait-robot dessiné, toujours le même pour une même personne (tiré au sort à partir de son id)."""
    r = random.Random(pid * 7919)
    return {"peau": r.choice(PEAUX), "cheveux": r.choice(CHEVEUX), "veste": r.choice(VESTES),
            "coiffure": r.choice(["court", "court", "long", "boucles", "chignon", "chauve", "raie"]),
            "bouche": r.choice(["droite", "sourire", "moue", "pincee"]),
            "sourcils": r.choice(["droits", "hauts", "fronces"]),
            "lunettes": r.random() < .3, "barbe": r.random() < .18, "moustache": r.random() < .2,
            "chapeau": r.random() < .14, "boucle": r.random() < .25, "cicatrice": r.random() < .1,
            "col": r.choice(["chemise", "roule", "cravate", "noeud"]), "dx": r.uniform(-2.5, 2.5)}


@app.template_filter("hm")
def hm(d):
    return f"{d:%H}h{d:%M}" if d else ""


@app.template_filter("jour")
def jour(d):
    return f"{JOURS[d.weekday()]} {d:%d/%m} · {d:%H}h{d:%M}"


@app.template_filter("duree")
def duree(minutes):
    h, m = divmod(int(minutes), 60)
    return f"{h} h" + (f" {m:02d}" if m else "")


@app.template_filter("a_lieu")
def a_lieu(nom):
    """« au Bar Le Corbeau », « à la Gare centrale », « à l'Hôtel des Glycines »."""
    if nom[0] in "AEÉIOUH":
        return "à l'" + nom
    if nom.split()[0] in ("Gare", "Pharmacie", "Salle", "Bibliothèque", "Laverie", "Patinoire"):
        return "à la " + nom
    return ("aux " if nom.startswith("Serres") else "au ") + nom


@app.template_filter("valeur")
def valeur(v):
    """Une caractéristique d'indice, lisible : une heure ISO devient « 18h40 », True devient « oui »."""
    if isinstance(v, bool):
        return "oui" if v else "non"
    if isinstance(v, str) and len(v) >= 16 and v[4] == "-" and v[10] == "T":
        return f"{v[11:13]}h{v[14:16]}"
    if isinstance(v, int) and v >= 1000:
        return f"{v:,}".replace(",", " ")
    return v


@app.template_filter("creneau")
def creneau(r):
    return f"de {hm(r.lower)} à {hm(r.upper)}" if r else ""


# ---------- l'accueil ----------

@app.get("/")
def accueil():
    j = joueur()
    affaires = lire("""
        SELECT a.code, a.titre, a.nature, a.crime_le, a.delai_minutes, l.nom AS lieu,
               (SELECT max(score) FROM parties p WHERE p.affaire_id = a.id AND p.joueur_id = %s) AS mon_score,
               (SELECT bool_or(reussie) FROM parties p WHERE p.affaire_id = a.id AND p.joueur_id = %s) AS resolue,
               EXISTS (SELECT 1 FROM parties p WHERE p.affaire_id = a.id AND p.joueur_id = %s AND p.accuse_id IS NULL) AS en_cours,
               (SELECT count(*) FROM parties p WHERE p.affaire_id = a.id AND p.reussie) AS resolue_par
        FROM affaires_publiques a JOIN lieux l ON l.id = a.lieu_crime_id ORDER BY a.code""",
                    *([j["id"] if j else None] * 3))
    classement = lire("""
        SELECT j.pseudo, count(*) FILTER (WHERE pa.reussie) AS resolues, count(*) AS jouees,
               coalesce(sum(pa.score), 0) AS points
        FROM joueurs j JOIN parties pa ON pa.joueur_id = j.id AND pa.accuse_id IS NOT NULL
        GROUP BY j.id ORDER BY points DESC, resolues DESC LIMIT 10""")
    return render_template("accueil.html", j=j, affaires=affaires, classement=classement)


@app.post("/connexion")
def connexion():
    pseudo = request.form.get("pseudo", "").strip()[:20]
    if len(pseudo) < 2:
        flash("Un nom de code fait au moins 2 caractères.")
        return redirect(url_for("accueil"))
    with db() as c:
        c.execute("INSERT INTO joueurs (pseudo) VALUES (%s) ON CONFLICT (pseudo) DO NOTHING", (pseudo,))
        session["joueur_id"] = c.execute("SELECT id FROM joueurs WHERE pseudo = %s", (pseudo,)).fetchone()["id"]
    return redirect(url_for("accueil"))


@app.get("/deconnexion")
def deconnexion():
    session.clear()
    return redirect(url_for("accueil"))


# ---------- une partie ----------

def affaire_publique(code):
    return un("""SELECT a.*, l.nom AS lieu FROM affaires_publiques a JOIN lieux l ON l.id = a.lieu_crime_id
                 WHERE a.code = %s""", code) or abort(404)


def partie_en_cours(j, affaire_id, creer):
    p = un("SELECT * FROM parties WHERE joueur_id = %s AND affaire_id = %s AND accuse_id IS NULL", j["id"], affaire_id)
    if p is None and creer:
        # RG10 : l'index unique partiel empêche deux parties en cours, même avec deux onglets.
        with db() as c:
            c.execute("INSERT INTO parties (joueur_id, affaire_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                      (j["id"], affaire_id))
        p = partie_en_cours(j, affaire_id, False)
    return p


@app.get("/affaire/<code>")
def affaire(code):
    j = joueur()
    if not j:
        return redirect(url_for("accueil"))
    a = affaire_publique(code)
    p = partie_en_cours(j, a["id"], creer=True)
    t = un("SELECT * FROM temps_parties WHERE partie_id = %s", p["id"])
    actions = lire("""
        SELECT ac.*, coalesce(pe.prenom || ' ' || pe.nom, l.nom, i.scelle || ' · ' || i.libelle) AS cible,
               a.enquete_le + make_interval(mins => sum(ac.duree) OVER (ORDER BY ac.id)::int) AS horloge
        FROM actions ac JOIN affaires_publiques a ON a.id = ac.affaire_id
        LEFT JOIN personnes pe ON pe.id = ac.personne_id LEFT JOIN lieux l ON l.id = ac.lieu_id
        LEFT JOIN indices i ON i.id = ac.indice_id
        WHERE ac.partie_id = %s ORDER BY ac.id""", p["id"])
    interroges = {x["personne_id"] for x in actions if x["type"] == "interroger"}
    voisinage = {x["personne_id"] for x in actions if x["type"] == "voisinage"}
    fouilles = {x["lieu_id"] for x in actions if x["type"] == "fouiller"}
    analyses = {x["indice_id"] for x in actions if x["type"] == "analyser"}
    bareme = {x["code"]: x["duree"] for x in lire("SELECT code, duree FROM types_action")}
    bareme_labo = {x["code"]: x for x in lire("SELECT * FROM types_indice")}

    personnes = lire("""SELECT p.*, i.role FROM implications i JOIN personnes p ON p.id = i.personne_id
                        WHERE i.affaire_id = %s ORDER BY array_position(ARRAY['victime','suspect','temoin'], i.role),
                        p.nom""", a["id"])
    noms = {x["id"]: f"{x['prenom']} {x['nom']}" for x in personnes}
    declarations = lire("""
        SELECT d.*, l.nom AS lieu, g.prenom || ' ' || g.nom AS garant
        FROM declarations d JOIN lieux l ON l.id = d.lieu_id LEFT JOIN personnes g ON g.id = d.garant_id
        WHERE d.affaire_id = %s AND d.personne_id = ANY(%s)""", a["id"], list(interroges))
    decl = {}
    for d in declarations:
        decl.setdefault(d["personne_id"], []).append(d)

    indices = lire("""
        SELECT ix.*, l.nom AS lieu, ti.libelle AS type_libelle, ti.duree_analyse
        FROM indices ix JOIN lieux l ON l.id = ix.lieu_id JOIN types_indice ti ON ti.code = ix.type
        WHERE ix.affaire_id = %s AND ix.lieu_id = ANY(%s) ORDER BY ix.scelle""", a["id"], list(fouilles))
    designations = lire("""
        SELECT dz.indice_id, dz.fiabilite, p.prenom || ' ' || p.nom AS personne
        FROM designations dz JOIN personnes p ON p.id = dz.personne_id
        WHERE dz.indice_id = ANY(%s) ORDER BY dz.fiabilite DESC""", list(analyses))
    presences = lire("""
        SELECT pr.*, pe.prenom || ' ' || pe.nom AS personne, l.nom AS lieu
        FROM presences pr JOIN personnes pe ON pe.id = pr.personne_id JOIN lieux l ON l.id = pr.lieu_id
        WHERE pr.indice_id = ANY(%s)""", list(analyses))
    for ix in indices:
        ix["analyse"] = ix["id"] in analyses
        ix["designe"] = [d for d in designations if d["indice_id"] == ix["id"]]
        ix["presences"] = [x for x in presences if x["indice_id"] == ix["id"]]

    # Les lieux connus : le lieu du crime, ceux cités dans les déclarations, ceux où un scellé situe quelqu'un.
    connus = {a["lieu_crime_id"]} | {d["lieu_id"] for d in declarations} | {x["lieu_id"] for x in presences}
    lieux = lire("""SELECT l.*, (SELECT count(*) FROM indices i WHERE i.affaire_id = %s AND i.lieu_id = l.id
                    AND l.id = ANY(%s)) AS nb_scelles FROM lieux l WHERE l.id = ANY(%s) ORDER BY l.nom""",
                 a["id"], list(fouilles), list(connus))
    for l in lieux:
        l["fouille"] = l["id"] in fouilles
        l["crime"] = l["id"] == a["lieu_crime_id"]

    liens = lire("""SELECT li.*, pa.prenom || ' ' || pa.nom AS nom_a, pb.prenom || ' ' || pb.nom AS nom_b
                    FROM liens li JOIN personnes pa ON pa.id = li.personne_a JOIN personnes pb ON pb.id = li.personne_b
                    WHERE li.personne_a = ANY(%s) OR li.personne_b = ANY(%s)""", list(voisinage), list(voisinage))

    nouveau = request.args.get("nouveau", "")
    notif = compte_rendu(nouveau, actions, a, noms, decl, declarations, presences, indices, liens,
                         {l["id"]: l["nom"] for l in lieux}, t)
    return render_template(
        "affaire.html", notif=notif, j=j, a=a, p=p, t=t, actions=actions, personnes=personnes, decl=decl,
        interroges=interroges, voisinage=voisinage, indices=indices, lieux=lieux, liens=liens,
        bareme=bareme, bareme_labo=bareme_labo, nouveau=nouveau, avant=request.args.get("avant", type=int),
        mur=mur(personnes, liens, int(nouveau.split("-")[1]) if nouveau.startswith("voisinage-") else None), frise=frise(a, personnes, declarations, presences, noms),
        fin_enquete=a["enquete_le"] + timedelta(minutes=a["delai_minutes"]),
        epuise=t["restant"] < min(bareme["voisinage"], 60))


def compte_rendu(nouveau, actions, a, noms, decl, declarations, presences, indices, liens, nom_lieu, t):
    """Ce que la dernière action a rapporté, dit clairement, avec les liens vers où le voir."""
    if not nouveau or not actions or "-" not in nouveau:
        return None
    type_, cible = nouveau.split("-", 1)
    dern = actions[-1]
    if dern["type"] != type_ or not cible.isdigit():
        return None
    cible = int(cible)
    n = {"cout": dern["duree"], "restant": t["restant"], "lignes": [], "liens": [], "sorte": type_}

    def lieux_neufs(ids, sauf_decl=None, sauf_pres=None):
        autres = ({a["lieu_crime_id"]} | {d["lieu_id"] for d in declarations if d["personne_id"] != sauf_decl}
                  | {x["lieu_id"] for x in presences if x["indice_id"] != sauf_pres})
        return [(i, nom_lieu[i]) for i in dict.fromkeys(ids) if i not in autres and i in nom_lieu]

    if type_ == "interroger":
        qui = noms.get(cible, "?")
        n["titre"] = f"Interrogatoire {('d’' if qui[:1] in 'AEÉIOUYH' else 'de ')}{qui}"
        for d in decl.get(cible, []):
            n["lignes"].append(f"Dit avoir été {a_lieu(d['lieu'])}, {creneau(d['creneau'])}"
                               + (f", avec {d['garant']}." if d["garant"] else ", sans personne pour le confirmer."))
        if not decl.get(cible):
            n["lignes"].append("N'a rien voulu déclarer.")
        neufs = lieux_neufs([d["lieu_id"] for d in decl.get(cible, [])], sauf_decl=cible)
        n["liens"].append(("Lire sa déposition", f"#interroger-{cible}"))
        if neufs:
            n["lignes"].append("Nouveau lieu à fouiller : " + ", ".join(nom for _, nom in neufs) + ".")
            n["liens"].append(("Aller au lieu", f"#fouiller-{neufs[0][0]}"))
        n["liens"].append(("Chronologie", "#chronologie"))
    elif type_ == "voisinage":
        qui = noms.get(cible) or next((l["nom_a"] if l["personne_a"] == cible else l["nom_b"] for l in liens
                                       if cible in (l["personne_a"], l["personne_b"])), "?")
        n["titre"] = f"Voisinage autour de {qui}"
        siens = [l for l in liens if cible in (l["personne_a"], l["personne_b"])]
        for l in siens:
            autre = l["nom_b"] if l["personne_a"] == cible else l["nom_a"]
            n["lignes"].append(f"{LIBELLE_LIEN[l['type']].capitalize()} avec {autre}")
        if not siens:
            n["lignes"].append("Personne ne lui connaît de lien.")
        n["resume"] = f"{len(siens)} lien{'s' if len(siens) > 1 else ''} épinglé{'s' if len(siens) > 1 else ''} sur le mur"
        n["liens"].append(("Voir le mur", "#mur"))
    elif type_ == "fouiller":
        n["titre"] = f"Fouille {a_lieu(nom_lieu.get(cible, '?'))}"
        trouves = [ix for ix in indices if ix["lieu_id"] == cible]
        for ix in trouves:
            n["lignes"].append(f"{ix['scelle']} · {ix['libelle']} (labo {duree(ix['duree_analyse'])})")
        n["resume"] = (f"{len(trouves)} scellé{'s' if len(trouves) > 1 else ''} saisi{'s' if len(trouves) > 1 else ''}"
                       if trouves else "Rien trouvé : du temps perdu.")
        if trouves:
            n["liens"].append(("Voir les scellés", f"#analyser-{trouves[0]['id']}"))
    elif type_ == "analyser":
        ix = next((x for x in indices if x["id"] == cible), None)
        if not ix:
            return None
        n["titre"] = f"Labo : {ix['libelle']}"
        for d in ix["designe"]:
            n["lignes"].append(f"Désigne {d['personne']} (fiabilité {d['fiabilite']} %)")
        for x in ix["presences"]:
            n["lignes"].append(f"Situe {x['personne']} {a_lieu(x['lieu'])}, {creneau(x['creneau'])}")
        if not ix["designe"] and not ix["presences"]:
            n["lignes"].append("Ne désigne personne : une impasse.")
        neufs = lieux_neufs([x["lieu_id"] for x in ix["presences"]], sauf_pres=cible)
        if neufs:
            n["lignes"].append("Nouveau lieu à fouiller : " + ", ".join(nom for _, nom in neufs) + ".")
            n["liens"].append(("Aller au lieu", f"#fouiller-{neufs[0][0]}"))
        n["liens"].insert(0, ("Lire le rapport du labo", f"#analyser-{cible}"))
        if ix["presences"]:
            n["liens"].append(("Comparer sur la chronologie", "#chronologie"))
    return n


@app.post("/affaire/<code>/action")
def agir(code):
    j = joueur() or abort(403)
    a = affaire_publique(code)
    p = partie_en_cours(j, a["id"], creer=False)
    if not p:
        return redirect(url_for("affaire", code=code))
    type_ = request.form["type"]
    cible = int(request.form["cible"])
    colonne = {"interroger": "personne_id", "voisinage": "personne_id", "fouiller": "lieu_id",
               "analyser": "indice_id"}.get(type_) or abort(400)
    avant = un("SELECT utilise FROM temps_parties WHERE partie_id = %s", p["id"])["utilise"]
    try:
        with db() as c:
            # La base fixe la durée (barème) et refuse de dépasser le délai (RG11) : duree=1 est écrasée.
            c.execute(f"""INSERT INTO actions (partie_id, affaire_id, type, {colonne}, duree)
                          VALUES (%s, %s, %s, %s, 1) ON CONFLICT DO NOTHING""", (p["id"], a["id"], type_, cible))
    except psycopg.errors.RaiseException as e:
        flash("Plus assez de temps pour ça. " + str(e).split(":", 1)[-1].strip().split("\n")[0])
        return redirect(url_for("affaire", code=code))
    except psycopg.errors.ForeignKeyViolation:
        abort(400)
    ancre = f"#{type_}-{cible}"
    if type_ == "voisinage":
        ancre = "#mur"
    return redirect(url_for("affaire", code=code, nouveau=f"{type_}-{cible}", avant=avant) + ancre)


@app.post("/affaire/<code>/accuser")
def accuser(code):
    j = joueur() or abort(403)
    a = affaire_publique(code)
    p = partie_en_cours(j, a["id"], creer=False) or abort(409)
    try:
        with db() as c:
            fin = c.execute("SELECT * FROM accuser(%s, %s)", (p["id"], int(request.form["suspect"]))).fetchone()
    except psycopg.errors.ForeignKeyViolation:
        abort(400, "On n'accuse qu'un suspect de l'affaire (RG12).")
    return redirect(url_for("resultat", partie_id=fin["id"]))


@app.get("/partie/<int:partie_id>")
def resultat(partie_id):
    j = joueur()
    p = un("""SELECT pa.*, a.code, a.titre, a.coupable_id, a.crime_le, a.delai_minutes, l.nom AS lieu_crime,
                     acc.prenom || ' ' || acc.nom AS accuse, cou.prenom || ' ' || cou.nom AS coupable,
                     t.utilise, t.restant
              FROM parties pa JOIN affaires a ON a.id = pa.affaire_id JOIN lieux l ON l.id = a.lieu_crime_id
              JOIN personnes acc ON acc.id = pa.accuse_id JOIN personnes cou ON cou.id = a.coupable_id
              JOIN temps_parties t ON t.partie_id = pa.id
              WHERE pa.id = %s AND pa.accuse_id IS NOT NULL""", partie_id) or abort(404)
    # La solution, lue dans la base : le mobile, l'alibi menteur (requête Q2), et le garant complice.
    mobile = un("""SELECT li.type FROM liens li JOIN implications v ON v.affaire_id = %s AND v.role = 'victime'
                   WHERE (li.personne_a, li.personne_b) IN ((least(v.personne_id, %s), greatest(v.personne_id, %s)))""",
                p["affaire_id"], p["coupable_id"], p["coupable_id"])
    mensonges = lire("""
        SELECT ld.nom AS dit, lp.nom AS etait, pr.creneau, ix.scelle, ix.libelle
        FROM declarations d
        JOIN presences pr ON pr.personne_id = d.personne_id AND pr.creneau && d.creneau AND pr.lieu_id <> d.lieu_id
        JOIN lieux ld ON ld.id = d.lieu_id JOIN lieux lp ON lp.id = pr.lieu_id
        LEFT JOIN indices ix ON ix.id = pr.indice_id
        WHERE d.affaire_id = %s AND d.personne_id = %s""", p["affaire_id"], p["coupable_id"])
    garant = un("""SELECT g.prenom || ' ' || g.nom AS nom FROM declarations d JOIN personnes g ON g.id = d.garant_id
                   WHERE d.affaire_id = %s AND d.personne_id = %s""", p["affaire_id"], p["coupable_id"])
    nb = un("SELECT count(*) AS n FROM actions WHERE partie_id = %s", partie_id)["n"]
    return render_template("resultat.html", j=j, p=p, mobile=mobile and LIBELLE_LIEN[mobile["type"]],
                           mensonges=mensonges, garant=garant, nb=nb)


# ---------- le mur et la frise : calculés ici, dessinés en SVG ----------

def mur(personnes, liens, neuf_de=None):
    """Les personnes de l'affaire (et les proches découverts) en cercle autour de la victime."""
    W, H = 1040, 720
    cx, cy = W / 2, H / 2
    victime = [x for x in personnes if x["role"] == "victime"]
    autour = [x for x in personnes if x["role"] != "victime"]
    ids = {x["id"] for x in personnes}
    proches = {}
    for l in liens:
        for pid, nom in ((l["personne_a"], l["nom_a"]), (l["personne_b"], l["nom_b"])):
            if pid not in ids:
                proches[pid] = {"id": pid, "nom": nom, "role": "proche"}
    pos = {v["id"]: (cx, cy) for v in victime}
    for k, x in enumerate(autour):
        t = 2 * math.pi * k / len(autour) - math.pi / 2
        pos[x["id"]] = (cx + 330 * math.cos(t), cy + 255 * math.sin(t))
    for k, x in enumerate(proches.values()):
        t = 2 * math.pi * (k + 0.5) / max(len(proches), 1) + 0.3
        pos[x["id"]] = (cx + 455 * math.cos(t), cy + 300 * math.sin(t))
    noeuds = []
    for k, x in enumerate(victime + autour + list(proches.values())):
        nom = x["nom"] if x["role"] == "proche" else f"{x['prenom']} {x['nom']}"
        noeuds.append({"id": x["id"], "nom": nom, "role": x["role"], "x": pos[x["id"]][0], "y": pos[x["id"]][1],
                       "rot": ((x["id"] * 37) % 9) - 4, "teinte": (x["id"] * 47) % 360,
                       "initiales": "".join(m[0] for m in nom.split()[:2])})
    fils, relies = [], set()
    for k, l in enumerate(sorted(liens, key=lambda l: (neuf_de not in (l["personne_a"], l["personne_b"]), l["type"]))):
        (x1, y1), (x2, y2) = pos[l["personne_a"]], pos[l["personne_b"]]
        relies |= {l["personne_a"], l["personne_b"]}
        # un fil qui pend un peu, comme un vrai fil tendu entre deux punaises
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 + 18
        libelle = LIBELLE_LIEN[l["type"]]
        neuf = neuf_de is not None and neuf_de in (l["personne_a"], l["personne_b"])
        fils.append({"d": f"M{x1:.0f},{y1 - 52:.0f} Q{mx:.0f},{my - 52:.0f} {x2:.0f},{y2 - 52:.0f}",
                     "lx": mx, "ly": (y1 + y2) / 4 + my / 2 - 52, "type": libelle, "couleur": COULEUR_LIEN[l["type"]],
                     "largeur": 16 + 9 * len(libelle), "neuf": neuf, "retard": round(0.3 + 0.35 * k, 2) if neuf else 0,
                     "a": l["personne_a"], "b": l["personne_b"], "nom_a": l["nom_a"], "nom_b": l["nom_b"],
                     "longueur": math.hypot(x2 - x1, y2 - y1) + 40})
    for n in noeuds:
        n["relie"] = n["id"] in relies
        n["neuf"] = neuf_de is not None and any(f["neuf"] and n["id"] in (f["a"], f["b"]) for f in fils)
    return {"W": W, "H": H, "noeuds": noeuds, "fils": fils}


def frise(a, personnes, declarations, presences, noms):
    """La chronologie de la soirée : ce que chacun déclare, et ce que les scellés prouvent."""
    lignes = {}
    for d in declarations:
        lignes.setdefault(d["personne_id"], {"declare": [], "atteste": []})["declare"].append(d)
    for x in presences:
        lignes.setdefault(x["personne_id"], {"declare": [], "atteste": []})["atteste"].append(x)
    if not lignes:
        return None
    bornes = [a["crime_le"] - timedelta(hours=2), a["crime_le"] + timedelta(hours=2)]
    for v in lignes.values():
        for e in v["declare"] + v["atteste"]:
            bornes += [e["creneau"].lower, e["creneau"].upper]
    t0 = min(bornes).replace(minute=0, second=0)
    t1 = max(bornes)
    duree_tot = (t1 - t0).total_seconds()
    G, W = 170, 900

    def x(t):
        return G + (W - G - 20) * (t - t0).total_seconds() / duree_tot

    rangs = []
    for k, (pid, v) in enumerate(sorted(lignes.items(), key=lambda kv: noms.get(kv[0], ""))):
        y = 40 + k * 46
        barres = [{"x": x(e["creneau"].lower), "w": max(4, x(e["creneau"].upper) - x(e["creneau"].lower)),
                   "y": y, "lieu": e["lieu"], "texte": f"{hm(e['creneau'].lower)}–{hm(e['creneau'].upper)}",
                   "sorte": sorte} for sorte, liste in (("declare", v["declare"]), ("atteste", v["atteste"]))
                  for e in liste]
        rangs.append({"nom": noms.get(pid, "?"), "y": y, "barres": barres})
    heures = []
    t = t0
    while t <= t1:
        heures.append({"x": x(t), "texte": hm(t)})
        t += timedelta(hours=1)
    return {"W": W, "H": 60 + 46 * len(rangs), "rangs": rangs, "heures": heures, "crime_x": x(a["crime_le"])}


if __name__ == "__main__":
    app.run(debug=True)
