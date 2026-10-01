-- ShuttleIQ - KPI layer (MySQL views on the star schema)
-- Run after scripts/02_etl_load.py. Fact grain: one row per team per match.
USE shuttleiq;

-- 1. Team performance per edition and event (win rate, games, points)
CREATE OR REPLACE VIEW vw_team_performance AS
SELECT tr.edition_year, e.event_name, t.team_name, c.country_name,
       COUNT(*)                                   AS matches_played,
       SUM(f.is_winner)                           AS wins,
       ROUND(100 * SUM(f.is_winner) / COUNT(*), 1) AS win_rate_pct,
       SUM(f.games_won)                           AS games_won,
       SUM(f.games_lost)                          AS games_lost,
       SUM(f.points_won) - SUM(f.points_lost)     AS point_diff,
       MIN(CASE WHEN f.is_winner = 1 OR f.round_key >= 1 THEN f.round_key END) AS best_stage_reached
FROM fact_match_result f
JOIN dim_tournament tr ON tr.tournament_key = f.tournament_key
JOIN dim_event e       ON e.event_key       = f.event_key
JOIN dim_team t        ON t.team_key        = f.team_key
JOIN dim_country c     ON c.country_key     = t.country_key
GROUP BY tr.edition_year, e.event_name, t.team_name, c.country_name;

-- 2. Medal table by country (Gold = final winner, Silver = final loser, Bronze = semi-final losers)
CREATE OR REPLACE VIEW vw_medal_table AS
SELECT tr.edition_year, c.continent, c.country_name,
       SUM(f.round_key = 1 AND f.is_winner = 1) AS gold,
       SUM(f.round_key = 1 AND f.is_winner = 0) AS silver,
       SUM(f.round_key = 2 AND f.is_winner = 0) AS bronze,
       SUM((f.round_key = 1) OR (f.round_key = 2 AND f.is_winner = 0)) AS total_medals
FROM fact_match_result f
JOIN dim_tournament tr ON tr.tournament_key = f.tournament_key
JOIN dim_team t        ON t.team_key        = f.team_key
JOIN dim_country c     ON c.country_key     = t.country_key
GROUP BY tr.edition_year, c.continent, c.country_name
HAVING total_medals > 0;

-- 3. Upsets: lower-seeded / unseeded team beat a seeded team
CREATE OR REPLACE VIEW vw_upsets AS
SELECT tr.edition_year, e.event_name, r.round_name,
       w.team_name AS winner, f.team_seed AS winner_seed,
       l.team_name AS loser,  f.opponent_seed AS loser_seed,
       f.games_won, f.games_lost
FROM fact_match_result f
JOIN dim_tournament tr ON tr.tournament_key = f.tournament_key
JOIN dim_event e       ON e.event_key       = f.event_key
JOIN dim_round r       ON r.round_key       = f.round_key
JOIN dim_team w        ON w.team_key        = f.team_key
JOIN dim_team l        ON l.team_key        = f.opponent_team_key
WHERE f.is_winner = 1 AND f.is_upset = 1;

-- 4. Seed performance: does seeding predict winning?
CREATE OR REPLACE VIEW vw_seed_performance AS
SELECT CASE WHEN team_seed IS NULL THEN 'Unseeded'
            WHEN team_seed <= 4    THEN 'Seeds 1-4'
            WHEN team_seed <= 8    THEN 'Seeds 5-8'
            ELSE 'Seeds 9-16' END AS seed_group,
       COUNT(*) AS matches, SUM(is_winner) AS wins,
       ROUND(100 * SUM(is_winner) / COUNT(*), 1) AS win_rate_pct
FROM fact_match_result
WHERE result_type = 'Completed'
GROUP BY seed_group;

-- 5. Match quality per event and round: deciding games, deuce games, walkovers/retirements
CREATE OR REPLACE VIEW vw_match_quality AS
SELECT tr.edition_year, e.event_name, r.round_name,
       COUNT(*) / 2                                                AS matches,
       ROUND(100 * SUM(f.deciding_game_played) / COUNT(*), 1)      AS deciding_game_pct,
       ROUND(100 * SUM(f.deuce_games > 0) / COUNT(*), 1)           AS deuce_match_pct,
       ROUND(100 * SUM(f.result_type IN ('Retired','Walkover')) / COUNT(*), 1) AS retire_walkover_pct
FROM fact_match_result f
JOIN dim_tournament tr ON tr.tournament_key = f.tournament_key
JOIN dim_event e       ON e.event_key       = f.event_key
JOIN dim_round r       ON r.round_key       = f.round_key
GROUP BY tr.edition_year, e.event_name, r.round_name, r.stage_from_final;

-- 6. Head-to-head between any two teams across both editions
CREATE OR REPLACE VIEW vw_head_to_head AS
SELECT a.team_name AS team, b.team_name AS opponent, e.event_name,
       COUNT(*) AS meetings, SUM(f.is_winner) AS team_wins,
       COUNT(*) - SUM(f.is_winner) AS opponent_wins
FROM fact_match_result f
JOIN dim_team a ON a.team_key = f.team_key
JOIN dim_team b ON b.team_key = f.opponent_team_key
JOIN dim_event e ON e.event_key = f.event_key
GROUP BY a.team_name, b.team_name, e.event_name;
