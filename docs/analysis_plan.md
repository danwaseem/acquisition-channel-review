# Analysis plan

## Context

I study a fictional coffee subscription retailer. Customers pay $30 a month for a monthly box.

The data is simulated. No public dataset has channel spend, channel signups, channel retention, and a past spend change for one business. I simulate it and plant known effects so tests can check the analysis finds them. The true values go in docs/simulation_design.md. I write that file in the next step, after this plan is committed.

There are 6 acquisition channels: paid_search, paid_social, affiliate, referral, direct_mail, and podcast.

The data is weekly. There are 156 weeks. Week start dates run from 2023-01-02 to 2025-12-22. The decision date is 2025-12-29. I forecast the next 52 weeks (calendar 2026).

The random seed is 2026. I fix it now. I never change it.

## Metrics

Contribution per active subscriber month is $11. That is the $30 price minus coffee, packing, shipping, and payment fees.

12-month value per subscriber (V) = $11 x expected active months in the subscriber's first 12 months.

12-month cost per channel = planned media spend (52 weeks at the channel's average weekly spend over the last 13 weeks) + variable cost per signup x forecast signups + 12 x the channel's fixed monthly cost. Variable cost covers the first-box discount, referral credits, and affiliate commission. Fixed cost covers agency, platform, and production fees.

Value-to-cost ratio (R) = forecast 12-month signups x V / 12-month cost. R = 1.0 means the channel pays back within 12 months.

Net contribution = forecast 12-month signups x V - 12-month cost. This is what I rank channels by.

Payback month = the first month where $11 x cumulative expected active months per subscriber is at least the full cost per signup (12-month cost / forecast signups).

## Retention

I build a monthly life table per channel with DuckDB SQL from subscriber-level data. Month k hazard = subscribers who cancel after k paid months / subscribers still active at month k whose follow-up reaches month k.

A month's hazard is only estimated if at least 30 subscribers are at risk. Otherwise it counts as unknown.

Unknown months (for example a new channel without 12 months of history) use a range rule. Each draw takes a value uniformly between the lowest and highest estimated hazard for that month among the other channels.

Uncertainty: 2,000 parametric bootstrap draws of the monthly hazards (binomial on the at-risk counts), giving 2,000 draws of V per channel.

## Forecasting and back-test (R, forecast package)

I model log weekly signups. The seasonal period is 52.

I fit 3 variants:

1. Seasonal naive: Arima with seasonal order (0,1,0), no constant.
2. Harmonic regression: Fourier terms with ARIMA errors (auto.arima, seasonal = FALSE). I pick K from 1 to 10 by AICc on the training data.
3. Harmonic regression plus log weekly spend as an extra regressor.

Back-test: 4 rolling folds. I train on weeks 1 to 104, 1 to 117, 1 to 130, and 1 to 143. Each fold forecasts the next 13 weeks.

I report per channel, variant, and fold: MAPE on weekly signups, percent error on the 13-week total, and coverage of the 80% prediction interval. These are the error bands.

I pick the variant with the lowest mean MAPE across the 4 folds. If two are within 0.5 percentage points, I pick the simpler one (order 1, 2, 3).

If the chosen variant's 80% interval coverage across folds is below 65%, I widen that channel's final intervals by 1.5x and log it.

Final forecast: I refit the chosen variant on all 156 weeks and simulate 2,000 future paths of 52 weeks. For variant 3, future spend = the channel's average weekly spend over the last 13 weeks.

Short history rule: a channel with fewer than 104 weeks of data is not back-tested. I divide its signups by the pooled seasonal pattern from the long-history channels, fit ARIMA(1,0,0) with a mean to the log of that, simulate 2,000 paths, and multiply the pattern back.

## Past spend change: difference-in-differences (R, fixest)

Event: the paid_social budget was raised for 12 weeks, weeks starting 2024-07-01 to 2024-09-16 (weeks 79 to 90).

Treated: paid_social. Controls: paid_search, affiliate, and referral. I leave direct_mail out because its signups are very noisy. podcast had not launched yet.

Window: pre period weeks 53 to 78. Post period weeks 79 to 90.

Model: log(signups) ~ treated x post, with channel and week fixed effects. I use panel Newey-West standard errors.

Checks: a placebo test with a fake event in weeks 66 to 77 (it should show no effect), and a reversal check on weeks 91 to 102 after spend went back to normal (the effect should go away).

I turn the result into extra signups per week, the cost of each extra signup, and the implied spend elasticity (log effect / log of the spend ratio).

## Decision rules

I pair the 2,000 forecast signup totals with the 2,000 V draws to get 2,000 draws of R per channel.

FUND: the 5th percentile of R is at least 1.0. It pays back even in a weak year.

CUT: the 95th percentile of R is below 1.0. It fails even in a strong year.

HOLD: anything else. This means there is not enough evidence for a confident call. I keep current spend and collect the data named below.

For each HOLD channel I report the break-even signups per week, the break-even value per subscriber, and the specific data that would settle it.

## Budget scenario

I move the planned spend of CUT channels to FUND channels, split in proportion to their current spend.

I assume FUND channels respond to extra spend with the elasticity measured in the DiD. This is an assumption and I say so. I report extra signups and extra net contribution.

## Outputs

Charts: history plus 52-week forecast with bands per channel, back-test error by variant, DiD treated vs control, R ranges against the 1.0 line, net contribution ranking, and retention curves.

I build a 5-slide deck for non-technical stakeholders by code from the result files: (1) the answer, (2) ranking by contribution, (3) how sure we are, (4) what the past spend change showed, (5) the channels we cannot call yet and what data would change the call.

Tests check that the analysis recovers the planted effects.

## Rules I follow

This plan is committed before any data exists.

I do not change the data or these rules after seeing results. Any change goes in docs/changelog.md with the date and reason.
