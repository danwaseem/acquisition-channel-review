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
