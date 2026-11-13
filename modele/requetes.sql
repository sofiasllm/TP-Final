-- Le mur de l'enquêteur · les questions de l'enquêteur, en SQL
--   psql -h localhost -p 5433 -U postgres -d lemur -f modele/requetes.sql
-- Toutes portent sur l'affaire AFF-2026-001 ; changez le code pour une autre.

SET client_encoding = 'UTF8';   -- les accents passent aussi depuis la console Windows
SET TIME ZONE 'Europe/Paris';

\echo '===== Q1 · Les suspects, et l''alibi qu''ils déclarent ====='
SELECT p.matricule, p.prenom || ' ' || p.nom AS suspect, p.profession,
       l.nom AS lieu_declare,
       to_char(lower(d.creneau), 'HH24:MI') || ' à ' || to_char(upper(d.creneau), 'HH24:MI') AS creneau,
       g.prenom || ' ' || g.nom AS garant
FROM affaires a
JOIN implications i ON i.affaire_id = a.id AND i.role = 'suspect'
JOIN personnes p    ON p.id = i.personne_id
LEFT JOIN declarations d ON d.affaire_id = a.id AND d.personne_id = p.id
LEFT JOIN lieux l   ON l.id = d.lieu_id
LEFT JOIN personnes g ON g.id = d.garant_id
WHERE a.code = 'AFF-2026-001'
ORDER BY p.matricule;

\echo '===== Q2 · Les alibis qui mentent : une déclaration contredite par une présence attestée ====='
-- La base n'empêche pas une déclaration fausse (RG8) : c'est tout le jeu. Elle sait la trouver.
SELECT p.prenom || ' ' || p.nom AS personne,
       ld.nom AS dit_etre_a, lp.nom AS etait_en_fait_a,
       to_char(lower(pr.creneau), 'HH24:MI') || ' à ' || to_char(upper(pr.creneau), 'HH24:MI') AS quand,
       ix.scelle AS preuve
FROM affaires a
JOIN declarations d ON d.affaire_id = a.id
JOIN presences pr   ON pr.personne_id = d.personne_id
                   AND pr.creneau && d.creneau            -- les créneaux se chevauchent
                   AND pr.lieu_id <> d.lieu_id            -- mais pas au même endroit
JOIN personnes p ON p.id = d.personne_id
JOIN lieux ld ON ld.id = d.lieu_id
JOIN lieux lp ON lp.id = pr.lieu_id
LEFT JOIN indices ix ON ix.id = pr.indice_id
WHERE a.code = 'AFF-2026-001';

\echo '===== Q3 · Qui était sur le lieu du crime à l''heure du crime (une heure autour) ? ====='
SELECT p.prenom || ' ' || p.nom AS personne, i.role,
       to_char(lower(pr.creneau), 'HH24:MI') || ' à ' || to_char(upper(pr.creneau), 'HH24:MI') AS present
FROM affaires a
JOIN presences pr ON pr.lieu_id = a.lieu_crime_id
                 AND pr.creneau && tstzrange(a.crime_le - interval '30 minutes', a.crime_le + interval '30 minutes')
JOIN personnes p ON p.id = pr.personne_id
LEFT JOIN implications i ON i.affaire_id = a.id AND i.personne_id = p.id
WHERE a.code = 'AFF-2026-001';

\echo '===== Q4 · Le mur : tout le réseau de la victime, jusqu''à 3 liens (WITH RECURSIVE) ====='
WITH RECURSIVE
    l AS (SELECT personne_a AS de, personne_b AS vers, type FROM liens
          UNION ALL
          SELECT personne_b, personne_a, type FROM liens),       -- le lien se lit dans les deux sens
    reseau (personne_id, distance, chemin, types) AS (
        SELECT i.personne_id, 0, ARRAY[i.personne_id], ARRAY[]::text[]
        FROM affaires a JOIN implications i ON i.affaire_id = a.id AND i.role = 'victime'
        WHERE a.code = 'AFF-2026-001'
        UNION ALL
        SELECT l.vers, r.distance + 1, r.chemin || l.vers, r.types || l.type
        FROM reseau r JOIN l ON l.de = r.personne_id
        WHERE r.distance < 3 AND NOT l.vers = ANY (r.chemin)      -- pas de boucle
    )
SELECT DISTINCT ON (p.id) p.prenom || ' ' || p.nom AS personne, r.distance,
       array_to_string(r.types, ' → ') AS par_les_liens
FROM reseau r JOIN personnes p ON p.id = r.personne_id
WHERE r.distance > 0
ORDER BY p.id, r.distance;

\echo '===== Q5 · Ce que les indices disent de chaque suspect ====='
SELECT p.prenom || ' ' || p.nom AS suspect, count(dz.indice_id) AS nb_indices,
       round(avg(dz.fiabilite)) AS fiabilite_moyenne, max(dz.fiabilite) AS plus_forte,
       string_agg(ix.libelle, ' ; ' ORDER BY dz.fiabilite DESC) AS indices
FROM affaires a
JOIN implications i ON i.affaire_id = a.id AND i.role = 'suspect'
JOIN personnes p ON p.id = i.personne_id
LEFT JOIN designations dz ON dz.personne_id = p.id
LEFT JOIN indices ix ON ix.id = dz.indice_id AND ix.affaire_id = a.id
WHERE a.code = 'AFF-2026-001'
GROUP BY p.id ORDER BY fiabilite_moyenne DESC NULLS LAST;

\echo '===== Q6 · Le garant ment-il ? Les garants qui ont un lien avec celui qu''ils couvrent ====='
SELECT p.prenom || ' ' || p.nom AS declarant, g.prenom || ' ' || g.nom AS garant, li.type AS lien
FROM declarations d
JOIN affaires a ON a.id = d.affaire_id AND a.code = 'AFF-2026-001'
JOIN personnes p ON p.id = d.personne_id
JOIN personnes g ON g.id = d.garant_id
JOIN liens li ON li.personne_a = least(d.personne_id, d.garant_id)
             AND li.personne_b = greatest(d.personne_id, d.garant_id);

\echo '===== Q7 · Les indices de forme variable : toutes les empreintes nettes (jsonb) ====='
SELECT a.code, ix.scelle, ix.libelle, ix.caracteristiques ->> 'doigt' AS doigt,
       (ix.caracteristiques ->> 'points_communs')::int AS points
FROM indices ix JOIN affaires a ON a.id = ix.affaire_id
WHERE ix.caracteristiques @> '{"qualite": "nette"}'            -- servi par l'index GIN
ORDER BY points DESC;

\echo '===== Q8 · Le classement des enquêteurs ====='
SELECT j.pseudo, count(*) FILTER (WHERE pa.reussie) AS resolues, count(pa.accuse_id) AS jouees,
       coalesce(sum(pa.score), 0) AS points
FROM joueurs j LEFT JOIN parties pa ON pa.joueur_id = j.id
GROUP BY j.id ORDER BY points DESC, resolues DESC
LIMIT 10;

\echo '===== Q9 · Le carnet d''une partie : chaque action, ce qu''elle a coûté, l''heure à l''horloge du jeu ====='
SELECT j.pseudo, a.code, ac.type,
       coalesce(pe.prenom || ' ' || pe.nom, l.nom, i.scelle) AS cible,
       ac.duree / 60.0 AS heures,
       to_char(a.enquete_le + make_interval(mins => sum(ac.duree) OVER (PARTITION BY ac.partie_id ORDER BY ac.id)::int),
               'DD/MM HH24"h"MI') AS horloge_apres
FROM actions ac
JOIN parties p ON p.id = ac.partie_id JOIN joueurs j ON j.id = p.joueur_id JOIN affaires a ON a.id = p.affaire_id
LEFT JOIN personnes pe ON pe.id = ac.personne_id LEFT JOIN lieux l ON l.id = ac.lieu_id LEFT JOIN indices i ON i.id = ac.indice_id
ORDER BY ac.partie_id, ac.id
LIMIT 30;
