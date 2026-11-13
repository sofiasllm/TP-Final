"""Le mur de l'enquêteur · générateur d'affaires.

Écrit un fichier SQL qui remplit la base avec des affaires jouables. Chaque affaire est construite
comme une vraie enquête :
- un coupable tiré au sort parmi sept suspects, tous avec un mobile envers la victime (le sien est le seul
  de son genre : c'est ce que sait le proche) ;
- un alibi qui ment, couvert par un ami (lui aussi témoin, et menteur) ;
- deux façons indépendantes de le confondre : un relevé d'antenne qui le place sur les lieux à l'heure
  du crime, et un proche de la victime qui sait quel genre de personne elle attendait (le mur dit qui) ;
- une fausse piste solide : un suspect sans alibi, ses empreintes sur place (laissées des heures plus
  tôt) et une lettre de menace ;
- des indices dont le prix suit la valeur : le relevé d'antenne (8 h) prouve tout, la trace ADN (6 h) désigne le
  coupable sans dire quand, les objets (1 h) ne disent presque rien ;
- des innocents qu'on peut tous blanchir, chacun par une preuve d'un autre genre : caméra, antenne, reçu de
  carte bancaire, et un menteur qui cache autre chose (il jouait au casino) mais pas un crime.
Le joueur a un délai : il ne peut pas tout analyser, il doit choisir.

    python modele/generer.py                 # 6 affaires, graine 42, dans modele/donnees.sql
    python modele/generer.py --affaires 20 --graine 7

Puis : psql -h localhost -p 5433 -U postgres -d lemur -f modele/donnees.sql
Uniquement la bibliothèque standard de Python.
"""

import argparse
import json
import random
from datetime import datetime, timedelta, date
from pathlib import Path

PRENOMS = ["Adèle", "Basile", "Camille", "Dimitri", "Élise", "Fabien", "Garance", "Hugo", "Inès", "Jules",
           "Katia", "Léon", "Margaux", "Nadir", "Odile", "Paul", "Quentin", "Rose", "Samir", "Thaïs",
           "Ugo", "Violette", "Wassim", "Yasmine", "Zoé", "Anouk", "Bruno", "Clarisse", "Étienne", "Lina"]
NOMS = ["Lacombe", "Vasseur", "Delorme", "Marchetti", "Ribeiro", "Fontaine", "Kerjean", "Duval", "Benali",
        "Moreau", "Castel", "Lindqvist", "Petitjean", "Roussel", "Nguyen", "Arnaud", "Brisset", "Coste",
        "Le Gall", "Mercier", "Okafor", "Perrin", "Sorel", "Thibault", "Vidal", "Weber", "Zanetti"]
PROFESSIONS = ["notaire", "fleuriste", "antiquaire", "journaliste", "concierge", "comptable", "taxidermiste",
               "chimiste", "garagiste", "accordéoniste", "pilote de ligne", "libraire", "architecte", "dentiste",
               "photographe", "illusionniste", "astrologue", "pianiste", "guide de musée", "dresseur de perroquets"]
VILLE = "Brumeville"
LIEUX = [("Bar Le Corbeau", "bar"), ("Hôtel des Glycines", "hôtel"), ("Gare centrale", "gare"),
         ("Musée des Automates", "musée"), ("Cinéma Le Rex", "cinéma"), ("Pharmacie du Port", "commerce"),
         ("Salle de sport Titan", "sport"), ("Bibliothèque municipale", "public"), ("Parking Saint-Roch", "parking"),
         ("Casino du Lac", "casino"), ("Théâtre des Ombres", "théâtre"), ("Laverie Bulle", "commerce"),
         ("Marché couvert", "marché"), ("Club de jazz La Cave", "bar"), ("Garage Moreau", "garage"),
         ("Port de plaisance", "port"), ("Restaurant L'Ancre", "restaurant"), ("Serres du jardin botanique", "parc"),
         ("Manoir Vasseur", "demeure"), ("Atelier de l'horloger", "atelier"), ("Patinoire municipale", "sport"),
         ("Phare de la Pointe", "phare")]
NATURES = {
    "meurtre": ("On a retrouvé le corps {de_v} {l}, vers {h}. Une lutte brève, aucun témoin direct.", "Mort {l}"),
    "vol": ("Le diamant « Œil de Brume », confié à {v}, a disparu {l} vers {h}. La vitrine n'a pas été forcée.",
            "Le diamant envolé {l}"),
    "empoisonnement": ("Le verre {de_v} contenait de l'arsenic. La victime s'est effondrée {l} vers {h}.",
                       "Un dernier verre {l}"),
    "incendie": ("L'atelier {de_v} a brûlé. Le feu a été allumé {l} vers {h}, avec de l'essence à briquet.",
                 "Le feu {l}"),
    "enlèvement": ("Capitaine, le perroquet savant {de_v}, a été enlevé {l} vers {h}. Il connaît le code du coffre.",
                   "Le perroquet disparu {l}"),
}
# Chaque mobile : le type de lien sur le mur, la pièce qui le prouve, et ce qu'en sait un proche de la victime.
MOBILES = {
    "dette": ("Reconnaissance de dette", "quelqu'un qui lui devait beaucoup d'argent"),
    "ex": ("Lettres d'amour déchirées", "une ancienne histoire d'amour, qu'elle croyait finie"),
    "rivalite": ("Contrat perdu au profit de la victime", "un rival, qui ne digérait pas d'avoir perdu"),
    "famille": ("Testament modifié la semaine dernière", "quelqu'un de sa propre famille"),
}
DELAIS = [30, 28, 26]          # heures d'enquête, de plus en plus serrées


def a_lieu(nom):
    """« au Bar Le Corbeau », « à la Gare centrale », « à l'Hôtel des Glycines »."""
    feminins = ("Gare", "Pharmacie", "Salle", "Bibliothèque", "Laverie", "Patinoire")
    if nom[0] in "AEÉIOUH":
        return "à l'" + nom
    if nom.split()[0] in feminins:
        return "à la " + nom
    if nom.startswith("Serres"):
        return "aux " + nom
    return "au " + nom


def de(nom):
    return ("d'" if nom[0] in "AEÉIOUYH" else "de ") + nom


def q(v):
    """Une valeur Python en littéral SQL."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, datetime):
        return "'" + v.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(v, date):
        return "'" + v.isoformat() + "'"
    return "'" + str(v).replace("'", "''") + "'"


def creneau(debut, fin):
    return f"tstzrange({q(debut)}, {q(fin)})"


def hm(d):
    return d.strftime("%Hh%M")


class Generateur:
    def __init__(self, graine):
        self.r = random.Random(graine)
        self.sql = []
        self.ids = {"personne": 0, "indice": 0}
        self.scelles = []
        self.noms = {}
        self.prenoms_libres = []
        self.noms_libres = []

    def emit(self, ligne):
        self.sql.append(ligne)

    def lieux(self):
        self.emit("-- Les lieux de Brumeville")
        for i, (nom, type_) in enumerate(LIEUX, 1):
            self.emit(f"INSERT INTO lieux (id, nom, ville, type) OVERRIDING SYSTEM VALUE "
                      f"VALUES ({i}, {q(nom)}, {q(VILLE)}, {q(type_)});")

    def personne(self):
        self.ids["personne"] += 1
        pid = self.ids["personne"]
        prenom = self.prenoms_libres.pop()                   # pas deux mêmes prénoms dans une affaire
        nom = self.noms_libres.pop()                         # ni deux mêmes noms, sauf dans une famille
        self.noms[pid] = (prenom, nom)
        naissance = date(self.r.randint(1950, 2003), self.r.randint(1, 12), self.r.randint(1, 28))
        self.emit(f"INSERT INTO personnes (id, matricule, nom, prenom, naissance, profession) OVERRIDING SYSTEM VALUE "
                  f"VALUES ({pid}, 'P-{pid:05d}', {q(nom)}, {q(prenom)}, {q(naissance)}, "
                  f"{q(self.r.choice(PROFESSIONS))});")
        return pid

    def nom(self, pid):
        return " ".join(self.noms[pid])

    def indice(self, affaire, lieu, type_, libelle, trouve, carac, designe=()):
        self.ids["indice"] += 1
        iid = self.ids["indice"]
        scelle = self.scelles.pop()
        self.emit(f"INSERT INTO indices (id, scelle, affaire_id, lieu_id, type, libelle, trouve_le, caracteristiques) "
                  f"OVERRIDING SYSTEM VALUE VALUES ({iid}, 'SC-{scelle:05d}', {affaire}, {lieu}, {q(type_)}, "
                  f"{q(libelle)}, {q(trouve)}, {q(json.dumps(carac, ensure_ascii=False))}::jsonb);")
        for pid, fiab in designe:
            self.emit(f"INSERT INTO designations VALUES ({iid}, {pid}, {fiab});")
        return iid

    def presence(self, pid, lieu, debut, fin, indice):
        self.emit(f"INSERT INTO presences (personne_id, lieu_id, creneau, indice_id) "
                  f"VALUES ({pid}, {lieu}, {creneau(debut, fin)}, {indice});")

    def declaration(self, affaire, pid, faite, lieu, debut, fin, garant, texte):
        self.emit(f"INSERT INTO declarations (affaire_id, personne_id, faite_le, lieu_id, creneau, garant_id, texte) "
                  f"VALUES ({affaire}, {pid}, {q(faite)}, {lieu}, {creneau(debut, fin)}, {q(garant)}, {q(texte)});")

    def lien(self, a, b, type_, depuis):
        a, b = min(a, b), max(a, b)
        self.emit(f"INSERT INTO liens VALUES ({a}, {b}, {q(type_)}, {q(depuis)}) ON CONFLICT DO NOTHING;")

    def piece_mobile(self, n, mobile, lieu, pid, trouve):
        """La pièce qui prouve un mobile ; elle désigne le suspect, sans prouver qu'il est coupable."""
        r = self.r
        libelle, _ = MOBILES[mobile]
        carac = {
            "dette": {"montant": r.randint(8, 90) * 1000, "echeance_depassee": True, "signature": "lisible"},
            "ex": {"nombre": r.randint(6, 30), "derniere_lettre": "« Tu le regretteras. »"},
            "rivalite": {"enjeu": r.choice(["un concours", "un marché public", "une exposition"]),
                         "montant_perdu": r.randint(20, 300) * 1000},
            "famille": {"notaire": f"Maître {r.choice(NOMS)}", "nouvel_heritier": "une association"},
        }[mobile]
        self.indice(n, lieu, "document", libelle, trouve, carac, [(pid, 60)])

    def affaire(self, n):
        r = self.r
        self.prenoms_libres = r.sample(PRENOMS, 14)
        self.noms_libres = r.sample(NOMS, 14)
        nature = list(NATURES)[(n - 1) % len(NATURES)]
        crime = datetime(2026, r.randint(1, 10), r.randint(1, 27), r.randint(19, 23), r.choice([0, 15, 30, 45]))
        debut_enquete = (crime + timedelta(days=1)).replace(hour=8, minute=0)
        delai = DELAIS[(n - 1) % len(DELAIS)] * 60
        lieux = r.sample(range(1, len(LIEUX) + 1), 11)
        l_crime, l_alibi, l_inno1, l_inno2, l_faux, l_proche, l_rien, l_inno3, l_inno4, l_casino, l_inno5 = lieux
        nom_lieu = LIEUX[l_crime - 1][0]
        nom_alibi = LIEUX[l_alibi - 1][0]

        # Les scellés sont numérotés au hasard : leur ordre ne trahit pas l'indice décisif.
        base = 100 + 40 * n
        self.scelles = r.sample(range(base, base + 40), 30)

        self.emit(f"\n-- ===== Affaire {n} : {nature} =====")
        self.emit("BEGIN;")
        victime = self.personne()
        suspects = [self.personne() for _ in range(7)]
        r.shuffle(suspects)                                     # le matricule ne trahit pas le coupable
        coupable, inno1, inno2, faux, inno3, menteur, inno5 = suspects
        proche, passant, habitue, complice = (self.personne() for _ in range(4))   # les témoins
        conjoint = self.personne()                              # sans rôle dans l'affaire (RG2 : 0,n)

        # Le mobile du coupable est le seul de son genre ; les six autres se partagent les trois autres genres.
        genres = r.sample(list(MOBILES), 4)
        autres = genres[1:] * 2
        r.shuffle(autres)
        mobile = dict(zip(suspects, [genres[0]] + autres))
        resume_modele, titre_modele = NATURES[nature]
        resume = resume_modele.format(v=self.nom(victime), de_v=de(self.nom(victime)), l=a_lieu(nom_lieu), h=hm(crime))
        self.emit(f"INSERT INTO affaires (id, code, titre, nature, resume, crime_le, lieu_crime_id, enquete_le, "
                  f"delai_minutes, coupable_id) OVERRIDING SYSTEM VALUE VALUES ({n}, 'AFF-2026-{n:03d}', "
                  f"{q(titre_modele.format(l=a_lieu(nom_lieu)))}, {q(nature)}, {q(resume)}, {q(crime)}, {l_crime}, "
                  f"{q(debut_enquete)}, {delai}, {coupable});")
        self.emit(f"INSERT INTO implications VALUES ({n}, {victime}, 'victime');")
        for s in suspects:
            self.emit(f"INSERT INTO implications VALUES ({n}, {s}, 'suspect');")
        for t in (proche, passant, habitue, complice):
            self.emit(f"INSERT INTO implications VALUES ({n}, {t}, 'temoin');")

        # La famille porte le nom de la victime (le suspect au mobile « famille », et le proche).
        for pid in [s for s in suspects if mobile[s] == "famille"] + [proche]:
            self.noms[pid] = (self.noms[pid][0], self.noms[victime][1])
            self.emit(f"UPDATE personnes SET nom = {q(self.noms[victime][1])} WHERE id = {pid};")

        # ---- Le mur : chaque suspect a un mobile différent envers la victime.
        for s in suspects:
            self.lien(s, victime, mobile[s], date(r.randint(2012, 2025), r.randint(1, 12), 1))
        self.lien(coupable, complice, "ami", date(r.randint(2005, 2018), 3, 1))
        self.lien(complice, inno2, "collegue", date(2022, 9, 1))
        self.lien(conjoint, faux, "couple", date(2024, 2, 14))
        self.lien(conjoint, victime, "collegue", date(2019, 5, 1))
        self.lien(proche, victime, "famille", date(1990, 1, 1))
        self.lien(passant, inno1, "ami", date(2015, 6, 1))
        self.lien(habitue, coupable, "collegue", date(2021, 1, 1))
        self.lien(inno3, inno5, "ami", date(2017, 4, 1))
        self.lien(menteur, habitue, "ami", date(2020, 10, 1))

        m = timedelta(minutes=1)
        h = timedelta(hours=1)
        matin = debut_enquete - timedelta(hours=r.randint(1, 5))   # les scellés relevés avant 8 h
        p_coup, p_comp = self.noms[coupable][0], self.noms[complice][0]

        nom_casino = LIEUX[l_casino - 1][0]
        # ---- Le lieu du crime : 7 scellés, 26 h d'analyse en tout. Il faut choisir.
        antenne = f"BRM-{r.randint(100, 999)}"
        i_bornage = self.indice(n, l_crime, "bornage", f"Relevé de l'antenne {antenne}", matin,
                                {"operateur": "BrumeTel", "antenne": antenne, "rayon_m": 150,
                                 "debut": (crime - 30 * m).isoformat(), "fin": (crime + 15 * m).isoformat(),
                                 "lignes_captees": 2}, [(coupable, 95), (passant, 90)])
        self.presence(coupable, l_crime, crime - 20 * m, crime + 10 * m, i_bornage)
        self.presence(passant, l_crime, crime - 25 * m, crime - 15 * m, i_bornage)   # parti avant le crime
        self.indice(n, l_crime, "empreinte", "Empreinte sur la poignée de la porte", matin,
                    {"doigt": "index droit", "qualite": "nette", "points_communs": 14}, [(faux, 85)])
        i_hall = self.indice(n, l_crime, "video", "Caméra du hall d'entrée", matin,
                             {"camera": "CAM-HALL", "debut": (crime - 6 * h).isoformat(),
                              "fin": (crime - 5 * h).isoformat(), "note": "la bande est effacée après 17 h"},
                             [(faux, 80)])
        self.presence(faux, l_crime, crime - 6 * h, crime - 5 * h, i_hall)
        self.indice(n, l_crime, "empreinte", "Empreinte partielle sur l'objet du crime", matin,
                    {"doigt": "pouce gauche", "qualite": "partielle", "points_communs": 7},
                    [(coupable, 55), (inno2, 25)])
        self.indice(n, l_crime, "adn", "Trace de sang sur l'objet du crime", matin,
                    {"labo": "Laboratoire de Brumeville", "resultat": "profil complet, sang frais",
                     "remarque": "ne dit pas à quelle heure"}, [(coupable, 80)])
        self.indice(n, l_crime, "objet", "Gant de cuir abandonné", matin,
                    {"taille": r.choice(["S", "M", "L"]), "odeur": "essence à briquet"}, [])
        self.indice(n, l_crime, "objet", "Ticket de vestiaire tombé dans le caniveau", matin,
                    {"etablissement": nom_alibi, "numero": r.randint(10, 99),
                     "remis_a": (crime + 45 * m).strftime("%Hh%M")}, [])

        # ---- Le coupable et son complice : ils disent avoir passé la soirée ensemble, ailleurs.
        lendemain = debut_enquete - timedelta(hours=2)
        self.declaration(n, coupable, lendemain, l_alibi, crime - 90 * m, crime + 60 * m, complice,
                         f"J'ai passé toute la soirée {a_lieu(nom_alibi)} avec {p_comp}. Demandez-lui.")
        self.declaration(n, complice, lendemain, l_alibi, crime - 90 * m, crime + 60 * m, coupable,
                         f"{p_coup} et moi, on était {a_lieu(nom_alibi)} dès le début de soirée. On n'a pas bougé.")
        i_entree = self.indice(n, l_alibi, "video", f"Caméra de l'entrée, {nom_alibi}", matin,
                               {"camera": "CAM-01", "debut": (crime + 40 * m).isoformat(),
                                "fin": (crime + 120 * m).isoformat(), "note": "deux personnes entrent ensemble"},
                               [(coupable, 90), (complice, 90)])
        self.presence(coupable, l_alibi, crime + 40 * m, crime + 120 * m, i_entree)
        self.presence(complice, l_alibi, crime + 40 * m, crime + 120 * m, i_entree)
        self.piece_mobile(n, mobile[coupable], l_alibi, coupable, matin)
        self.declaration(n, habitue, lendemain, l_alibi, crime + 30 * m, crime + 60 * m, None,
                         f"Je suis arrivé·e {a_lieu(nom_alibi)} vers {hm(crime + 30 * m)}. Il n'y avait personne "
                         "que je connaissais. Un peu plus tard, deux personnes sont entrées en riant trop fort.")

        # ---- Deux innocents : un mobile, mais un alibi qu'une caméra confirme.
        for pid, lieu in ((inno1, l_inno1), (inno2, l_inno2)):
            nom_l = LIEUX[lieu - 1][0]
            i = self.indice(n, lieu, "video", f"Caméra de surveillance, {nom_l}", matin,
                            {"camera": f"CAM-{r.randint(2, 9):02d}", "debut": (crime - 60 * m).isoformat(),
                             "fin": (crime + 30 * m).isoformat()}, [(pid, 85)])
            self.presence(pid, lieu, crime - 60 * m, crime + 30 * m, i)
            self.piece_mobile(n, mobile[pid], lieu, pid, matin)
            self.declaration(n, pid, lendemain, lieu, crime - 90 * m, crime + 60 * m, None,
                             f"J'étais {a_lieu(nom_l)}. Oui, je lui en voulais, mais je n'ai pas bougé de là-bas.")

        # ---- Un innocent que seule l'antenne de son quartier peut blanchir (cher : 5 h de labo).
        nom_l = LIEUX[l_inno3 - 1][0]
        antenne3 = f"BRM-{r.randint(100, 999)}"
        i = self.indice(n, l_inno3, "bornage", f"Relevé de l'antenne {antenne3}", matin,
                        {"operateur": "BrumeTel", "antenne": antenne3, "rayon_m": 300,
                         "debut": (crime - 90 * m).isoformat(), "fin": (crime + 45 * m).isoformat(),
                         "lignes_captees": 1}, [(inno3, 92)])
        self.presence(inno3, l_inno3, crime - 90 * m, crime + 45 * m, i)
        self.piece_mobile(n, mobile[inno3], l_inno3, inno3, matin)
        self.declaration(n, inno3, lendemain, l_inno3, crime - 120 * m, crime + 60 * m, None,
                         f"J'étais {a_lieu(nom_l)}, au téléphone avec ma sœur, une bonne heure. Vérifiez si vous voulez.")

        # ---- Un menteur, mais pas un meurtrier : il cache qu'il jouait au casino.
        nom_l = LIEUX[l_inno4 - 1][0]
        self.declaration(n, menteur, lendemain, l_inno4, crime - 120 * m, crime + 90 * m, None,
                         f"J'étais {a_lieu(nom_l)}, toute la soirée. Je ne vois pas ce que vous me voulez.")
        i = self.indice(n, l_casino, "video", f"Caméra de la salle de jeu, {nom_casino}", matin,
                        {"camera": "CAM-JEU", "debut": (crime - 80 * m).isoformat(),
                         "fin": (crime + 50 * m).isoformat(), "note": "une table de roulette, toujours la même personne"},
                        [(menteur, 88)])
        self.presence(menteur, l_casino, crime - 80 * m, crime + 50 * m, i)
        self.piece_mobile(n, mobile[menteur], l_inno4, menteur, matin)
        self.indice(n, l_inno4, "document", "Relance d'un créancier de jeu", matin,
                    {"montant": r.randint(3, 40) * 1000, "expediteur": "Cercle privé de Brumeville"}, [(menteur, 50)])
        self.declaration(n, habitue, lendemain + 10 * m, l_casino, crime - 70 * m, crime - 10 * m, None,
                         f"Avant d'aller ailleurs, j'ai perdu un peu {a_lieu(nom_casino)}. Il y avait les habitués de la "
                         "roulette, comme toujours, le nez sur le tapis.")

        # ---- Un innocent blanchi par sa carte bancaire.
        nom_l = LIEUX[l_inno5 - 1][0]
        i = self.indice(n, l_inno5, "document", f"Ticket de carte bancaire, {nom_l}", matin,
                        {"montant": f"{r.randint(12, 80)},{r.randint(0, 99):02d} €", "heure": hm(crime - 5 * m),
                         "debut": (crime - 10 * m).isoformat(), "fin": (crime + 5 * m).isoformat(),
                         "code_saisi": True}, [(inno5, 80)])
        self.presence(inno5, l_inno5, crime - 10 * m, crime + 5 * m, i)
        self.piece_mobile(n, mobile[inno5], l_inno5, inno5, matin)
        self.declaration(n, inno5, lendemain, l_inno5, crime - 60 * m, crime + 30 * m, None,
                         f"J'ai dîné {a_lieu(nom_l)}, seul·e. J'ai payé par carte, ça doit se retrouver.")

        # ---- La fausse piste : pas d'alibi, des empreintes sur place, une lettre de menace.
        nom_faux = LIEUX[l_faux - 1][0]
        self.declaration(n, faux, lendemain, l_faux, crime - 60 * m, crime + 60 * m, None,
                         f"J'étais seul·e {a_lieu(nom_faux)}, personne ne peut le confirmer. Oui, je suis passé·e "
                         f"{a_lieu(nom_lieu)} dans l'après-midi. Et alors ?")
        self.piece_mobile(n, mobile[faux], l_faux, faux, matin)
        self.indice(n, l_faux, "document", "Brouillon d'une lettre de menace", matin,
                    {"encre": "violette", "phrase": "Tu vas payer.", "date": (crime - timedelta(days=9)).date().isoformat()},
                    [(faux, 70)])

        # ---- Les autres témoins.
        self.declaration(n, proche, lendemain, l_proche, crime - 40 * m, crime - 30 * m, None,
                         f"Je l'ai eu·e au téléphone vers {hm(crime - 35 * m)}. Elle attendait quelqu'un : "
                         f"{MOBILES[mobile[coupable]][1]}. Elle avait peur.")
        self.declaration(n, passant, lendemain, l_crime, crime - 25 * m, crime - 15 * m, None,
                         f"Je suis passé·e {a_lieu(nom_lieu)} vers {hm(crime - 20 * m)}. J'ai croisé une "
                         "silhouette pressée, capuche relevée, qui entrait au moment où je sortais.")
        # un lieu qui ne donne rien : une fouille perdue pour qui n'a pas réfléchi
        self.emit(f"-- (le lieu {l_rien} n'a aucun scellé : une fouille inutile)")
        self.emit("COMMIT;")

    def ecrire(self, nb, chemin):
        self.emit("-- Fichier écrit par modele/generer.py : ne pas modifier à la main.")
        self.emit("SET client_encoding = 'UTF8';")
        self.emit("SET client_min_messages = warning;")
        self.emit("SET TIME ZONE 'Europe/Paris';")
        self.emit("TRUNCATE actions, parties, joueurs, liens, declarations, presences, designations, "
                  "indices, implications, affaires, lieux, personnes RESTART IDENTITY CASCADE;")
        self.lieux()
        for n in range(1, nb + 1):
            self.affaire(n)
        self.emit("\n-- Les compteurs repartent après les id écrits.")
        self.emit("DO $$ BEGIN")
        for table in ("lieux", "personnes", "affaires", "indices"):
            self.emit(f"  PERFORM setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}));")
        self.emit("END $$;")
        Path(chemin).write_text("\n".join(self.sql) + "\n", encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--affaires", type=int, default=6)
    p.add_argument("--graine", type=int, default=42)
    p.add_argument("--sortie", default=str(Path(__file__).with_name("donnees.sql")))
    a = p.parse_args()
    Generateur(a.graine).ecrire(a.affaires, a.sortie)
    print(f"{a.affaires} affaires écrites dans {a.sortie}")
