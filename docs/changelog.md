# Changelog

## 2026-08-16

Wrote the analysis plan before generating any data.

I decided the following before any data was generated.

- Range rule detail: each bootstrap draw uses one uniform number for all of a channel's unknown months, because a channel's churn level tends to persist across months.
- Forecast paths also include uncertainty in the fitted regression coefficients (intercept, Fourier terms, spend), drawn from their estimated covariance matrix. For the short-history rule this is the intercept. Without this, intervals are too narrow.
- Payback month is reported only up to month 12, since V only covers 12 months. Otherwise it is "over 12 months".
- DiD standard errors use fixest vcov = "NW" with its default lag.

## 2026-08-17

I decided the following before running the final forecasts.

- The pooled seasonal pattern for the short-history rule is the average of the long-history channels' Fourier seasonal component from the "fourier" variant refit on all 156 weeks (log scale, centered to mean 0 over the 52 positions). I use the "fourier" variant for every long channel so the pattern does not depend on spend.
- If a channel is widened by the 1.5x rule, each path total becomes median * (total / median)^1.5.

I wrote the following before the cost-benefit and decision code was run.

- Forecast draw i is paired with value draw i. The two sets of draws are independent, so this pairing is fair.
- Payback month uses the median survival curve (s1 to s12 in value_summary.csv) and the median cost per signup.
- HOLD details: break-even signups per week = (52 * planned weekly spend + 12 * fixed monthly cost) / (V_median - variable cost) / 52. Break-even V = median 12-month cost / median forecast signups. For a channel with unknown retention months, break-even churn = the single monthly churn rate in the unknown months that makes V equal break-even V (estimated months stay at their estimates).
- Extra output, added after the DiD step and before this step ran: marginal return per extra dollar at current spend = elasticity * median signups * (V_median - variable cost) / (52 * planned weekly spend). It does not change any FUND, CUT or HOLD call.
