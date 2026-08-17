# Difference-in-differences on the paid_social spend change.
# Run from the repo root: Rscript r/did.R

suppressPackageStartupMessages({
  library(fixest)
  library(dplyr)
  library(readr)
  library(jsonlite)
})

options(warn = 1)

if (!file.exists("data/weekly_channel.csv")) {
  stop("Run this from the repo root: Rscript r/did.R", call. = FALSE)
}

dir.create("outputs/tables", recursive = TRUE, showWarnings = FALSE)

weekly <- read_csv("data/weekly_channel.csv", show_col_types = FALSE)
costs <- read_csv("data/channel_costs.csv", show_col_types = FALSE)

controls <- c("paid_search", "affiliate", "referral")
panel <- weekly %>%
  filter(.data$channel %in% c("paid_social", controls)) %>%
  mutate(treated = .data$channel == "paid_social") %>%
  arrange(channel, week)

est <- function(weeks_used, post_weeks) {
  data <- panel %>%
    filter(.data$week %in% weeks_used) %>%
    mutate(
      post = .data$week %in% post_weeks,
      tp = .data$treated & .data$post
    )

  fit <- feols(
    log(signups) ~ tp | channel + week,
    data = data,
    panel.id = ~ channel + week,
    vcov = "NW"
  )

  coef_table <- coeftable(fit)
  row_name <- rownames(coef_table)[[1]]
  estimate <- as.numeric(coef_table[row_name, "Estimate"])
  se <- as.numeric(coef_table[row_name, "Std. Error"])
  p_value <- as.numeric(coef_table[row_name, "Pr(>|t|)"])
  ci_low <- estimate - 1.96 * se
  ci_high <- estimate + 1.96 * se

  list(
    estimate = estimate,
    se = se,
    ci_low = ci_low,
    ci_high = ci_high,
    p_value = p_value,
    n_obs = as.integer(nobs(fit))
  )
}

main <- est(53:90, 79:90)
placebo <- est(53:77, 66:77)
reversal <- est(c(53:78, 91:102), 91:102)

results <- bind_rows(
  data.frame(
    test = "main",
    estimate = main$estimate,
    se = main$se,
    ci_low = main$ci_low,
    ci_high = main$ci_high,
    p_value = main$p_value,
    n_obs = main$n_obs,
    stringsAsFactors = FALSE
  ),
  data.frame(
    test = "placebo",
    estimate = placebo$estimate,
    se = placebo$se,
    ci_low = placebo$ci_low,
    ci_high = placebo$ci_high,
    p_value = placebo$p_value,
    n_obs = placebo$n_obs,
    stringsAsFactors = FALSE
  ),
  data.frame(
    test = "reversal",
    estimate = reversal$estimate,
    se = reversal$se,
    ci_low = reversal$ci_low,
    ci_high = reversal$ci_high,
    p_value = reversal$p_value,
    n_obs = reversal$n_obs,
    stringsAsFactors = FALSE
  )
) %>%
  mutate(ci_covers_zero = .data$ci_low <= 0 & .data$ci_high >= 0)

social <- weekly %>%
  filter(.data$channel == "paid_social") %>%
  arrange(week)
social_costs <- costs %>%
  filter(.data$channel == "paid_social")
variable_cost <- social_costs$variable_cost_per_signup[[1]]
fixed_monthly_cost <- social_costs$fixed_monthly_cost[[1]]

pre <- social %>% filter(.data$week >= 53, .data$week <= 78)
post <- social %>% filter(.data$week >= 79, .data$week <= 90)

mean_pre_spend <- mean(pre$spend)
mean_post_spend <- mean(post$spend)
mean_pre_signups <- mean(pre$signups)
mean_post_signups <- mean(post$signups)

multiplier <- exp(main$estimate)
effect_pct <- (multiplier - 1) * 100
spend_ratio <- mean_post_spend / mean_pre_spend
extra_signups_per_week <- mean_post_signups * (1 - 1 / multiplier)
extra_spend_per_week <- mean_post_spend - mean_pre_spend
cost_per_extra_signup <- (
  extra_spend_per_week + variable_cost * extra_signups_per_week
) / extra_signups_per_week
avg_cost_per_signup_pre <- (
  mean_pre_spend +
    variable_cost * mean_pre_signups +
    fixed_monthly_cost * 12 / 52
) / mean_pre_signups
log_spend_ratio <- log(spend_ratio)
elasticity <- main$estimate / log_spend_ratio
elasticity_ci_low <- main$ci_low / log_spend_ratio
elasticity_ci_high <- main$ci_high / log_spend_ratio

translation <- data.frame(
  estimate = main$estimate,
  se = main$se,
  ci_low = main$ci_low,
  ci_high = main$ci_high,
  multiplier = multiplier,
  effect_pct = effect_pct,
  mean_pre_spend = mean_pre_spend,
  mean_post_spend = mean_post_spend,
  mean_pre_signups = mean_pre_signups,
  mean_post_signups = mean_post_signups,
  spend_ratio = spend_ratio,
  extra_signups_per_week = extra_signups_per_week,
  extra_spend_per_week = extra_spend_per_week,
  variable_cost_per_signup = variable_cost,
  fixed_monthly_cost = fixed_monthly_cost,
  cost_per_extra_signup = cost_per_extra_signup,
  avg_cost_per_signup_pre = avg_cost_per_signup_pre,
  elasticity = elasticity,
  elasticity_ci_low = elasticity_ci_low,
  elasticity_ci_high = elasticity_ci_high,
  stringsAsFactors = FALSE
)

weekly_gap <- panel %>%
  filter(.data$week >= 53, .data$week <= 102) %>%
  group_by(week, week_start) %>%
  summarise(
    treated_log = log(signups[.data$treated][[1]]),
    control_mean_log = mean(log(signups[!.data$treated])),
    .groups = "drop"
  ) %>%
  mutate(gap = .data$treated_log - .data$control_mean_log)

pre_gap_mean <- weekly_gap %>%
  filter(.data$week >= 53, .data$week <= 78) %>%
  summarise(mean_gap = mean(.data$gap)) %>%
  pull(mean_gap)

weekly_gap <- weekly_gap %>%
  mutate(gap_vs_pre = .data$gap - pre_gap_mean) %>%
  select(week, week_start, treated_log, control_mean_log, gap, gap_vs_pre)

write_csv(results, "outputs/tables/did_results.csv")
write_csv(translation, "outputs/tables/did_translation.csv")
write_csv(weekly_gap, "outputs/tables/did_weekly.csv")

session_path <- "outputs/tables/r_session.txt"
fixest_line <- sprintf(
  "fixest version used for DiD: %s",
  as.character(packageVersion("fixest"))
)
if (file.exists(session_path)) {
  existing <- readLines(session_path, warn = FALSE)
  writeLines(c(existing, "", fixest_line), session_path)
} else {
  writeLines(fixest_line, session_path)
}

message("Wrote DiD tables to outputs/tables")
print(results)
print(translation)
