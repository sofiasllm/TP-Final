-- Le mur de l'enquêteur · la base refuse-t-elle ce que les règles interdisent ?
--   psql -h localhost -p 5433 -U postgres -d lemur -f modele/verifier.sql
-- À lancer après schema.sql et donnees.sql. Rejouable : chaque essai est annulé, la base ne bouge pas.

SET client_encoding = 'UTF8';   -- les accents passent aussi depuis la console Windows

SET client_min_messages = warning;
DROP TABLE IF EXISTS pg_temp.resultats;
CREATE TEMP TABLE resultats (n int, resultat text, test text);

-- essai(n, test, requête, doit_passer) : joue la requête, l'annule, et note si la base a réagi comme prévu.
CREATE OR REPLACE FUNCTION pg_temp.essai(n int, test text, requete text, doit_passer boolean DEFAULT false)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE passe boolean;
BEGIN
    BEGIN
        EXECUTE requete;
        SET CONSTRAINTS ALL IMMEDIATE;          -- force les contraintes différées
        passe := true;
        RAISE EXCEPTION 'annuler';
    EXCEPTION WHEN OTHERS THEN
        IF SQLERRM <> 'annuler' THEN passe := false; END IF;
    END;
    INSERT INTO resultats VALUES (n, CASE WHEN passe = doit_passer THEN 'OK' ELSE 'ÉCHEC' END, test);
END $$;

-- Une partie de test, pour les essais sur les parties.
DO $p$ BEGIN
    INSERT INTO joueurs (pseudo) VALUES ('verif') ON CONFLICT DO NOTHING;
    INSERT INTO parties (joueur_id, affaire_id) SELECT id, 1 FROM joueurs WHERE pseudo = 'verif';
END $p$;

DO $tout$ BEGIN
    PERFORM pg_temp.essai(1, 'RG2  : un matricule mal formé est refusé',
    $q$INSERT INTO personnes (matricule, nom, prenom, naissance, profession) VALUES ('X-1', 'A', 'B', '1990-01-01', 'notaire')$q$);
    PERFORM pg_temp.essai(2, 'RG2  : une seconde victime dans la même affaire est refusée',
    $q$INSERT INTO implications SELECT 1, id, 'victime' FROM personnes WHERE id NOT IN (SELECT personne_id FROM implications WHERE affaire_id = 1) LIMIT 1$q$);
    PERFORM pg_temp.essai(3, 'RG2  : une personne n''a qu''un rôle dans une affaire',
    $q$INSERT INTO implications SELECT affaire_id, personne_id, 'temoin' FROM implications WHERE affaire_id = 1 AND role = 'suspect' LIMIT 1$q$);
    PERFORM pg_temp.essai(4, 'RG3  : un témoin ne peut pas être le coupable',
    $q$UPDATE affaires SET coupable_id = (SELECT personne_id FROM implications WHERE affaire_id = 1 AND role = 'temoin' LIMIT 1) WHERE id = 1$q$);
    PERFORM pg_temp.essai(5, 'RG4  : une affaire avec deux suspects seulement est refusée',
    $q$WITH p AS (INSERT INTO personnes (matricule, nom, prenom, naissance, profession)
                 VALUES ('P-90001','A','A','1990-01-01','notaire'), ('P-90002','B','B','1990-01-01','notaire'), ('P-90003','C','C','1990-01-01','notaire') RETURNING id),
           a AS (INSERT INTO affaires (code, titre, nature, resume, crime_le, lieu_crime_id, coupable_id)
                 SELECT 'AFF-2026-900', 't', 'vol', 'r', now(), 1, min(id) FROM p RETURNING id)
       INSERT INTO implications SELECT a.id, p.id, CASE WHEN p.id = (SELECT max(id) FROM p) THEN 'victime' ELSE 'suspect' END FROM a, p$q$);
    PERFORM pg_temp.essai(6, 'RG6  : une vidéo sans début ni fin est refusée',
    $q$INSERT INTO indices (scelle, affaire_id, lieu_id, type, libelle, trouve_le, caracteristiques) VALUES ('SC-99999', 1, 1, 'video', 'x', now(), '{"camera": "CAM-1"}')$q$);
    PERFORM pg_temp.essai(7, 'RG6  : une fiabilité de 120 % est refusée',
    $q$UPDATE designations SET fiabilite = 120 WHERE indice_id = (SELECT min(indice_id) FROM designations)$q$);
    PERFORM pg_temp.essai(8, 'RG7  : une même personne en deux lieux au même moment est refusée',
    $q$INSERT INTO presences (personne_id, lieu_id, creneau) SELECT personne_id, lieu_id % 20 + 1, creneau FROM presences LIMIT 1$q$);
    PERFORM pg_temp.essai(9, 'RG7  : une présence sur un autre créneau est acceptée',
    $q$INSERT INTO presences (personne_id, lieu_id, creneau) SELECT personne_id, lieu_id, tstzrange('2030-01-01', '2030-01-02') FROM presences LIMIT 1$q$, true);
    PERFORM pg_temp.essai(10, 'RG8  : une déclaration d''une personne hors de l''affaire est refusée',
    $q$INSERT INTO declarations (affaire_id, personne_id, faite_le, lieu_id, creneau, texte)
       SELECT 1, id, now(), 1, tstzrange(now(), now() + interval '1 hour'), 'x' FROM personnes WHERE id NOT IN (SELECT personne_id FROM implications WHERE affaire_id = 1) LIMIT 1$q$);
    PERFORM pg_temp.essai(11, 'RG8  : on ne se porte pas garant de soi-même',
    $q$UPDATE declarations SET garant_id = personne_id WHERE id = (SELECT min(id) FROM declarations)$q$);
    PERFORM pg_temp.essai(12, 'RG8  : une déclaration qui ment est acceptée (c''est le jeu)',
    $q$INSERT INTO declarations (affaire_id, personne_id, faite_le, lieu_id, creneau, texte)
       SELECT d.affaire_id, d.personne_id, now(), (d.lieu_id % 20) + 1, d.creneau, 'Je mens' FROM declarations d LIMIT 1$q$, true);
    PERFORM pg_temp.essai(13, 'RG9  : un lien d''une personne avec elle-même est refusé',
    $q$INSERT INTO liens VALUES (1, 1, 'ami', '2020-01-01')$q$);
    PERFORM pg_temp.essai(14, 'RG9  : le même lien rangé dans l''autre sens est refusé',
    $q$INSERT INTO liens SELECT personne_b, personne_a, type, depuis FROM liens LIMIT 1$q$);
    PERFORM pg_temp.essai(15, 'RG10 : deux joueurs ne portent pas le même pseudo',
    $q$INSERT INTO joueurs (pseudo) VALUES ('verif')$q$);
    PERFORM pg_temp.essai(16, 'RG10 : une seconde partie en cours sur la même affaire est refusée',
    $q$INSERT INTO parties (joueur_id, affaire_id) SELECT id, 1 FROM joueurs WHERE pseudo = 'verif'$q$);
    PERFORM pg_temp.essai(17, 'RG6  : un indice d''un type inconnu est refusé',
    $q$INSERT INTO indices (scelle, affaire_id, lieu_id, type, libelle, trouve_le) VALUES ('SC-99998', 1, 1, 'horoscope', 'x', now())$q$);
    PERFORM pg_temp.essai(18, 'RG11 : interroger une personne de l''affaire est accepté',
    $q$INSERT INTO actions (partie_id, affaire_id, type, personne_id, duree)
       SELECT (SELECT max(id) FROM parties), 1, 'interroger', personne_id, 1 FROM implications WHERE affaire_id = 1 LIMIT 1$q$, true);
    PERFORM pg_temp.essai(19, 'RG11 : la durée vient du barème, pas de celui qui écrit (2 h pour interroger)',
    $q$DO $d$ DECLARE d int; BEGIN
         INSERT INTO actions (partie_id, affaire_id, type, personne_id, duree)
         SELECT (SELECT max(id) FROM parties), 1, 'interroger', personne_id, 1 FROM implications WHERE affaire_id = 1 LIMIT 1
         RETURNING duree INTO d;
         IF d <> 120 THEN RAISE EXCEPTION 'durée %', d; END IF; END $d$$q$, true);
    PERFORM pg_temp.essai(20, 'RG11 : interroger quelqu''un qui n''est pas dans l''affaire est refusé',
    $q$INSERT INTO actions (partie_id, affaire_id, type, personne_id, duree)
       SELECT (SELECT max(id) FROM parties), 1, 'interroger', id, 1 FROM personnes WHERE id NOT IN (SELECT personne_id FROM implications WHERE affaire_id = 1) LIMIT 1$q$);
    PERFORM pg_temp.essai(21, 'RG11 : analyser un scellé d''une autre affaire est refusé',
    $q$INSERT INTO actions (partie_id, affaire_id, type, indice_id, duree)
       SELECT (SELECT max(id) FROM parties), 1, 'analyser', min(id), 1 FROM indices WHERE affaire_id = 2$q$);
    PERFORM pg_temp.essai(22, 'RG11 : une fouille qui vise une personne est refusée',
    $q$INSERT INTO actions (partie_id, affaire_id, type, personne_id, lieu_id, duree)
       SELECT (SELECT max(id) FROM parties), 1, 'fouiller', personne_id, 1, 1 FROM implications WHERE affaire_id = 1 LIMIT 1$q$);
    PERFORM pg_temp.essai(23, 'RG11 : fouiller deux fois le même lieu est refusé',
    $q$INSERT INTO actions (partie_id, affaire_id, type, lieu_id, duree) VALUES ((SELECT max(id) FROM parties), 1, 'fouiller', 1, 1);
       INSERT INTO actions (partie_id, affaire_id, type, lieu_id, duree) VALUES ((SELECT max(id) FROM parties), 1, 'fouiller', 1, 1)$q$);
    PERFORM pg_temp.essai(24, 'RG11 : dépasser le délai de l''affaire est refusé',
    $q$INSERT INTO actions (partie_id, affaire_id, type, indice_id, duree)
       SELECT (SELECT max(id) FROM parties), 1, 'analyser', id, 1 FROM indices WHERE affaire_id = 1$q$);
    PERFORM pg_temp.essai(25, 'RG11 : une action faite ne se modifie pas',
    $q$INSERT INTO actions (partie_id, affaire_id, type, lieu_id, duree) VALUES ((SELECT max(id) FROM parties), 1, 'fouiller', 1, 1);
       UPDATE actions SET duree = 1 WHERE partie_id = (SELECT max(id) FROM parties)$q$);
    PERFORM pg_temp.essai(26, 'RG12 : accuser un témoin est refusé',
    $q$SELECT accuser((SELECT max(id) FROM parties), (SELECT personne_id FROM implications WHERE affaire_id = 1 AND role = 'temoin' LIMIT 1))$q$);
    PERFORM pg_temp.essai(27, 'RG12 : accuser un suspect est accepté, le score est calculé',
    $q$SELECT accuser((SELECT max(id) FROM parties), (SELECT coupable_id FROM affaires WHERE id = 1))$q$, true);
    PERFORM pg_temp.essai(28, 'RG12 : après l''accusation, la partie ne se modifie plus',
    $q$DO $d$ DECLARE p int := (SELECT max(id) FROM parties); BEGIN
         PERFORM accuser(p, (SELECT coupable_id FROM affaires WHERE id = 1));
         UPDATE parties SET score = 1000 WHERE id = p; END $d$$q$);
    PERFORM pg_temp.essai(29, 'RG12 : après l''accusation, plus aucune action',
    $q$DO $d$ DECLARE p int := (SELECT max(id) FROM parties); BEGIN
         PERFORM accuser(p, (SELECT coupable_id FROM affaires WHERE id = 1));
         INSERT INTO actions (partie_id, affaire_id, type, lieu_id, duree) VALUES (p, 1, 'fouiller', 1, 1); END $d$$q$);
END $tout$;

-- On range la partie de test.
DO $r$ BEGIN
    DELETE FROM parties WHERE joueur_id = (SELECT id FROM joueurs WHERE pseudo = 'verif');
    DELETE FROM joueurs WHERE pseudo = 'verif';
END $r$;

SELECT n AS "n°", resultat AS "résultat", test FROM resultats ORDER BY n;
