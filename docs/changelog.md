# Changelog

## 2026-08-16

Wrote the analysis plan before generating any data.

I decided the following before any data was generated.

- Range rule detail: each bootstrap draw uses one uniform number for all of a channel's unknown months, because a channel's churn level tends to persist across months.
- Forecast paths also include uncertainty in the fitted regression coefficients (intercept, Fourier terms, spend), drawn from their estimated covariance matrix. For the short-history rule this is the intercept. Without this, intervals are too narrow.
- Payback month is reported only up to month 12, since V only covers 12 months. Otherwise it is "over 12 months".
- DiD standard errors use fixest vcov = "NW" with its default lag.
