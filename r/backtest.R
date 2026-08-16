# Back-test three seasonal forecast variants.
# Run from the repo root: Rscript r/backtest.R

set.seed(2026)

suppressPackageStartupMessages({
  library(forecast)
  library(dplyr)
  library(readr)
  library(jsonlite)
})

options(warn = 1)

if (!file.exists("data/weekly_channel.csv")) {
  stop("Run this from the repo root: Rscript r/backtest.R", call. = FALSE)
}

dir.create("outputs/tables", recursive = TRUE, showWarnings = FALSE)

weekly <- read_csv(
  "data/weekly_channel.csv",
  show_col_types = FALSE
)

long_channels <- weekly %>%
  count(channel, name = "n_weeks") %>%
  filter(n_weeks >= 104) %>%
  arrange(channel) %>%
  pull(channel)

train_ends <- c(104L, 117L, 130L, 143L)
horizon <- 13L

order_string <- function(fit) {
  ord <- forecast::arimaorder(fit)
  paste(unname(ord[c("p", "d", "q")]), collapse = ",")
}

forecast_frame <- function(channel, variant, fold_id, test, fc) {
  data.frame(
    channel = channel,
    variant = variant,
    fold = fold_id,
    week = test$week,
    actual = test$signups,
    point = as.numeric(fc$mean),
    lo80 = as.numeric(fc$lower),
    hi80 = as.numeric(fc$upper),
    stringsAsFactors = FALSE
  )
}

metric_row <- function(channel, variant, fold_id, train_end, K, fit, test, fc) {
  actual <- test$signups
  point <- as.numeric(fc$mean)
  lo80 <- as.numeric(fc$lower)
  hi80 <- as.numeric(fc$upper)
  data.frame(
    channel = channel,
    variant = variant,
    fold = fold_id,
    train_end_week = train_end,
    K = K,
    arima_order = order_string(fit),
    mape = mean(abs(point - actual) / actual) * 100,
    total_pct_error = (sum(point) - sum(actual)) / sum(actual) * 100,
    coverage80 = mean(actual >= lo80 & actual <= hi80),
    stringsAsFactors = FALSE
  )
}

fit_snaive <- function(y, channel, train_end) {
  fit <- tryCatch(
    forecast::Arima(
      y,
      order = c(0, 0, 0),
      seasonal = c(0, 1, 0),
      include.constant = FALSE,
      lambda = 0
    ),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    stop(sprintf(
      "Seasonal naive fit failed for %s, training end week %d: %s",
      channel, train_end, conditionMessage(fit)
    ), call. = FALSE)
  }
  fc <- tryCatch(
    forecast::forecast(fit, h = horizon, level = 80, biasadj = FALSE),
    error = function(e) e
  )
  if (inherits(fc, "error")) {
    stop(sprintf(
      "Seasonal naive forecast failed for %s, training end week %d: %s",
      channel, train_end, conditionMessage(fc)
    ), call. = FALSE)
  }
  list(fit = fit, fc = fc, K = NA_integer_)
}

fit_one_k <- function(y, K, spend_train, spend_future) {
  xreg <- forecast::fourier(y, K = K)
  newxreg <- forecast::fourier(y, K = K, h = horizon)
  if (!is.null(spend_train)) {
    xreg <- cbind(xreg, log_spend = log(spend_train))
    newxreg <- cbind(newxreg, log_spend = log(spend_future))
  }
  tryCatch(
    {
      fit <- forecast::auto.arima(
        y,
        xreg = xreg,
        seasonal = FALSE,
        lambda = 0
      )
      if (!is.finite(fit$aicc)) {
        stop("AICc is not finite")
      }
      fc <- forecast::forecast(
        fit,
        h = horizon,
        level = 80,
        xreg = newxreg,
        biasadj = FALSE
      )
      list(fit = fit, fc = fc, aicc = fit$aicc, K = K)
    },
    error = function(e) NULL
  )
}

pick_fourier <- function(y, channel, train_end, variant, spend_train, spend_future) {
  best <- NULL
  for (K in 1:10) {
    candidate <- fit_one_k(y, K, spend_train, spend_future)
    if (is.null(candidate)) {
      message(sprintf(
        "Skipped K=%d for %s %s training end week %d",
        K, channel, variant, train_end
      ))
      next
    }
    if (is.null(best) || candidate$aicc < best$aicc) {
      best <- candidate
    }
  }
  if (is.null(best)) {
    stop(sprintf(
      "All Fourier fits failed for %s, variant %s, training end week %d",
      channel, variant, train_end
    ), call. = FALSE)
  }
  best
}

forecast_rows <- list()
metric_rows <- list()

for (channel_name in long_channels) {
  history <- weekly %>%
    filter(.data$channel == .env$channel_name) %>%
    arrange(week)

  for (fold_id in seq_along(train_ends)) {
    train_end <- train_ends[[fold_id]]
    train <- history %>% filter(week <= train_end)
    test <- history %>%
      filter(week > train_end, week <= train_end + horizon) %>%
      arrange(week)
    if (nrow(test) != horizon) {
      stop(sprintf(
        "%s fold ending week %d does not have %d held-out weeks",
        channel, train_end, horizon
      ), call. = FALSE)
    }

    y <- ts(train$signups, frequency = 52)
    message(sprintf(
      "Fitting %s, fold %d, training end week %d",
      channel_name, fold_id, train_end
    ))

    snaive <- fit_snaive(y, channel_name, train_end)
    forecast_rows[[length(forecast_rows) + 1]] <- forecast_frame(
      channel_name, "snaive", fold_id, test, snaive$fc
    )
    metric_rows[[length(metric_rows) + 1]] <- metric_row(
      channel_name, "snaive", fold_id, train_end, snaive$K, snaive$fit, test, snaive$fc
    )

    fourier_fit <- pick_fourier(
      y, channel_name, train_end, "fourier", NULL, NULL
    )
    message(sprintf("  fourier K=%d AICc=%.2f", fourier_fit$K, fourier_fit$aicc))
    forecast_rows[[length(forecast_rows) + 1]] <- forecast_frame(
      channel_name, "fourier", fold_id, test, fourier_fit$fc
    )
    metric_rows[[length(metric_rows) + 1]] <- metric_row(
      channel_name, "fourier", fold_id, train_end, fourier_fit$K,
      fourier_fit$fit, test, fourier_fit$fc
    )

    spend_fit <- pick_fourier(
      y, channel_name, train_end, "fourier_spend", train$spend, test$spend
    )
    message(sprintf("  fourier_spend K=%d AICc=%.2f", spend_fit$K, spend_fit$aicc))
    forecast_rows[[length(forecast_rows) + 1]] <- forecast_frame(
      channel_name, "fourier_spend", fold_id, test, spend_fit$fc
    )
    metric_rows[[length(metric_rows) + 1]] <- metric_row(
      channel_name, "fourier_spend", fold_id, train_end, spend_fit$K,
      spend_fit$fit, test, spend_fit$fc
    )
  }
}

forecasts <- bind_rows(forecast_rows)
metrics <- bind_rows(metric_rows)

variant_rank <- c(snaive = 1L, fourier = 2L, fourier_spend = 3L)

coverage_all <- forecasts %>%
  mutate(inside = actual >= lo80 & actual <= hi80) %>%
  group_by(channel, variant) %>%
  summarise(coverage80 = mean(inside), .groups = "drop")

summary_base <- metrics %>%
  group_by(channel, variant) %>%
  summarise(
    mean_mape = mean(mape),
    mean_abs_total_error = mean(abs(total_pct_error)),
    min_total_error = min(total_pct_error),
    max_total_error = max(total_pct_error),
    .groups = "drop"
  ) %>%
  inner_join(coverage_all, by = c("channel", "variant"))

summary_rows <- list()
for (channel_name in unique(summary_base$channel)) {
  part <- summary_base %>% filter(.data$channel == .env$channel_name)
  best <- min(part$mean_mape)
  eligible <- part$mean_mape <= best + 0.5
  eligible_rank <- variant_rank[part$variant[eligible]]
  winner <- names(eligible_rank)[which.min(eligible_rank)]
  part$chosen <- part$variant == winner
  part$widen <- part$chosen & part$coverage80 < 0.65
  summary_rows[[length(summary_rows) + 1]] <- part
}

summary_tbl <- bind_rows(summary_rows) %>%
  mutate(
    variant = factor(variant, levels = c("snaive", "fourier", "fourier_spend"))
  ) %>%
  arrange(channel, variant) %>%
  mutate(variant = as.character(variant)) %>%
  select(
    channel,
    variant,
    mean_mape,
    mean_abs_total_error,
    min_total_error,
    max_total_error,
    coverage80,
    chosen,
    widen
  )

write_csv(forecasts, "outputs/tables/backtest_forecasts.csv")
write_csv(metrics, "outputs/tables/backtest_metrics.csv")
write_csv(summary_tbl, "outputs/tables/backtest_summary.csv")

versions <- data.frame(
  package = c("forecast", "dplyr", "readr", "jsonlite"),
  version = vapply(
    c("forecast", "dplyr", "readr", "jsonlite"),
    function(pkg) as.character(packageVersion(pkg)),
    character(1)
  ),
  stringsAsFactors = FALSE
)

writeLines(
  c(
    capture.output(sessionInfo()),
    "",
    "Package versions used:",
    jsonlite::toJSON(versions, pretty = TRUE, auto_unbox = TRUE)
  ),
  "outputs/tables/r_session.txt"
)

message("Wrote back-test tables to outputs/tables")
