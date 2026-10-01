# ShuttleIQ - DAX measures and columns (Power BI)

Create a table `_Measures` (Home > Enter Data, one blank column, name it `_Measures`), then add each measure below
with New measure. Table names match the CSV file names.

## Measures
```dax
Matches = DISTINCTCOUNT(fact_match_result[match_id])

Team Match Rows = COUNTROWS(fact_match_result)

Wins = CALCULATE(COUNTROWS(fact_match_result), fact_match_result[is_winner] = 1)

Win Rate = DIVIDE([Wins], [Team Match Rows])

Upsets = CALCULATE(DISTINCTCOUNT(fact_match_result[match_id]), fact_match_result[is_upset] = 1)

Upset Rate = DIVIDE([Upsets], [Matches])

Deciding Game Rate =
DIVIDE(CALCULATE(DISTINCTCOUNT(fact_match_result[match_id]),
        fact_match_result[deciding_game_played] = 1), [Matches])

Deuce Match Rate =
DIVIDE(CALCULATE(DISTINCTCOUNT(fact_match_result[match_id]),
        fact_match_result[deuce_games] > 0), [Matches])

Retire Walkover Rate =
DIVIDE(CALCULATE(DISTINCTCOUNT(fact_match_result[match_id]),
        fact_match_result[result_type] IN {"Retired", "Walkover"}), [Matches])

Avg Winning Margin (pts) =
VAR w = CALCULATETABLE(fact_match_result,
            fact_match_result[is_winner] = 1, fact_match_result[result_type] = "Completed")
RETURN DIVIDE(SUMX(w, fact_match_result[points_won] - fact_match_result[points_lost]), COUNTROWS(w))

Gold   = CALCULATE(COUNTROWS(fact_match_result), fact_match_result[round_key] = 1, fact_match_result[is_winner] = 1)
Silver = CALCULATE(COUNTROWS(fact_match_result), fact_match_result[round_key] = 1, fact_match_result[is_winner] = 0)
Bronze = CALCULATE(COUNTROWS(fact_match_result), fact_match_result[round_key] = 2, fact_match_result[is_winner] = 0)
Total Medals = [Gold] + [Silver] + [Bronze]

Countries Represented = DISTINCTCOUNT(dim_team[country_key])
Teams = DISTINCTCOUNT(fact_match_result[team_key])
```

## Calculated columns
In `fact_match_result`:
```dax
Seed Group =
SWITCH(TRUE(),
    ISBLANK(fact_match_result[team_seed]), "Unseeded",
    fact_match_result[team_seed] <= 4, "Seeds 1-4",
    fact_match_result[team_seed] <= 8, "Seeds 5-8",
    "Seeds 9-16")
```
In `dim_round`:
```dax
Round Order = 7 - dim_round[stage_from_final]
```
Then select the `round_name` column > Column tools > Sort by column > `Round Order`
(this shows Round of 64 first and Final last).

In `dim_tournament`:
```dax
Edition = "WC " & dim_tournament[edition_year]
```
