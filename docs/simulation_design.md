# Simulation design

## Why I simulate

I study a fictional coffee subscription retailer. Customers pay $30 a month for a monthly box.

No public dataset has channel spend, channel signups, channel retention, and a past spend change for one business. I simulate the data and plant known effects. Tests check that the analysis finds them.

The random seed is 2026. I fixed it before generating any data. I will not change it.

The true values are in data/truth.json. Only the simulator and the tests may read that file. Analysis code must never read it.

## Data-generating process

There are 6 channels. I generate them in this order: paid_search, paid_social, affiliate, referral, direct_mail, podcast.

I use one numpy generator: rng = np.random.default_rng(2026).

There are 156 weeks. Week t starts on 2023-01-02 + 7*(t-1) days. Week 1 is 2023-01-02. Week 156 is 2025-12-22. The decision date is 2025-12-29.

The seasonal index uses p = (t-1) mod 52.

g(p) = 0.10*cos(2*pi*p/52) + 0.15 when 46 <= p <= 51, plus 0.08 when p <= 2.

s(p) = exp(g(p)) / the mean of exp(g(p)) for p from 0 to 51. It averages exactly 1.

A is the mean signups per week when spend is at its normal level. S is the normal weekly spend in dollars.

| channel | A | S | phi | sigma_e | p1 | h | variable cost | fixed monthly | launch week |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| paid_search | 150 | 4250 | 0.3 | 0.04 | 0.30 | 0.06 | 15 | 2000 | 1 |
| paid_social | 120 | 6850 | 0.3 | 0.04 | 0.45 | 0.09 | 15 | 3000 | 1 |
| affiliate | 80 | 3485 | 0.3 | 0.04 | 0.50 | 0.12 | 35 | 1500 | 1 |
| referral | 60 | 595 | 0.3 | 0.04 | 0.20 | 0.03 | 30 | 800 | 1 |
| direct_mail | 40 | 1855 | 0.0 | 0.35 | 0.35 | 0.07 | 15 | 1000 | 1 |
| podcast | 30 | 1465 | 0.5 | 0.08 | 0.30 | 0.07 | 15 | 1000 | 143 |

For each channel I draw the noise for all 156 weeks, then I keep weeks on or after the launch week.

sigma_u = sigma_e / sqrt(1 - phi^2). u_1 comes from Normal(0, sigma_u). After that, u_t = phi*u_(t-1) + Normal(0, sigma_e).

spend_t = S * exp(Normal(0, 0.05)). For paid_social in weeks 79 to 90, I multiply by 1.5. I then round spend to whole dollars.

mu_t = A * s(p) * (spend_t / S)^0.5.

Signups are Poisson(mu_t * exp(u_t - sigma_u^2 / 2)).

Each signup is one subscriber. The signup date is the week start plus a random whole number of days from 0 to 6.

With probability p1, the paid months T equal 1. Otherwise T = 1 + Geometric(h). I use numpy's geometric distribution, which starts at 1. I do not store T.

m_obs = floor((2025-12-29 - signup_date, in days) / 30.4375).

months_paid = min(T, m_obs + 1). A subscriber is cancelled when T <= m_obs.

Podcast starts in week 143. That week starts on 2025-09-22. It has 14 weeks of history before the decision date. I write no rows before a channel launches.

Variable cost covers the first-box discount, referral credits, and affiliate commission. Fixed monthly cost covers agency, platform, and production fees. Contribution per active subscriber month is $11.

## True values per channel

These come from the formulas below. They do not use the random draws.

E = 1 + (1 - p1) * the sum from i = 0 to 10 of (1 - h)^i.

E is the expected number of active months in the first 12 months. V = 11 * E.

Annual signups = A * 52.

Annual cost = 52*S + annual signups * variable cost + 12 * fixed monthly cost.

R = annual signups * V / annual cost.

Net = annual signups * V - annual cost.

Payback is the first month k from 1 to 12 where $11 times cumulative expected active months up to k is at least annual cost / annual signups. Otherwise payback is "over 12 months".

| channel | E | V | annual signups | annual cost | R | net | payback | intended call |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| paid_search | 6.76 | 74.36 | 7800 | 362000 | 1.60 | 217995 | 7 | FUND |
| paid_social | 4.95 | 54.40 | 6240 | 485800 | 0.70 | -146339 | over 12 months | CUT |
| affiliate | 4.15 | 45.60 | 4160 | 344820 | 0.55 | -155122 | over 12 months | CUT |
| referral | 8.59 | 94.51 | 3120 | 134140 | 2.20 | 160736 | 5 | FUND |
| direct_mail | 6.11 | 67.17 | 2080 | 139660 | 1.00 | 49 | 12 | HOLD |
| podcast | 6.50 | 71.49 | 1560 | 111580 | 1.00 | -58 | over 12 months | HOLD |

The table is rounded. data/truth.json holds the full values.

## Past spend change

The paid_social budget is 1.5 times its normal level for weeks 79 to 90. Signups scale with the square root of spend. The true effect is +22.5% signups during those 12 weeks.

The true log effect is 0.5 * ln(1.5). The true elasticity is 0.5.

## Why each channel sits where it does

FUND and CUT channels have true R far from 1.0 (1.60, 2.20, 0.70, 0.55). paid_search and referral are FUND. paid_social and affiliate are CUT.

direct_mail has true R of 1.00 and very noisy weekly signups, so its range should straddle 1.0. The intended call is HOLD.

podcast has true R of 1.00 and launched only 14 weeks before the decision date, so most of its 12-month retention is unknown and falls under the range rule. The intended call is HOLD.

I tested this design on prototype data across many seeds before generating the real data, and set the noise levels so the borderline channels are borderline by design. The FUND and CUT channels came out as intended every time.

The DiD channels have mild week-to-week carry-over so that Newey-West standard errors stay honest over a short window.
