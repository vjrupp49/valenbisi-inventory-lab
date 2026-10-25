# Figures for docs/service_level_findings.md. Reads the CSVs written by src/analysis/service_level.py
# (reports/_cache) and writes PNGs to docs/figures/. Needs: ggplot2, dplyr, scales.
#   Rscript analysis/plot_service_level.R
suppressMessages({library(ggplot2); library(dplyr); library(scales)})

cache <- file.path("reports", "_cache")
out   <- file.path("docs", "figures")
dir.create(out, showWarnings = FALSE, recursive = TRUE)
subtitle <- "Frozen dataset data-freeze-2026-10-24, 15 complete days. Stockouts are lower bounds (short ones can be missed)."

# 1. City-wide stockout and blockout rate by Madrid hour, weekday vs weekend (median across days, ribbon = min to max)
h <- read.csv(file.path(cache, "hourly_summary.csv")) %>% filter(day_type %in% c("weekday", "weekend"))
long <- bind_rows(
  h %>% transmute(day_type, hour_of_day, measure = "Stockout (no bikes)", med = stockout_median, lo = stockout_min, hi = stockout_max),
  h %>% transmute(day_type, hour_of_day, measure = "Blockout (no free docks)", med = blockout_median, lo = blockout_min, hi = blockout_max)
)
p1 <- ggplot(long, aes(hour_of_day, med, colour = day_type, fill = day_type)) +
  geom_ribbon(aes(ymin = lo, ymax = hi), alpha = 0.15, colour = NA) +
  geom_line(linewidth = 0.9) +
  facet_wrap(~measure) +
  scale_y_continuous(labels = percent) +
  scale_x_continuous(breaks = seq(0, 23, 3)) +
  labs(x = "Hour of day (Madrid time)", y = "Share of station-snapshots", colour = NULL, fill = NULL,
       title = "Empty and full stations by hour of day",
       subtitle = paste0(subtitle, "\nLine = median across days; ribbon = lowest to highest day. 9 weekdays, 5 weekend days.")) +
  theme_minimal(base_size = 11) + theme(legend.position = "bottom", plot.subtitle = element_text(size = 8))
ggsave(file.path(out, "hourly_service_level.png"), p1, width = 9, height = 4.6, dpi = 130)

# 2. How unevenly stations are affected
s <- read.csv(file.path(cache, "station_summary.csv"))
s2 <- bind_rows(s %>% transmute(measure = "Stockout rate", rate = stockout_rate),
                s %>% transmute(measure = "Blockout rate", rate = blockout_rate))
p2 <- ggplot(s2, aes(rate)) +
  geom_histogram(binwidth = 0.025, boundary = 0, fill = "#3b6ea5", colour = "white") +
  facet_wrap(~measure) +
  scale_x_continuous(labels = percent) +
  labs(x = "Share of the station's snapshots (headline rate)", y = "Number of stations",
       title = "Most stations are rarely empty or full; a few are often",
       subtitle = subtitle) +
  theme_minimal(base_size = 11) + theme(plot.subtitle = element_text(size = 8))
ggsave(file.path(out, "station_distribution.png"), p2, width = 9, height = 4, dpi = 130)

# 3. Stockout heatmap for the 40 stations with the highest overall stockout rate
top <- s %>% arrange(desc(stockout_rate)) %>% slice_head(n = 40) %>% pull(station_id)
cells <- read.csv(file.path(cache, "station_hour_cells.csv")) %>% filter(station_id %in% top)
cells$station <- factor(cells$station_id, levels = rev(top))
p3 <- ggplot(cells, aes(hour_of_day, station, fill = stockout_rate)) +
  geom_tile() +
  scale_fill_viridis_c(labels = percent, na.value = "grey90") +
  scale_x_continuous(breaks = seq(0, 23, 3)) +
  scale_y_discrete(drop = FALSE) +
  labs(x = "Hour of day (Madrid time)", y = "Station id (highest overall stockout rate at top)", fill = "Stockout rate",
       title = "When the 40 most often empty stations run out",
       subtitle = paste0(subtitle, "\nBlank = fewer than 80 eligible snapshots (often because the station's count was stuck and excluded).")) +
  theme_minimal(base_size = 9) + theme(plot.subtitle = element_text(size = 7))
ggsave(file.path(out, "stockout_heatmap_top40.png"), p3, width = 8, height = 7, dpi = 130)
cat("figures written to", out, "\n")
