# Power BI build guide - ShuttleIQ

## 1. Load the data
8 files from `data\processed\`:
`fact_match_result`, `dim_tournament`, `dim_event`, `dim_round`, `dim_team`, `dim_country`, `bridge_team_player`, `dim_player`.

In Power Query, `team_seed` and `opponent_seed` must be Whole Number, `start_date` and `end_date` Date.

## 2. Relationships (Model view)
(all many-to-one, single direction, from the fact side):

| From (many) | To (one) | State |
|---|---|---|
| fact_match_result[tournament_key] | dim_tournament[tournament_key] | active |
| fact_match_result[event_key] | dim_event[event_key] | active |
| fact_match_result[round_key] | dim_round[round_key] | active |
| fact_match_result[team_key] | dim_team[team_key] | active |
| fact_match_result[opponent_team_key] | dim_team[team_key] | inactive (role-playing) |
| dim_team[country_key] | dim_country[country_key] | active |

`bridge_team_player` and `dim_player` are kept for the MySQL model; in Power BI the team name already
shows the player (singles) or the pair (doubles), so no extra relationships are needed.
NOT related `dim_team[event_key]` to `dim_event`  (it would create two paths to dim_event).

## 3. Hierarchies (enables drill-down)
- `dim_country`: continent > country_name
- `dim_event`: discipline > event_name
- `dim_tournament`: tournament_name > edition_year
Right-click the top field in the Data pane > New hierarchy, then drag the lower field under it.

## 4. Measures
Add everything in `DAX_measures.md`.

## 5. Pages
Add slicers for **Edition** (dim_tournament) and **Event** (dim_event) on every page, and Sync slicers across pages.

**Page 1 - Overview**: cards = Matches, Teams, Countries Represented, Upset Rate, Deciding Game Rate, Retire Walkover Rate.
Clustered column: Matches by round_name (sorted by Round Order). Donut: Matches by result_type.

**Page 2 - Medal Table**: matrix with country_name in rows; Gold, Silver, Bronze, Total Medals as values
(use the country hierarchy, so you can drill continent > country). Stacked bar: Total Medals by country.

**Page 3 - Team Performance**: table with team_name, country_name, Team Match Rows, Wins, Win Rate,
Avg Winning Margin. Bar: top 10 teams by Wins (Top N filter). Add a **drill-through page** "Team detail"
(drag team_name into Drill-through fields) showing that team's matches by round.

**Page 4 - Upsets and Seeds**: column chart Win Rate by Seed Group. Column: Upsets by round_name.
Table of upset matches: add team_name (winner), opponent_team_key via a measure or use the `vw_upsets` output
(optional CSV). Card: Upset Rate.

**Page 5 - Match Quality**: line/column of Deciding Game Rate and Deuce Match Rate by round_name;
matrix Event > Round with Retire Walkover Rate. Use the event hierarchy for drill-down.

## 6. Save
File > Save as `ShuttleIQ.pbix` into `powerbi\` in the project folder.
