-- ShuttleIQ - Data Warehouse (Star schema with a team-player bridge)
-- Grain of fact_match_result: ONE ROW PER TEAM PER MATCH (2 rows per match).
-- A "team" is one player in singles and a pair in doubles.

CREATE DATABASE IF NOT EXISTS shuttleiq CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE shuttleiq;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS fact_match_result;
DROP TABLE IF EXISTS bridge_team_player;
DROP TABLE IF EXISTS dim_team;
DROP TABLE IF EXISTS dim_player;
DROP TABLE IF EXISTS dim_round;
DROP TABLE IF EXISTS dim_event;
DROP TABLE IF EXISTS dim_tournament;
DROP TABLE IF EXISTS dim_country;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE dim_country (
    country_key   INT PRIMARY KEY,
    ioc_code      VARCHAR(5)  NOT NULL UNIQUE,
    country_name  VARCHAR(60) NOT NULL,
    continent     VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE dim_tournament (
    tournament_key  INT PRIMARY KEY,
    tournament_name VARCHAR(100) NOT NULL,
    edition_year    SMALLINT     NOT NULL,
    host_city       VARCHAR(40)  NOT NULL,
    host_country    VARCHAR(40)  NOT NULL,
    start_date      DATE         NOT NULL,
    end_date        DATE         NOT NULL
) ENGINE=InnoDB;

CREATE TABLE dim_event (
    event_key       INT PRIMARY KEY,
    event_code      CHAR(2)     NOT NULL UNIQUE,
    event_name      VARCHAR(30) NOT NULL,
    discipline      VARCHAR(10) NOT NULL,
    gender_category VARCHAR(10) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE dim_round (
    round_key        INT PRIMARY KEY,
    stage_from_final TINYINT     NOT NULL UNIQUE,   -- 1=Final ... 6=Round of 64
    round_name       VARCHAR(20) NOT NULL,
    round_group      VARCHAR(20) NOT NULL           -- Early rounds / Business end
) ENGINE=InnoDB;

CREATE TABLE dim_player (
    player_key   INT PRIMARY KEY,
    player_name  VARCHAR(80) NOT NULL,
    country_key  INT NOT NULL,
    CONSTRAINT fk_player_country FOREIGN KEY (country_key) REFERENCES dim_country(country_key),
    UNIQUE KEY uq_player (player_name, country_key)
) ENGINE=InnoDB;

CREATE TABLE dim_team (
    team_key     INT PRIMARY KEY,
    event_key    INT NOT NULL,
    team_name    VARCHAR(170) NOT NULL,
    team_size    TINYINT NOT NULL,
    country_key  INT NOT NULL,
    CONSTRAINT fk_team_event   FOREIGN KEY (event_key)   REFERENCES dim_event(event_key),
    CONSTRAINT fk_team_country FOREIGN KEY (country_key) REFERENCES dim_country(country_key)
) ENGINE=InnoDB;

CREATE TABLE bridge_team_player (
    team_key   INT NOT NULL,
    player_key INT NOT NULL,
    PRIMARY KEY (team_key, player_key),
    CONSTRAINT fk_btp_team   FOREIGN KEY (team_key)   REFERENCES dim_team(team_key),
    CONSTRAINT fk_btp_player FOREIGN KEY (player_key) REFERENCES dim_player(player_key)
) ENGINE=InnoDB;

CREATE TABLE fact_match_result (
    result_key           INT PRIMARY KEY,
    match_id             VARCHAR(40) NOT NULL,
    tournament_key       INT NOT NULL,
    event_key            INT NOT NULL,
    round_key            INT NOT NULL,
    team_key             INT NOT NULL,
    opponent_team_key    INT NOT NULL,
    team_seed            SMALLINT NULL,
    opponent_seed        SMALLINT NULL,
    is_winner            TINYINT NOT NULL,
    games_won            TINYINT NOT NULL,
    games_lost           TINYINT NOT NULL,
    points_won           SMALLINT NOT NULL,
    points_lost          SMALLINT NOT NULL,
    games_played         TINYINT NOT NULL,
    deciding_game_played TINYINT NOT NULL,
    deuce_games          TINYINT NOT NULL,          -- games that went past 21 points
    is_upset             TINYINT NOT NULL,          -- lower seed / unseeded beat a seed
    result_type          VARCHAR(12) NOT NULL,      -- Completed / Retired / Walkover / NoScore
    bracket_section      VARCHAR(60) NULL,
    CONSTRAINT fk_f_tournament FOREIGN KEY (tournament_key)    REFERENCES dim_tournament(tournament_key),
    CONSTRAINT fk_f_event      FOREIGN KEY (event_key)         REFERENCES dim_event(event_key),
    CONSTRAINT fk_f_round      FOREIGN KEY (round_key)         REFERENCES dim_round(round_key),
    CONSTRAINT fk_f_team       FOREIGN KEY (team_key)          REFERENCES dim_team(team_key),
    CONSTRAINT fk_f_opponent   FOREIGN KEY (opponent_team_key) REFERENCES dim_team(team_key),
    UNIQUE KEY uq_match_team (match_id, team_key),
    KEY ix_f_team (team_key),
    KEY ix_f_tourn_event (tournament_key, event_key, round_key)
) ENGINE=InnoDB;
