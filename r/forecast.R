# Final 52-week signup forecasts with simulated paths.
# Run from the repo root: Rscript r/forecast.R

set.seed(2026)

suppressPackageStartupMessages({
  library(forecast)
  library(dplyr)
  library(readr)
  library(jsonlite)
})

options(warn = 1)

if (!file.exists("data/weekly_channel.csv")) {
  stop("Run this from the repo root: Rscript r/forecast.R", call. = FALSE)
}
if (!file.exists("outputs/tables/backtest_summary.csv")) {
  stop("Need outputs/tables/backtest_summary.csv from the back-test.", call. = FALSE)
}

dir.create("outputs/tables", recursive = TRUE, showWarnings = FALSE)

n_paths <- 2000L
horizon <- 52L
first_future_week <- 157L
last_history_week <- 156L
first_week_start <- as.Date("2023-01-02")

weekly <- read_csv("data/weekly_channel.csv", show_col_types = FALSE)
summary_tbl <- read_csv(
  "outputs/tables/backtest_summary.csv",
  show_col_types = FALSE
)

channel_weeks <- weekly %>%
  count(channel, name = "n_weeks")

long_channels <- channel_weeks %>%
  filter(n_weeks >= 104) %>%
  arrange(channel) %>%
  pull(channel)

short_channels <- channel_weeks %>%
  filter(n_weeks < 104) %>%
  arrange(channel) %>%
  pull(channel)

chosen <- summary_tbl %>%
  filter(chosen) %>%
  select(channel, variant, widen)

future_weeks <- first_future_week:(first_future_week + horizon - 1L)
future_starts <- first_week_start + 7 * (future_weeks - 1L)
future_p <- (future_weeks - 1L) %% 52L

planned_spend <- weekly %>%
  group_by(channel) %>%
  arrange(week, .by_group = TRUE) %>%
  summarise(
    planned_weekly_spend = mean(tail(spend, 13)),
    last_52w_signups = {
      recent <- signups[week >= 105 & week <= 156]
      # Need the full last 52 history weeks. Short-history channels get NA.
      if (length(recent) == 52) sum(recent) else NA_real_
    },
    .groups = "drop"
  )

order_string <- function(fit) {
  ord <- forecast::arimaorder(fit)
  paste(unname(ord[c("p", "d", "q")]), collapse = ",")
}

fit_one_k <- function(y, K, spend) {
  xreg <- forecast::fourier(y, K = K)
  if (!is.null(spend)) {
    xreg <- cbind(xreg, log_spend = log(spend))
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
      list(fit = fit, aicc = fit$aicc, K = K)
    },
    error = function(e) NULL
  )
}

pick_fourier <- function(y, channel_name, variant, spend) {
  best <- NULL
  for (K in 1:10) {
    candidate <- fit_one_k(y, K, spend)
    if (is.null(candidate)) {
      message(sprintf(
        "Skipped K=%d for %s variant %s on full history",
        K, channel_name, variant
      ))
      next
    }
    if (is.null(best) || candidate$aicc < best$aicc) {
      best <- candidate
    }
  }
  if (is.null(best)) {
    stop(sprintf(
      "All Fourier fits failed for %s variant %s on full history",
      channel_name, variant
    ), call. = FALSE)
  }
  best
}

fit_snaive <- function(y, channel_name) {
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
      "Seasonal naive fit failed for %s on full history: %s",
      channel_name, conditionMessage(fit)
    ), call. = FALSE)
  }
  list(fit = fit, K = NA_integer_)
}

regression_names <- function(fit) {
  names_coef <- names(fit$coef)
  if (is.null(names_coef) || length(names_coef) == 0) {
    return(character(0))
  }
  arma_pat <- "^(ar|ma|sar|sma)[0-9]+$"
  keep <- !grepl(arma_pat, names_coef)
  names_coef[keep]
}

future_xreg_for_fit <- function(fit, y, K, planned, variant) {
  if (identical(variant, "snaive")) {
    return(NULL)
  }
  xreg <- forecast::fourier(y, K = K, h = horizon)
  if (identical(variant, "fourier_spend")) {
    xreg <- cbind(xreg, log_spend = log(rep(planned, horizon)))
  }
  xreg
}

draw_coeff_noise <- function(fit, future_xreg, n_paths) {
  reg_names <- regression_names(fit)
  noise <- matrix(0, nrow = n_paths, ncol = horizon)

  if (length(reg_names) == 0) {
    return(noise)
  }

  cov <- as.matrix(fit$var.coef[reg_names, reg_names, drop = FALSE])
  # Cholesky of the covariance. Sigma = t(U) %*% U for R's chol(U).
  chol_factor <- tryCatch(
    chol(cov),
    error = function(e) NULL
  )
  if (is.null(chol_factor)) {
    stop("Could not factor the coefficient covariance matrix.", call. = FALSE)
  }

  x_future <- matrix(0, nrow = horizon, ncol = length(reg_names))
  colnames(x_future) <- reg_names
  if ("intercept" %in% reg_names) {
    x_future[, "intercept"] <- 1
  }
  if (!is.null(future_xreg)) {
    shared <- intersect(colnames(future_xreg), reg_names)
    for (name in shared) {
      x_future[, name] <- future_xreg[, name]
    }
  }

  z <- matrix(rnorm(n_paths * length(reg_names)), nrow = length(reg_names))
  delta <- t(chol_factor) %*% z
  noise <- t(x_future %*% delta)
  noise
}

widen_totals <- function(totals) {
  med <- stats::median(totals)
  med * (totals / med)^1.5
}

simulate_long_channel <- function(channel_name, variant, widen_flag, planned) {
  history <- weekly %>%
    filter(.data$channel == .env$channel_name) %>%
    arrange(week)
  y <- ts(history$signups, frequency = 52)

  if (identical(variant, "snaive")) {
    picked <- fit_snaive(y, channel_name)
    fit <- picked$fit
    K <- picked$K
    future_xreg <- NULL
  } else if (identical(variant, "fourier")) {
    picked <- pick_fourier(y, channel_name, variant, NULL)
    fit <- picked$fit
    K <- picked$K
    future_xreg <- future_xreg_for_fit(fit, y, K, planned, variant)
  } else if (identical(variant, "fourier_spend")) {
    picked <- pick_fourier(y, channel_name, variant, history$spend)
    fit <- picked$fit
    K <- picked$K
    future_xreg <- future_xreg_for_fit(fit, y, K, planned, variant)
  } else {
    stop(sprintf("Unknown variant %s for %s", variant, channel_name), call. = FALSE)
  }

  weekly_paths <- matrix(NA_real_, nrow = n_paths, ncol = horizon)
  for (i in seq_len(n_paths)) {
    sim <- if (is.null(future_xreg)) {
      stats::simulate(fit, nsim = horizon, future = TRUE)
    } else {
      stats::simulate(fit, nsim = horizon, xreg = future_xreg, future = TRUE)
    }
    weekly_paths[i, ] <- as.numeric(sim)
  }

  log_paths <- log(weekly_paths)
  log_paths <- log_paths + draw_coeff_noise(fit, future_xreg, n_paths)
  weekly_paths <- exp(log_paths)
  totals <- rowSums(weekly_paths)

  if (isTRUE(widen_flag)) {
    new_totals <- widen_totals(totals)
    scale <- new_totals / totals
    weekly_paths <- weekly_paths * scale
    totals <- new_totals
  }

  list(
    method = variant,
    K = K,
    arima_order = order_string(fit),
    weekly_paths = weekly_paths,
    totals = totals,
    widen = isTRUE(widen_flag)
  )
}

# Pooled seasonal pattern from the fourier variant on every long channel.
seasonal_parts <- list()
for (channel_name in long_channels) {
  history <- weekly %>%
    filter(.data$channel == .env$channel_name) %>%
    arrange(week)
  y <- ts(history$signups, frequency = 52)
  picked <- pick_fourier(y, channel_name, "fourier", NULL)
  fit <- picked$fit
  K <- picked$K
  fourier_names <- grep("^[SC][0-9]+-52$", names(fit$coef), value = TRUE)
  if (length(fourier_names) == 0) {
    stop(sprintf("No Fourier coefficients for pooled pattern on %s", channel_name),
         call. = FALSE)
  }
  fmat <- forecast::fourier(y, K = K)[1:52, fourier_names, drop = FALSE]
  seasonal <- as.numeric(fmat %*% fit$coef[fourier_names])
  seasonal <- seasonal - mean(seasonal)
  seasonal_parts[[channel_name]] <- seasonal
  message(sprintf("Pooled source %s fourier K=%d", channel_name, K))
}

pooled_matrix <- do.call(rbind, seasonal_parts)
pooled_log_index <- colMeans(pooled_matrix)
pooled_seasonal <- data.frame(
  p = 0:51,
  log_index = as.numeric(pooled_log_index),
  stringsAsFactors = FALSE
)
write_csv(pooled_seasonal, "outputs/tables/pooled_seasonal.csv")

simulate_short_channel <- function(channel_name, planned) {
  history <- weekly %>%
    filter(.data$channel == .env$channel_name) %>%
    arrange(week)
  p_hist <- (history$week - 1L) %% 52L
  z <- log(history$signups) - pooled_log_index[p_hist + 1L]
  fit <- tryCatch(
    forecast::Arima(z, order = c(1, 0, 0), include.mean = TRUE),
    error = function(e) e
  )
  if (inherits(fit, "error")) {
    stop(sprintf(
      "Short-history ARIMA failed for %s: %s",
      channel_name, conditionMessage(fit)
    ), call. = FALSE)
  }
  if (!("intercept" %in% names(fit$coef))) {
    stop(sprintf("Short-history fit for %s has no intercept.", channel_name),
         call. = FALSE)
  }
  se_intercept <- sqrt(as.numeric(fit$var.coef["intercept", "intercept"]))

  weekly_paths <- matrix(NA_real_, nrow = n_paths, ncol = horizon)
  for (i in seq_len(n_paths)) {
    sim <- as.numeric(stats::simulate(fit, nsim = horizon, future = TRUE))
    intercept_draw <- rnorm(1, mean = 0, sd = se_intercept)
    log_path <- sim + intercept_draw + pooled_log_index[future_p + 1L]
    weekly_paths[i, ] <- exp(log_path)
  }
  totals <- rowSums(weekly_paths)

  list(
    method = "short_history",
    K = NA_integer_,
    arima_order = order_string(fit),
    weekly_paths = weekly_paths,
    totals = totals,
    widen = FALSE
  )
}

path_rows <- list()
weekly_rows <- list()
summary_rows <- list()

all_channels <- sort(unique(weekly$channel))
for (channel_name in all_channels) {
  planned <- planned_spend %>%
    filter(.data$channel == .env$channel_name) %>%
    pull(planned_weekly_spend)
  last52 <- planned_spend %>%
    filter(.data$channel == .env$channel_name) %>%
    pull(last_52w_signups)

  message(sprintf("Forecasting %s", channel_name))
  if (channel_name %in% long_channels) {
    meta <- chosen %>% filter(.data$channel == .env$channel_name)
    if (nrow(meta) != 1) {
      stop(sprintf("Need exactly one chosen variant for %s", channel_name),
           call. = FALSE)
    }
    result <- simulate_long_channel(
      channel_name,
      meta$variant[[1]],
      isTRUE(meta$widen[[1]]),
      planned
    )
  } else {
    result <- simulate_short_channel(channel_name, planned)
  }

  path_rows[[length(path_rows) + 1]] <- data.frame(
    channel = channel_name,
    draw = seq_len(n_paths),
    total_signups = as.numeric(result$totals),
    stringsAsFactors = FALSE
  )

  for (j in seq_len(horizon)) {
    col <- result$weekly_paths[, j]
    weekly_rows[[length(weekly_rows) + 1]] <- data.frame(
      channel = channel_name,
      week = future_weeks[[j]],
      week_start = future_starts[[j]],
      p5 = as.numeric(stats::quantile(col, 0.05, names = FALSE, type = 7)),
      p10 = as.numeric(stats::quantile(col, 0.10, names = FALSE, type = 7)),
      median = as.numeric(stats::quantile(col, 0.50, names = FALSE, type = 7)),
      p90 = as.numeric(stats::quantile(col, 0.90, names = FALSE, type = 7)),
      p95 = as.numeric(stats::quantile(col, 0.95, names = FALSE, type = 7)),
      stringsAsFactors = FALSE
    )
  }

  summary_rows[[length(summary_rows) + 1]] <- data.frame(
    channel = channel_name,
    method = result$method,
    K = result$K,
    arima_order = result$arima_order,
    planned_weekly_spend = planned,
    last_52w_signups = last52,
    total_p5 = as.numeric(stats::quantile(result$totals, 0.05, names = FALSE, type = 7)),
    total_median = as.numeric(stats::quantile(result$totals, 0.50, names = FALSE, type = 7)),
    total_p95 = as.numeric(stats::quantile(result$totals, 0.95, names = FALSE, type = 7)),
    widen = result$widen,
    stringsAsFactors = FALSE
  )
}

paths <- bind_rows(path_rows)
forecast_weekly <- bind_rows(weekly_rows)
forecast_summary <- bind_rows(summary_rows) %>%
  arrange(channel)

write_csv(forecast_weekly, "outputs/tables/forecast_weekly.csv")
write_csv(forecast_summary, "outputs/tables/forecast_summary.csv")

arrow_ok <- requireNamespace("arrow", quietly = TRUE)
if (arrow_ok) {
  arrow::write_parquet(paths, "outputs/tables/forecast_paths.parquet")
  message("Wrote outputs/tables/forecast_paths.parquet")
} else {
  write_csv(paths, "outputs/tables/forecast_paths.csv")
  message("arrow not installed; wrote outputs/tables/forecast_paths.csv")
  convert <- system2(
    "uv",
    c("run", "python", "-m", "acr.io"),
    stdout = TRUE,
    stderr = TRUE
  )
  status <- attr(convert, "status")
  if (!is.null(status) && status != 0) {
    cat(paste(convert, collapse = "\n"), "\n")
    stop("Failed to convert forecast_paths.csv to parquet.", call. = FALSE)
  }
  message(paste(convert, collapse = "\n"))
  if (file.exists("outputs/tables/forecast_paths.parquet")) {
    unlink("outputs/tables/forecast_paths.csv")
  }
}

message("Wrote final forecast tables to outputs/tables")
