# Le mur de l'enquêteur

Un jeu d'enquête policière sur une base de données : chaque affaire a un coupable caché, un mobile et un alibi qui
ment. Le joueur a un délai en heures d'enquête : chaque interrogatoire, fouille ou analyse au labo lui en coûte. Il
ne peut pas tout faire, il choisit, puis il accuse.

- **Groupe** : Sofia Selloum, Rodolphe Fanneau de la Horie, Credo Badou
- **Cours** : Conception et architecture des données, Bachelor 3, TP des séances 3 et 4
- **Base choisie** : PostgreSQL seul (`jsonb` pour les indices, `WITH RECURSIVE` pour le mur, `EXCLUDE` pour
  « jamais deux endroits à la fois »). Pourquoi : [docs/adr/0001-postgresql-seul.md](docs/adr/0001-postgresql-seul.md)

## Le rendu

| Fichier | Contenu |
|---|---|
| [CONCEPTION.md](CONCEPTION.md) | les 12 règles de gestion, les questions tranchées, le MCD, le MLD, ce que le schéma ne garantit pas |
| [docs/adr/0001-postgresql-seul.md](docs/adr/0001-postgresql-seul.md) | le choix de la base, comparée à Neo4j et MongoDB |
| [docs/mcd.png](docs/mcd.png) | le MCD en image (le même que le Mermaid de CONCEPTION.md) |
| [modele/schema.sql](modele/schema.sql) | bonus : la base (tables, contraintes, triggers, vue, fonction `accuser`) |
| [modele/generer.py](modele/generer.py) | bonus : le générateur d'affaires jouables |
| [modele/verifier.sql](modele/verifier.sql) | bonus : 29 tests, au moins un par règle, qui montrent que la base refuse ce qu'elle doit refuser |
| [modele/requetes.sql](modele/requetes.sql) | bonus : 9 requêtes d'enquêteur (alibis qui mentent, mur sur 3 niveaux, empreintes en `jsonb`, carnet d'une partie…) |
| [app/app.py](app/app.py), `app/templates/`, `app/static/` | bonus : le jeu, une application web (Flask), avec son habillage polar (`style.css`) et ses animations (`jeu.js`) |

## Lancer le bonus

Il faut PostgreSQL (testé en 16 et 18) et Python 3.10 ou plus.

**1. La base.** Sur le serveur du TD (port 5433, utilisateur `postgres`) :

```bash
createdb -h localhost -p 5433 -U postgres lemur
psql -h localhost -p 5433 -U postgres -d lemur -f modele/schema.sql
python modele/generer.py                       # écrit modele/donnees.sql (6 affaires)
psql -h localhost -p 5433 -U postgres -d lemur -f modele/donnees.sql
psql -h localhost -p 5433 -U postgres -d lemur -f modele/verifier.sql     # 29 lignes « OK »
psql -h localhost -p 5433 -U postgres -d lemur -f modele/requetes.sql
```

Sous Windows, `psql` et `createdb` sont dans `C:\Program Files\PostgreSQL\18\bin\`. Avec pgAdmin : créer la base
`lemur`, puis ouvrir chaque fichier dans le Query Tool et faire F5 (`requetes.sql` utilise `\echo`, réservé à psql :
dans pgAdmin, lancer les requêtes une par une).

Plus d'affaires : `python modele/generer.py --affaires 50 --graine 7`.

**2. Le jeu.**

```bash
pip install -r app/requirements.txt
python app/app.py                               # puis ouvrir http://localhost:5000
```

L'application se connecte à `postgresql://postgres@localhost:5433/lemur`. Pour une autre base :
`DATABASE_URL=postgresql://utilisateur:motdepasse@hote:port/base` (sous Windows : `set DATABASE_URL=...`).

## Comment on joue

Le temps est la monnaie du jeu : il n'y a pas de vrai chronomètre, seules les actions font avancer l'horloge.
Après chaque action, un compte rendu en bas à droite dit ce qu'elle a rapporté et mène droit à l'info.

1. Choisir un nom de code, ouvrir une affaire. On a 26 à 30 heures d'enquête.
2. **Interroger** (2 h) : chacun dit où il était, parfois avec un garant. Certains mentent.
3. **Voisinage** (1 h) : les liens d'une personne apparaissent sur le mur (dette, rivalité, ex, famille, amitié…).
4. **Fouiller** un lieu (3 h) : il livre ses scellés, ou rien. On ne connaît au départ que le lieu des faits ; les
   autres lieux apparaissent dans les déclarations.
5. **Labo** (1 à 8 h selon le scellé, et plus un scellé en dit, plus il coûte) : un relevé d'antenne (8 h) ou une
   caméra (4 h) dit où quelqu'un était *vraiment*, l'ADN (6 h) désigne sans dater, l'empreinte (3 h) peut être ancienne. La
   chronologie met côte à côte ce que chacun déclare et ce que les scellés prouvent.
6. **Accuser** : on désigne le coupable dans le tapissage des suspects, c'est définitif. Score : 50 points pour le bon coupable, plus 10 par heure restante.

Chaque affaire a sept suspects, tous avec un mobile. Elle a une fausse piste solide (un suspect sans alibi, ses empreintes sur place), un
menteur qui n'a rien fait, et des scellés qui coûtent
cher pour rien. Elle se résout en 13 heures environ si l'on choisit bien.
