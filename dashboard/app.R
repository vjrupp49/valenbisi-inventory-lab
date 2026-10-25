# Valenbisi Inventory Lab: dashboard skeleton (Shiny).
# Reads CSV exports of the dbt marts (python src/export_marts.py --db ... --out dashboard/data).
# Needs only: shiny, ggplot2, dplyr. Run from the repo root:  shiny::runApp("dashboard")
#
# Honesty rules baked in: a banner states how many days of data exist and whether they are SYNTHETIC;
# provisional segments are labelled; nothing here is hard-coded.

library(shiny)
library(ggplot2)
library(dplyr)

data_dir <- Sys.getenv("VALENBISI_DASH_DATA", unset = file.path("dashboard", "data"))
if (!dir.exists(data_dir)) data_dir <- "data"   # when launched from inside dashboard/

read_mart <- function(name) {
  path <- file.path(data_dir, paste0(name, ".csv"))
  if (!file.exists(path)) return(NULL)
  read.csv(path, stringsAsFactors = FALSE)
}

banner_text <- function(meta) {
  if (is.null(meta)) return("No data exported yet. Run src/export_marts.py.")
  prefix <- if (isTRUE(as.logical(meta$synthetic))) "SYNTHETIC DATA - NOT REAL. " else ""
  paste0(prefix, meta$n_snapshots, " station-snapshots over ", meta$n_days, " day(s), ",
         meta$first_ts, " to ", meta$last_ts, ". ",
         if (meta$n_days < 14) "Fewer than 14 days: all rates and segments are provisional." else "")
}

ui <- fluidPage(
  titlePanel("Valenbisi Inventory Lab"),
  uiOutput("banner"),
  tabsetPanel(
    tabPanel("Service level",
             sidebarLayout(
               sidebarPanel(
                 selectInput("measure", "Measure",
                             c("Stockout rate (headline)" = "stockout_rate",
                               "Stockout rate (strict: excludes counts flat 6 h+)" = "stockout_rate_strict",
                               "Stockout rate (raw)" = "stockout_rate_raw",
                               "Blockout rate (headline)" = "blockout_rate",
                               "Blockout rate (strict)" = "blockout_rate_strict",
                               "Blockout rate (raw)" = "blockout_rate_raw")),
                 numericInput("min_rows", "Min. eligible snapshots per cell", 1, min = 0),
                 helpText("Headline = installed and renting (or returning) stations, minus readings whose bike count has not changed for 12 h or more. Stockouts shorter than the 10-minute snapshot spacing can be missed, so rates are lower bounds. Cells with too little data are blank.")
               ),
               mainPanel(plotOutput("heatmap", height = "600px"))
             )),
    tabPanel("Segmentation", tableOutput("seg"),
             helpText("ABC by inferred activity, XYZ by day-to-day variability. Activity is a lower bound on trips.")),
    tabPanel("Collection health", plotOutput("health"))
  )
)

server <- function(input, output, session) {
  kpi  <- read_mart("kpi_service_level")
  seg  <- read_mart("seg_station_abc_xyz")
  hlth <- read_mart("fct_run_health")
  meta <- read_mart("meta")

  output$banner <- renderUI(tags$div(style = "padding:8px;background:#fff3cd;margin-bottom:8px;",
                                     banner_text(meta)))

  output$heatmap <- renderPlot({
    req(kpi)
    elig <- if (grepl("^blockout", input$measure)) "n_blockout_eligible" else "n_stockout_eligible"
    d <- kpi %>% filter(.data[[elig]] >= input$min_rows)
    ggplot(d, aes(x = hour_of_day, y = reorder(factor(station_id), n_installed_rows), fill = .data[[input$measure]])) +
      geom_tile() +
      scale_fill_viridis_c(na.value = "grey90", labels = scales::percent) +
      labs(x = "Hour of day (Valencia time)", y = "Station", fill = NULL) +
      theme_minimal()
  })

  output$seg <- renderTable({
    req(seg)
    seg %>% arrange(desc(mean_daily_activity)) %>%
      select(station_id, abc_class, xyz_class, n_days_used, mean_daily_activity, cv_daily_activity, is_provisional)
  })

  output$health <- renderPlot({
    req(hlth)
    hlth$snapshot_ts <- as.POSIXct(hlth$snapshot_ts, tz = "UTC")
    ggplot(hlth, aes(snapshot_ts, gap_minutes)) +
      geom_point(alpha = .5) +
      labs(x = NULL, y = "Minutes since previous run") +
      theme_minimal()
  })
}

shinyApp(ui, server)
