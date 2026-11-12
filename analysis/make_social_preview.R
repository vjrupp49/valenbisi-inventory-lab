# Social preview card for the GitHub repository (1280 x 640). Numbers are read from the generated results files.
#   Rscript analysis/make_social_preview.R   ->  docs/figures/social_preview.png
suppressMessages({library(ggplot2); library(dplyr); library(scales)})

h <- read.csv(file.path("reports", "_cache", "hourly_summary.csv")) %>% filter(day_type == "weekday")
f1 <- readLines(file.path("docs", "forecast_results.md"), encoding = "UTF-8")
auc <- as.numeric(strsplit(grep("^\\| gbm \\|", f1, value = TRUE)[1], "|", fixed = TRUE)[[1]][7])
s3 <- readLines(file.path("docs", "service_level_results.md"), encoding = "UTF-8")
row <- grep("^\\| 0\\.[0-9]+ \\| 0\\.[0-9]+ \\| 0\\.[0-9]+ \\| 0\\.[0-9]+", s3, value = TRUE)[1]
stockout <- as.numeric(trimws(strsplit(row, "|", fixed = TRUE)[[1]][3]))
s1 <- grep("^[|] (weekday|weekend|holiday) [|]", s3, value = TRUE)
n_days <- sum(as.integer(sapply(strsplit(s1, "|", fixed = TRUE), function(x) trimws(x[3]))))

navy <- "#14213d"; blue <- "#3b6ea5"; light <- "#f4f6fa"
chart <- ggplot(h, aes(hour_of_day, stockout_median)) +
  geom_area(fill = blue, alpha = 0.25) + geom_line(colour = blue, linewidth = 1.6) +
  scale_y_continuous(labels = percent, limits = c(0, 0.22)) +
  scale_x_continuous(breaks = c(0, 6, 12, 18, 23)) +
  labs(x = "Hour of day (Madrid)", y = NULL, title = "Share of stations empty, weekdays") +
  theme_minimal(base_size = 16) +
  theme(plot.title = element_text(colour = navy, face = "bold", size = 15), panel.grid.minor = element_blank(),
        plot.background = element_rect(fill = light, colour = NA), panel.background = element_rect(fill = light, colour = NA))

png(file.path("docs", "figures", "social_preview.png"), width = 1280, height = 640, res = 100)
grid::grid.newpage()
grid::grid.rect(gp = grid::gpar(fill = light, col = NA))
grid::grid.rect(x = 0, y = 0.5, width = 0.012, height = 1, just = "left", gp = grid::gpar(fill = blue, col = NA))
grid::grid.text("Valenbisi Inventory Lab", x = 0.05, y = 0.86, just = "left", gp = grid::gpar(fontsize = 32, fontface = "bold", col = navy))
grid::grid.text("Valencia's bike stations as inventory:\nforecasting stockouts and testing rebalancing", x = 0.05, y = 0.72, just = "left",
                gp = grid::gpar(fontsize = 19, col = "#444444", lineheight = 1.2))
stat <- function(y, big, small) {
  grid::grid.text(big, x = 0.05, y = y, just = c("left", "bottom"), gp = grid::gpar(fontsize = 34, fontface = "bold", col = blue))
  grid::grid.text(small, x = 0.05, y = y - 0.015, just = c("left", "top"), gp = grid::gpar(fontsize = 15, col = "#444444"))
}
stat(0.45, sprintf("%.0f%%", 100 * stockout), "of station-time spent empty")
stat(0.29, sprintf("AUC %.2f", auc), "forecasting an empty station 1 hour ahead")
stat(0.13, sprintf("%d days", n_days), "of live data, every 10 minutes")
print(chart, vp = grid::viewport(x = 0.76, y = 0.50, width = 0.44, height = 0.72))
grid::grid.text("DuckDB + dbt  |  Python  |  R  |  GitHub Actions", x = 0.05, y = 0.025, just = c("left", "bottom"), gp = grid::gpar(fontsize = 12, col = "#777777"))
invisible(dev.off())
cat("wrote docs/figures/social_preview.png\n")
