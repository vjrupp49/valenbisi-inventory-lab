# Figures for the forecast and simulation findings. Reads the tables the analysis scripts wrote into docs/*_results*.md
# (nothing is typed in by hand) and writes PNGs to docs/figures/.   Rscript analysis/plot_model_results.R
# Needs: ggplot2, dplyr, scales.
suppressMessages({library(ggplot2); library(dplyr); library(scales)})

md_table <- function(file, id) {
  x <- readLines(file.path("docs", file), warn = FALSE, encoding = "UTF-8")
  h <- grep(paste0("^#{2,3} ", id, "( |[.]|$)"), x)[1]
  rest <- x[(h + 1):length(x)]
  tbl <- rest[which(startsWith(rest, "|"))[1]:length(rest)]
  end <- which(!startsWith(tbl, "|"))[1]
  if (!is.na(end)) tbl <- tbl[seq_len(end - 1)]
  cells <- function(l) trimws(strsplit(sub("^\\|", "", sub("\\|$", "", l)), "|", fixed = TRUE)[[1]])
  df <- as.data.frame(do.call(rbind, lapply(tbl[-c(1, 2)], cells)), stringsAsFactors = FALSE)
  names(df) <- cells(tbl[1])
  df[] <- lapply(df, function(col) { n <- suppressWarnings(as.numeric(col)); if (all(is.na(n) == (col == ""))) n else col })
  df
}
out <- file.path("docs", "figures"); dir.create(out, showWarnings = FALSE, recursive = TRUE)

# 1. Forecast accuracy at 1, 3 and 6 hours, best (GBM) against simple baselines
files <- c("1 hour ahead" = "forecast_results.md", "3 hours ahead" = "forecast_results_h3.md", "6 hours ahead" = "forecast_results_h6.md")
f <- bind_rows(lapply(names(files), function(h) mutate(md_table(files[[h]], "F1"), horizon = h)))
f$horizon <- factor(f$horizon, names(files))
n_test <- sub(".*, ([0-9]+) test days.*", "\\1", grep("test days", readLines("docs/forecast_results.md", encoding = "UTF-8"), value = TRUE)[1])
f$model <- factor(f$model, c("gbm", "station_state", "persistence", "hour_of_week", "station_mean"),
                  c("Gradient boosting", "Station state", "Persistence", "Hour-of-week average", "Station average"))
p1 <- ggplot(f, aes(model, brier, fill = model == "Gradient boosting")) +
  geom_col(width = 0.7, show.legend = FALSE) +
  geom_errorbar(aes(ymin = brier_lo, ymax = brier_hi), width = 0.25) +
  scale_fill_manual(values = c("grey70", "#3b6ea5")) +
  facet_wrap(~horizon) + coord_flip() +
  labs(x = NULL, y = "Brier score (lower is better); bars = 95% interval from resampling test days",
       title = "Forecasting an empty station: a clear edge at 1 hour that fades by 6",
       subtitle = paste0("Rolling-origin backtest on ", n_test, " test days, frozen dataset data-freeze-2026-11-11. Early result from about a month of autumn data.")) +
  theme_minimal(base_size = 11) + theme(plot.subtitle = element_text(size = 8))
ggsave(file.path(out, "forecast_brier.png"), p1, width = 10, height = 4.2, dpi = 130)

# 2. Simulation: does forecasting beat just reacting to current counts?
s <- md_table("simulation_results.md", "E3b")
lab <- c(static = "Fixed route", forecast_1h = "Forecast 1 h", forecast_3h = "Forecast 3 h",
         forecast_6h = "Forecast 6 h", oracle_3h = "Perfect forecast 3 h")
s$policy <- factor(lab[s$policy], rev(lab))
p2 <- ggplot(s, aes(policy, extra_lost_pickups_avoided_per_day_vs_reactive)) +
  geom_hline(yintercept = 0, colour = "grey40") +
  geom_pointrange(aes(ymin = lo95, ymax = hi95), colour = "#3b6ea5") +
  coord_flip() +
  labs(x = NULL, y = "Lost pickups avoided per day, compared with reacting to current bike counts (positive = better)",
       title = "Simulation: forecasting adds a little; a 6-hour forecast is worse than reacting",
       subtitle = "Replica of the network under stated assumptions; compares strategies, not real savings. Bars = 95% CI for the mean of 100 runs.") +
  theme_minimal(base_size = 11) + theme(plot.subtitle = element_text(size = 8))
ggsave(file.path(out, "simulation_vs_reactive.png"), p2, width = 10, height = 3.8, dpi = 130)
cat("figures written to", out, "\n")
