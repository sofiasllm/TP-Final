# 1. Le mur de l'enquêteur est stocké dans PostgreSQL seul

- **Date** : 2026-11-10
- **Statut** : Acceptée

## Contexte

Ce que le sujet demande à la base, d'après la conception ([CONCEPTION.md](../../CONCEPTION.md)) :

- **La forme des données.** Onze entités très liées (affaires, personnes, lieux, indices et leurs types, présences,
  déclarations, joueurs, parties, actions et leurs sortes). Les indices ont six types aux caractéristiques différentes : une vidéo a une caméra, un début
  et une fin ; une empreinte a un doigt et une qualité ; un document a un montant ou une phrase. D'autres types
  viendront.
- **La façon de les lire.** Le dossier d'une affaire, c'est une dizaine de personnes, une dizaine d'indices et
  autant de liens, assemblés sur une page. Le mur se lit en suivant les liens à partir de la victime, sur 2 ou 3
  niveaux. Le cœur du jeu est une question qui croise trois tables : « quelle déclaration est contredite par une
  présence attestée ? » (requête Q2). Le tableau d'honneur trie les joueurs par points.
- **Les écritures.** Peu nombreuses : une ligne par action (interroger, voisinage, fouiller, analyser), une par
  accusation, une quinzaine par partie. Mais chaque action **dépend des précédentes** : elle n'est acceptée que si la
  somme des durées déjà dépensées, plus la sienne, tient dans le délai de l'affaire. Les affaires sont écrites d'un
  bloc par le générateur.
- **Les garanties.** Une personne n'est jamais à deux endroits à la fois (RG7). Le coupable et l'accusé sont des
  suspects de l'affaire (RG3, RG12). Une action vise une personne ou un indice *de l'affaire*, et le délai n'est
  jamais dépassé, même si deux actions arrivent en même temps (RG11). L'accusation est définitive et son score se
  calcule une seule fois (RG12). Le coupable reste caché au joueur (RG3).
- **Les mesures.** Avec 500 affaires générées (5 000 personnes), le parcours du mur sur 3 niveaux s'exécute en
  moins d'une milliseconde (`EXPLAIN ANALYZE`). Les 29 tests de [modele/verifier.sql](../../modele/verifier.sql) passent.
- **L'équipe.** Elle connaît PostgreSQL (séances 1 et 2), et le serveur du TD tourne déjà sur nos PC (port 5433).

## Options envisagées

1. **PostgreSQL seul**, avec les caractéristiques des indices en `jsonb`, le mur en `WITH RECURSIVE`, et RG7 en
   contrainte d'exclusion (`EXCLUDE USING gist`).
   - Pour : toutes les garanties sont dans la base. Les FK composites tiennent RG3, RG8, RG11 et RG12 sans une ligne
     de code ; `EXCLUDE` tient RG7 ; le délai tient dans un trigger qui verrouille la partie (`FOR UPDATE`) avant
     d'additionner les durées ; l'accusation tient dans une transaction. Le croisement déclarations ×
     présences est une jointure sur des intervalles (`&&`), naturelle en SQL. Le `jsonb` avec un index GIN donne la
     forme libre des indices, sans base de plus. Une seule base à installer, que l'équipe connaît.
   - Contre : la requête récursive du mur est longue et moins lisible qu'un motif Cypher ; elle ralentirait sur des
     parcours profonds. Le contenu du `jsonb` n'est vérifié que par un `CHECK` minimal.
2. **Neo4j** (graphe), tout le modèle en nœuds et relations.
   - Pour : le mur *est* un graphe. « Qui est à 3 liens de la victime ? » s'écrit
     `MATCH (v:Personne)-[*1..3]-(p)` ; un plus court chemin entre deux suspects est natif. Les relations portent
     leurs données (type de lien, fiabilité).
   - Contre : nos parcours font 2 ou 3 niveaux sur une dizaine de personnes, ce que PostgreSQL fait déjà en moins
     d'une milliseconde : Neo4j n'a rien à gagner ici. Il n'a pas d'équivalent à `EXCLUDE` sur des intervalles, ni de
     FK : RG3, RG7, RG8, RG11 et RG12 passeraient toutes dans le code, y compris le « pas plus que le délai », qui
     demande de verrouiller la partie pendant qu'on additionne. Le tableau d'honneur (un agrégat sur toutes
     les parties) est ce qu'un graphe fait mal. Une base que l'équipe ne connaît pas.
3. **MongoDB** (document), un document par affaire avec ses personnes, indices et déclarations imbriqués.
   - Pour : le dossier d'une affaire se lit en une lecture ; les indices ont chacun leur forme sans effort.
   - Contre : une personne peut être impliquée dans plusieurs affaires et apparaître sur plusieurs murs : imbriquée,
     elle est recopiée et ses copies divergent ; référencée, on refait les jointures à la main (`$lookup`). Les
     présences et les déclarations se croisent sur des intervalles de temps entre documents : rien de natif. RG7 ne
     peut pas s'exprimer (pas de contrainte entre documents). Pour les parties, on pourrait imbriquer les actions dans
     le document de la partie et vérifier le délai par une mise à jour conditionnelle ; mais chaque action doit viser
     une personne ou un indice de l'affaire, qui vivent dans un autre document : rien ne le vérifie.
4. **PostgreSQL et Neo4j ensemble** (PostgreSQL source de vérité, une copie du mur dans Neo4j alimentée chaque nuit).
   - Pour : chaque base fait ce qu'elle fait de mieux.
   - Contre : une seconde base à installer et à alimenter, pour un gain que la mesure ne montre pas. La règle
     « commencer simple » de la séance 2 s'applique.

Redis a été écarté d'emblée pour le tableau d'honneur : il est lu à chaque page d'accueil, mais calculé sur
quelques centaines de parties, en quelques millisecondes. Rien ne justifie une base de plus.

## Décision

Nous retenons **PostgreSQL seul**. Le sujet demande surtout des garanties (jamais deux endroits à la fois, un
suspect de la bonne affaire, une accusation définitive), et PostgreSQL les tient dans le schéma. Il couvre aussi
nos deux besoins « non relationnels » : la forme variable des indices avec `jsonb`, et le mur avec `WITH RECURSIVE`,
à des tailles où il est mesuré rapide.

**Normalisation.** Le schéma est en troisième forme normale. Les seules copies sont voulues, et dites dans
CONCEPTION.md (section « Ce qu'on recopie exprès ») :
- `parties.score` et `parties.reussie`, calculés une seule fois par la fonction `accuser()`, dans la transaction
  de l'accusation, puis figés par un trigger : la copie ne peut plus devenir fausse ;
- `actions.duree`, recopiée du barème par un trigger : c'est ce que l'action a coûté, comme un prix payé ;
- `actions.affaire_id`, `affaires.coupable_role` et `parties.accuse_role`, recopiés pour permettre des FK
  composites ; les FK et les colonnes générées les empêchent d'être fausses.

Nous refusons en revanche de recopier le temps utilisé dans `parties` : il changerait à chaque action, et la vue
`temps_parties` le calcule en additionnant une quinzaine de lignes.

Nous refusons de recopier le nom des personnes dans les déclarations ou les liens : une jointure coûte moins d'une
milliseconde, et un changement de nom laisserait des copies fausses.

## Conséquences

- **Ce qui devient plus difficile.** Les requêtes du mur (`WITH RECURSIVE`, avec le lien lu dans les deux sens et
  un tableau anti-boucle) sont plus longues à écrire et à relire que leur équivalent Cypher. Les caractéristiques
  des indices ne sont validées qu'en partie par la base : un champ mal nommé dans le `jsonb` passe, c'est le code
  (le générateur, ou un futur formulaire) qui doit le refuser. Les contraintes différées et la contrainte
  d'exclusion demandent l'extension `btree_gist`, livrée avec PostgreSQL mais à activer.
- **Ce qui la ferait revoir.**
  - Si le mur relie les affaires entre elles (un réseau criminel sur des milliers d'affaires) et que les
    parcours dépassent 4 niveaux ou **200 ms au 95e centile** : on ajouterait une copie du mur dans Neo4j,
    alimentée chaque nuit depuis PostgreSQL, qui reste la source de vérité (option 4).
  - Si un mode « en direct » met des centaines de joueurs sur la même affaire, avec un classement mis à jour à
    chaque action : le classement passerait dans Redis (`ZINCRBY`), comme le bandeau des ventes d'Ombelle (B6).
  - Si les types d'indices se multiplient au point que le `CHECK` minimal ne suffit plus : un schéma JSON validé
    par un trigger, avant d'envisager MongoDB.
