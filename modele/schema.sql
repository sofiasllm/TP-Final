-- Le mur de l'enquêteur · le MPD PostgreSQL (issu du MLD de CONCEPTION.md)
--
-- Rejouable : on efface d'abord ce qui existe.
--   psql -h localhost -p 5433 -U postgres -d lemur -f modele/schema.sql
--   (pgAdmin : Query Tool sur la base lemur, ouvrir ce fichier, F5)
--
-- Les numéros RGn renvoient aux règles de gestion de CONCEPTION.md.

SET client_encoding = 'UTF8';   -- les accents passent aussi depuis la console Windows
SET client_min_messages = warning;

DROP TABLE IF EXISTS actions, consultations, parties, joueurs, types_action, liens, declarations, presences,
                     designations, indices, types_indice, implications, affaires, lieux, personnes CASCADE;
DROP VIEW IF EXISTS affaires_publiques, temps_parties;
DROP FUNCTION IF EXISTS accuser(integer, integer);

-- RG7 : « pas deux présences qui se chevauchent » se dit avec une contrainte d'exclusion,
-- qui a besoin de cette extension (livrée avec PostgreSQL).
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- RG2 : une personne a un matricule unique (identifiant métier).
CREATE TABLE personnes (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    matricule   text NOT NULL UNIQUE CHECK (matricule ~ '^P-[0-9]{5}$'),
    nom         text NOT NULL,
    prenom      text NOT NULL,
    naissance   date NOT NULL,
    profession  text NOT NULL
);

-- RG5 : un lieu a un nom unique dans sa ville.
CREATE TABLE lieux (
    id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom    text NOT NULL,
    ville  text NOT NULL,
    type   text NOT NULL,
    UNIQUE (nom, ville)
);

-- RG1 : une affaire a un code unique, une date, un seul lieu du crime, et un délai d'enquête.
-- RG3 : une affaire a exactement un coupable, qui est un de ses suspects.
CREATE TABLE affaires (
    id             integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code           text NOT NULL UNIQUE CHECK (code ~ '^AFF-[0-9]{4}-[0-9]{3}$'),
    titre          text NOT NULL,
    nature         text NOT NULL CHECK (nature IN ('meurtre', 'vol', 'empoisonnement', 'incendie', 'enlèvement')),
    resume         text NOT NULL,
    crime_le       timestamptz NOT NULL,
    lieu_crime_id  integer NOT NULL REFERENCES lieux (id),           -- RG1 : (1,1) côté affaire
    enquete_le     timestamptz NOT NULL,                              -- RG1 : l'heure où l'enquête commence
    delai_minutes  integer NOT NULL CHECK (delai_minutes BETWEEN 60 AND 7 * 24 * 60),
    coupable_id    integer NOT NULL,                                  -- RG3 : (1,1) côté affaire
    coupable_role  text GENERATED ALWAYS AS ('suspect') STORED,       -- recopié exprès, pour la FK ci-dessous
    CHECK (enquete_le > crime_le)
);

-- RG2 : dans une affaire, une personne a un seul rôle ; une affaire a une seule victime.
CREATE TABLE implications (
    affaire_id  integer NOT NULL REFERENCES affaires (id) ON DELETE CASCADE,
    personne_id integer NOT NULL REFERENCES personnes (id),
    role        text NOT NULL CHECK (role IN ('victime', 'suspect', 'temoin')),
    PRIMARY KEY (affaire_id, personne_id),
    UNIQUE (affaire_id, personne_id, role)
);
CREATE UNIQUE INDEX une_seule_victime ON implications (affaire_id) WHERE role = 'victime';
CREATE INDEX ON implications (personne_id);

-- RG3 : le coupable est un suspect de la même affaire. La FK composite le garantit ;
-- elle est différée, car l'affaire et ses implications se créent dans la même transaction.
ALTER TABLE affaires
    ADD CONSTRAINT coupable_est_un_suspect
    FOREIGN KEY (id, coupable_id, coupable_role)
    REFERENCES implications (affaire_id, personne_id, role)
    DEFERRABLE INITIALLY DEFERRED;

-- RG6 : le type d'un indice fixe la durée de son analyse au labo.
CREATE TABLE types_indice (
    code             text PRIMARY KEY,
    libelle          text NOT NULL UNIQUE,
    duree_analyse    integer NOT NULL CHECK (duree_analyse > 0)        -- en minutes
);
INSERT INTO types_indice VALUES
    -- plus un indice en dit, plus il coûte : le bornage situe à la minute près, l'ADN désigne sans dater,
    -- la vidéo montre une fenêtre, l'empreinte peut être ancienne, l'objet ne dit presque rien.
    ('empreinte', 'Empreinte digitale', 180), ('adn', 'Trace ADN', 360), ('video', 'Vidéo de surveillance', 240),
    ('bornage', 'Bornage téléphonique', 480), ('document', 'Document', 120), ('objet', 'Objet', 60);

-- RG6 : un indice a un numéro de scellé unique, est trouvé dans un seul lieu pour une seule affaire ;
-- ses caractéristiques dépendent de son type (jsonb).
CREATE TABLE indices (
    id                integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scelle            text NOT NULL UNIQUE CHECK (scelle ~ '^SC-[0-9]{5}$'),
    affaire_id        integer NOT NULL REFERENCES affaires (id) ON DELETE CASCADE,
    lieu_id           integer NOT NULL REFERENCES lieux (id),
    type              text NOT NULL REFERENCES types_indice (code),
    libelle           text NOT NULL,
    trouve_le         timestamptz NOT NULL,
    caracteristiques  jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(caracteristiques) = 'object'),
    UNIQUE (id, affaire_id),                                           -- cible de la FK de actions
    -- RG6 : le minimum vérifiable par la base ; le reste de la forme est vérifié par le code.
    CHECK (type NOT IN ('video', 'bornage') OR caracteristiques ?& ARRAY['debut', 'fin']),
    CHECK (type <> 'empreinte' OR caracteristiques ? 'doigt')
);
CREATE INDEX ON indices (affaire_id, lieu_id);
CREATE INDEX ON indices USING gin (caracteristiques);

-- RG6 : un indice désigne zéro ou plusieurs personnes, avec une fiabilité.
CREATE TABLE designations (
    indice_id    integer NOT NULL REFERENCES indices (id) ON DELETE CASCADE,
    personne_id  integer NOT NULL REFERENCES personnes (id),
    fiabilite    smallint NOT NULL CHECK (fiabilite BETWEEN 0 AND 100),
    PRIMARY KEY (indice_id, personne_id)
);
CREATE INDEX ON designations (personne_id);

-- RG7 : une présence attestée situe une personne dans un lieu sur un créneau ;
-- une personne n'a jamais deux présences attestées qui se chevauchent.
CREATE TABLE presences (
    id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    personne_id  integer NOT NULL REFERENCES personnes (id),
    lieu_id      integer NOT NULL REFERENCES lieux (id),
    creneau      tstzrange NOT NULL CHECK (NOT isempty(creneau) AND NOT lower_inf(creneau) AND NOT upper_inf(creneau)),
    indice_id    integer REFERENCES indices (id) ON DELETE CASCADE,  -- RG7 : attestée par 0 ou 1 indice
    EXCLUDE USING gist (personne_id WITH =, creneau WITH &&)
);
CREATE INDEX ON presences (indice_id);

-- RG8 : une déclaration est faite par une personne impliquée dans l'affaire ; elle dit où elle prétend
-- avoir été, et avec qui. Elle peut mentir : rien n'interdit qu'elle contredise une présence.
CREATE TABLE declarations (
    id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    affaire_id   integer NOT NULL,
    personne_id  integer NOT NULL,
    faite_le     timestamptz NOT NULL,
    lieu_id      integer NOT NULL REFERENCES lieux (id),
    creneau      tstzrange NOT NULL CHECK (NOT isempty(creneau)),
    garant_id    integer REFERENCES personnes (id),                   -- RG8 : 0 ou 1 garant
    texte        text NOT NULL,
    FOREIGN KEY (affaire_id, personne_id) REFERENCES implications (affaire_id, personne_id) ON DELETE CASCADE,
    CHECK (garant_id IS DISTINCT FROM personne_id)
);
CREATE INDEX ON declarations (affaire_id, personne_id);

-- RG9 : un lien relie deux personnes distinctes ; au plus un lien d'un type donné entre elles.
-- Le lien n'a pas de sens : on le range une seule fois, la plus petite id d'abord.
CREATE TABLE liens (
    personne_a  integer NOT NULL REFERENCES personnes (id),
    personne_b  integer NOT NULL REFERENCES personnes (id),
    type        text NOT NULL CHECK (type IN ('famille', 'couple', 'ami', 'collegue', 'dette', 'rivalite', 'ex')),
    depuis      date NOT NULL,
    PRIMARY KEY (personne_a, personne_b, type),
    CHECK (personne_a < personne_b)
);
CREATE INDEX ON liens (personne_b);

-- RG10 : un joueur a un pseudo unique.
CREATE TABLE joueurs (
    id         integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pseudo     text NOT NULL UNIQUE CHECK (length(pseudo) BETWEEN 2 AND 20),
    inscrit_le timestamptz NOT NULL DEFAULT now()
);

-- RG10 : une partie porte sur une seule affaire ; au plus une partie en cours par joueur et par affaire.
-- RG12 : une partie se termine par une seule accusation, contre un suspect de l'affaire.
CREATE TABLE parties (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    joueur_id     integer NOT NULL REFERENCES joueurs (id),
    affaire_id    integer NOT NULL REFERENCES affaires (id) ON DELETE CASCADE,
    commencee_le  timestamptz NOT NULL DEFAULT now(),
    accuse_id     integer,
    accuse_role   text GENERATED ALWAYS AS ('suspect') STORED,
    accusee_le    timestamptz,
    reussie       boolean,
    score         integer CHECK (score >= 0),                        -- recopié exprès : calculé une fois, figé
    UNIQUE (id, affaire_id),
    FOREIGN KEY (affaire_id, accuse_id, accuse_role) REFERENCES implications (affaire_id, personne_id, role),
    CHECK ((accuse_id IS NULL) = (accusee_le IS NULL)),
    CHECK ((accuse_id IS NULL) = (reussie IS NULL)),
    CHECK ((accuse_id IS NULL) = (score IS NULL)),
    CHECK (accusee_le IS NULL OR accusee_le >= commencee_le)
);
CREATE UNIQUE INDEX une_partie_en_cours ON parties (joueur_id, affaire_id) WHERE accuse_id IS NULL;

-- RG11 : les quatre sortes d'action et leur durée (celle d'une analyse dépend du type d'indice).
CREATE TABLE types_action (
    code     text PRIMARY KEY,
    libelle  text NOT NULL UNIQUE,
    duree    integer CHECK (duree > 0)                                -- en minutes ; NULL pour « analyser »
);
INSERT INTO types_action VALUES
    ('interroger', 'Interroger une personne', 120), ('voisinage', 'Enquête de voisinage', 60),
    ('fouiller', 'Fouiller un lieu', 180), ('analyser', 'Analyser un scellé', NULL);

-- RG11 : chaque action d'une partie vise une seule cible : une personne de l'affaire, un lieu, ou un
-- indice de l'affaire. affaire_id est recopié exprès : les FK composites garantissent que la cible
-- est de l'affaire de la partie. duree est recopiée exprès, comme un prix payé : c'est ce que l'action
-- a coûté ce jour-là, même si le barème change ensuite.
CREATE TABLE actions (
    id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    partie_id    integer NOT NULL,
    affaire_id   integer NOT NULL,
    type         text NOT NULL REFERENCES types_action (code),
    personne_id  integer,
    lieu_id      integer REFERENCES lieux (id),
    indice_id    integer,
    duree        integer NOT NULL CHECK (duree > 0),
    faite_le     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (partie_id, affaire_id) REFERENCES parties (id, affaire_id) ON DELETE CASCADE,
    FOREIGN KEY (affaire_id, personne_id) REFERENCES implications (affaire_id, personne_id),
    FOREIGN KEY (indice_id, affaire_id) REFERENCES indices (id, affaire_id) ON DELETE CASCADE,
    -- RG11 : la bonne cible pour chaque sorte d'action, et une seule.
    CHECK (CASE type
             WHEN 'interroger' THEN personne_id IS NOT NULL AND lieu_id IS NULL AND indice_id IS NULL
             WHEN 'voisinage'  THEN personne_id IS NOT NULL AND lieu_id IS NULL AND indice_id IS NULL
             WHEN 'fouiller'   THEN personne_id IS NULL AND lieu_id IS NOT NULL AND indice_id IS NULL
             WHEN 'analyser'   THEN personne_id IS NULL AND lieu_id IS NULL AND indice_id IS NOT NULL
           END),
    -- RG11 : la même action sur la même cible, une seule fois par partie.
    UNIQUE NULLS NOT DISTINCT (partie_id, type, personne_id, lieu_id, indice_id)
);
CREATE INDEX ON actions (partie_id);


-- ===== Ce que les contraintes ne savent pas dire : les triggers =====

-- RG2 et RG4 : une affaire a une victime et au moins trois suspects. Vérifié en fin de transaction
-- (contrainte différée), quand l'affaire et ses implications sont toutes écrites.
CREATE OR REPLACE FUNCTION verifier_trois_suspects() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM implications WHERE affaire_id = NEW.id AND role = 'victime') THEN
        RAISE EXCEPTION 'RG2 : l''affaire % n''a pas de victime', NEW.code;
    END IF;
    IF (SELECT count(*) FROM implications WHERE affaire_id = NEW.id AND role = 'suspect') < 3 THEN
        RAISE EXCEPTION 'RG4 : l''affaire % a moins de trois suspects', NEW.code;
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER trois_suspects AFTER INSERT ON affaires
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION verifier_trois_suspects();

-- RG12 : une partie terminée ne se modifie plus.
CREATE OR REPLACE FUNCTION partie_figee() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.accuse_id IS NOT NULL THEN
        RAISE EXCEPTION 'RG12 : la partie % est terminée, elle ne se modifie plus', OLD.id;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER partie_figee BEFORE UPDATE ON parties FOR EACH ROW EXECUTE FUNCTION partie_figee();

-- RG11 et RG12 : avant chaque action, on fixe sa durée d'après le barème, puis on vérifie que la partie
-- est en cours et que le délai de l'affaire n'est pas dépassé. La partie est verrouillée (FOR UPDATE) :
-- deux actions lancées en même temps ne peuvent pas dépasser le délai à elles deux.
CREATE OR REPLACE FUNCTION avant_action() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    p        parties;
    delai    integer;
    utilise  integer;
BEGIN
    SELECT * INTO p FROM parties WHERE id = NEW.partie_id FOR UPDATE;
    IF p.accuse_id IS NOT NULL THEN
        RAISE EXCEPTION 'RG12 : la partie % est terminée', NEW.partie_id;
    END IF;
    IF NEW.type = 'analyser' THEN
        SELECT ti.duree_analyse INTO NEW.duree
        FROM indices i JOIN types_indice ti ON ti.code = i.type WHERE i.id = NEW.indice_id;
    ELSE
        SELECT duree INTO NEW.duree FROM types_action WHERE code = NEW.type;
    END IF;
    SELECT delai_minutes INTO delai FROM affaires WHERE id = p.affaire_id;
    SELECT coalesce(sum(duree), 0) INTO utilise FROM actions WHERE partie_id = NEW.partie_id;
    IF utilise + NEW.duree > delai THEN
        RAISE EXCEPTION 'RG11 : plus assez de temps (il reste % min, l''action en demande %)',
            delai - utilise, NEW.duree USING ERRCODE = 'P0011';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER avant_action BEFORE INSERT ON actions FOR EACH ROW EXECUTE FUNCTION avant_action();

-- RG11 : une action faite ne se modifie pas (sa durée est ce qu'elle a coûté).
CREATE OR REPLACE FUNCTION action_figee() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'RG11 : une action faite ne se modifie pas';
END $$;
CREATE TRIGGER action_figee BEFORE UPDATE ON actions FOR EACH ROW EXECUTE FUNCTION action_figee();


-- ===== Le coupable reste caché : la vue publique et l'accusation =====

-- Tout ce que le joueur a le droit de voir d'une affaire (sans coupable_id).
CREATE VIEW affaires_publiques AS
    SELECT id, code, titre, nature, resume, crime_le, lieu_crime_id, enquete_le, delai_minutes FROM affaires;

-- Le temps utilisé et restant de chaque partie, calculé à la demande (pas de copie à tenir à jour).
CREATE VIEW temps_parties AS
    SELECT p.id AS partie_id, a.delai_minutes,
           coalesce(sum(ac.duree), 0)::int AS utilise,
           (a.delai_minutes - coalesce(sum(ac.duree), 0))::int AS restant,
           a.enquete_le + make_interval(mins => coalesce(sum(ac.duree), 0)::int) AS horloge
    FROM parties p JOIN affaires a ON a.id = p.affaire_id
    LEFT JOIN actions ac ON ac.partie_id = p.id
    GROUP BY p.id, a.delai_minutes, a.enquete_le;

-- RG12 : l'accusation se fait en une seule transaction ; le score est calculé une fois et figé.
-- score = 50 + 10 par heure restante si c'est le bon suspect, 0 sinon.
CREATE OR REPLACE FUNCTION accuser(p_partie integer, p_accuse integer)
RETURNS parties LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    p       parties;
    ok      boolean;
    reste   integer;
BEGIN
    SELECT * INTO p FROM parties WHERE id = p_partie FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'partie % introuvable', p_partie; END IF;
    SELECT a.coupable_id = p_accuse INTO ok FROM affaires a WHERE a.id = p.affaire_id;
    SELECT restant INTO reste FROM temps_parties WHERE partie_id = p_partie;
    UPDATE parties SET
        accuse_id  = p_accuse,
        accusee_le = now(),
        reussie    = ok,
        score      = CASE WHEN ok THEN 50 + 10 * (reste / 60) ELSE 0 END
    WHERE id = p_partie
    RETURNING * INTO p;
    RETURN p;
END $$;
