# Valenbisi Inventory Lab: dashboard (Shiny, runs locally).
#
# Data sources (nothing is typed in by hand):
#   * dashboard/data/*.csv   exported dbt marts   (python src/export_marts.py --db ... --out dashboard/data)
#   * docs/*_results*.md     tables written by the analysis scripts (forecast, segmentation, simulation);
#                            this app parses the tables out of those files, so the numbers shown are exactly
#                            the ones the scripts produced.
# Needs: shiny, ggplot2, dplyr, scales.   Run from the repo root:  shiny::runApp("dashboard")
#
# Honesty rules: a banner states how many days of data exist and whether they are SYNTHETIC; every tab
# repeats its main limitation; the simulation tab says it compares strategies and does not measure savings.

library(shiny)
library(ggplot2)
library(dplyr)

app_dir  <- if (dir.exists("dashboard")) "dashboard" else "."
data_dir <- Sys.getenv("VALENBISI_DASH_DATA", unset = file.path(app_dir, "data"))
docs_dir <- Sys.getenv("VALENBISI_DOCS_DIR", unset = file.path(app_dir, "..", "docs"))

read_mart <- function(name) {
  path <- file.path(data_dir, paste0(name, ".csv"))
  if (!file.exists(path)) return(NULL)
  read.csv(path, stringsAsFactors = FALSE)
}

# ---- read one table out of an auto-generated results file --------------------------------------
# Finds the heading that starts with `id` (e.g. "E3." or "F1.") and returns the first pipe table after it.
md_table <- function(file, id) {
  path <- file.path(docs_dir, file)
  if (!file.exists(path)) return(NULL)
  x <- readLines(path, warn = FALSE, encoding = "UTF-8")
  h <- grep(paste0("^#{2,3} ", id, "( |[.]|$)"), x)
  if (!length(h)) return(NULL)
  rest <- x[(h[1] + 1):length(x)]
  start <- which(startsWith(rest, "|"))[1]
  if (is.na(start)) return(NULL)
  tbl <- rest[start:length(rest)]
  end <- which(!startsWith(tbl, "|"))[1]
  if (!is.na(end)) tbl <- tbl[seq_len(end - 1)]
  cells <- function(l) trimws(strsplit(sub("^\\|", "", sub("\\|$", "", l)), "|", fixed = TRUE)[[1]])
  head <- cells(tbl[1])
  rows <- lapply(tbl[-c(1, 2)], cells)
  df <- as.data.frame(do.call(rbind, rows), stringsAsFactors = FALSE)
  names(df) <- head
  df[] <- lapply(df, function(col) { n <- suppressWarnings(as.numeric(col)); if (all(is.na(n) == (col == "" | is.na(col)))) n else col })
  df
}

banner_text <- function(meta) {
  if (is.null(meta)) return("No data exported yet. Run src/export_marts.py.")
  prefix <- if (isTRUE(as.logical(meta$synthetic))) "SYNTHETIC DATA - NOT REAL. " else ""
  paste0(prefix, meta$n_snapshots, " station-snapshots over ", meta$n_days, " calendar day(s) (",
         substr(meta$first_ts, 1, 10), " to ", substr(meta$last_ts, 1, 10), "). ",
         if (meta$n_days < 90) "Under 90 days, one season: results are early looks, not seasonal conclusions." else "")
}

note <- function(...) tags$p(style = "color:#555;max-width:900px;", ...)
policy_labels <- c(static = "Static route", reactive = "Reactive", forecast_1h = "Forecast 1 h",
                   forecast_3h = "Forecast 3 h", forecast_6h = "Forecast 6 h", oracle_3h = "Perfect forecast 3 h")

ui <- fluidPage(
  titlePanel("Valenbisi Inventory Lab"),
  uiOutput("banner"),
  tabsetPanel(
    tabPanel("Overview", br(),
             note("Valencia's bike-share stations treated as inventory nodes: bikes are stock, an empty station is a stockout, ",
                  "a full station is a blockout, and the operator's trucks are replenishment. Data: the live Valenbisi feed (JCDecaux Open Licence), ",
                  "collected every 10 minutes."),
             uiOutput("overview")),
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
               mainPanel(
                 h4("Network average by hour of day"), plotOutput("hourly", height = "260px"),
                 h4("Every station by hour of day"), plotOutput("heatmap", height = "600px"))
             )),
    tabPanel("Segmentation", br(),
             note("ABC by inferred activity (changes in bike counts, a lower bound on trips), XYZ by day-to-day variability."),
             fluidRow(column(5, plotOutput("seg_counts", height = "260px")), column(7, tableOutput("seg_summary"))),
             h4("Stations"), tableOutput("seg")),
    tabPanel("Forecast", br(),
             note("Question: will this station hit zero bikes within the next H hours? Tested by rolling-origin backtest ",
                  "(train on the past, predict the next day, repeat). Lower Brier score is better. Edge over simple baselines is clear at 1 hour and fades by 3 to 6 hours."),
             plotOutput("fc_brier", height = "320px"),
             tableOutput("fc_table"),
             h4("Is the 1-hour forecast calibrated?"),
             note("If the model says 30%, about 30% of those hours should have a stockout. Points near the diagonal mean yes."),
             plotOutput("fc_calib", height = "340px")),
    tabPanel("Simulation", br(),
             tags$div(style = "padding:8px;background:#fde8e8;max-width:900px;",
                      tags$b("A what-if machine, not a measurement. "),
                      "It compares rebalancing strategies on a replica of the network under stated assumptions. ",
                      "The replica understates empty stations, so only differences between strategies carry information, and they carry the assumptions."),
             h4("Lost pickups avoided per day versus no rebalancing"), plotOutput("sim_avoided", height = "320px"),
             h4("Does forecasting add anything beyond reacting to current counts?"), plotOutput("sim_vs_reactive", height = "300px"),
             h4("Sensitivity: budget and demand"),
             note("Forecast edge over reactive (lost pickups a day) by transfers per round. Bars show 95% confidence intervals for the average."),
             selectInput("sim_scale", "Assumed demand (1 = counted pickups)", c(1, 1.5, 2), selected = 1),
             plotOutput("sim_grid", height = "300px"),
             h4("Is the replica realistic?"), tableOutput("sim_valid")),
    tabPanel("Collection health", br(),
             note("Gap between consecutive collector runs. The feed provider's own outages and the scheduler's drift show up here."),
             plotOutput("health"))
  )
)

server <- function(input, output, session) {
  kpi  <- read_mart("kpi_service_level")
  seg  <- read_mart("seg_station_abc_xyz")
  hlth <- read_mart("fct_run_health")
  meta <- read_mart("meta")

  output$banner <- renderUI(tags$div(style = "padding:8px;background:#fff3cd;margin-bottom:8px;", banner_text(meta)))

  output$overview <- renderUI({
    sim <- md_table("simulation_results.md", "E3b")
    e3  <- md_table("simulation_results.md", "E3")
    fc3 <- md_table("forecast_results_h3.md", "F1")
    items <- list()
    if (!is.null(kpi)) {
      w <- kpi$n_stockout_eligible
      share <- weighted.mean(kpi$stockout_rate, w, na.rm = TRUE)
      items <- c(items, list(tags$li(sprintf(
        "Headline stockout rate across the network: %.1f%% of eligible station-time (see Service level); the pattern repeats daily and differs a lot between stations.", 100 * share))))
    }
    items <- c(items, list(
      tags$li("A flat bike count is not proof the data is fresh: a station's count can stay frozen for hours. Those readings are excluded from headline rates.")))
    if (!is.null(e3) && !is.null(sim)) {
      r <- sim[sim$policy == "forecast_3h", ]
      items <- c(items, list(tags$li(sprintf(
        "In the simulation, rebalancing by a 3-hour forecast beats reactive rebalancing by about %.0f lost pickups a day (95%% CI %.0f to %.0f), a small effect; the rebalancing budget matters more.",
        r$extra_lost_pickups_avoided_per_day_vs_reactive, r$lo95, r$hi95))))
    }
    tagList(h4("What the data says so far"), tags$ul(items),
            h4("What it cannot say"),
            tags$ul(tags$li("No trip data: activity is inferred from changes in counts, a lower bound."),
                    tags$li("No truck data: the real rebalancing effort is unknown."),
                    tags$li("One window in one season: no weather, holiday or seasonal conclusions yet.")),
            note("Data: JCDecaux Open Licence; weather: Open-Meteo (CC BY 4.0). Full write-ups are in the docs folder of the repository."))
  })

  output$hourly <- renderPlot({
    req(kpi)
    elig <- if (grepl("^blockout", input$measure)) "n_blockout_eligible" else "n_stockout_eligible"
    d <- kpi %>% filter(.data[[elig]] > 0) %>% group_by(hour_of_day) %>%
      summarise(rate = weighted.mean(.data[[input$measure]], .data[[elig]], na.rm = TRUE), .groups = "drop")
    ggplot(d, aes(hour_of_day, rate)) + geom_line(linewidth = 1) + geom_point() +
      scale_y_continuous(labels = scales::percent, limits = c(0, NA)) +
      labs(x = "Hour of day (Valencia time)", y = "Share of station-time") + theme_minimal()
  })

  output$heatmap <- renderPlot({
    req(kpi)
    elig <- if (grepl("^blockout", input$measure)) "n_blockout_eligible" else "n_stockout_eligible"
    d <- kpi %>% filter(.data[[elig]] >= input$min_rows)
    ggplot(d, aes(x = hour_of_day, y = reorder(factor(station_id), n_installed_rows), fill = .data[[input$measure]])) +
      geom_tile() +
      scale_fill_viridis_c(na.value = "grey90", labels = scales::percent) +
      scale_y_discrete(drop = FALSE) +
      labs(x = "Hour of day (Valencia time)", y = "Station", fill = NULL) +
      theme_minimal() + theme(axis.text.y = element_blank())
  })

  output$seg_counts <- renderPlot({
    req(seg)
    ggplot(seg, aes(abc_class, fill = xyz_class)) + geom_bar() +
      labs(x = "ABC class (activity)", y = "Stations", fill = "XYZ") + theme_minimal()
  })
  output$seg_summary <- renderTable({
    req(seg)
    seg %>% group_by(abc_class, xyz_class) %>%
      summarise(stations = n(), mean_daily_activity = round(mean(mean_daily_activity), 1), .groups = "drop")
  })
  output$seg <- renderTable({
    req(seg)
    seg %>% arrange(desc(mean_daily_activity)) %>%
      select(station_id, abc_class, xyz_class, n_days_used, mean_daily_activity, cv_daily_activity, is_provisional)
  })

  forecast_all <- reactive({
    files <- c("1 hour" = "forecast_results.md", "3 hours" = "forecast_results_h3.md", "6 hours" = "forecast_results_h6.md")
    bind_rows(lapply(names(files), function(h) { t <- md_table(files[[h]], "F1"); if (is.null(t)) NULL else mutate(t, horizon = h) }))
  })
  output$fc_brier <- renderPlot({
    d <- forecast_all(); req(nrow(d) > 0)
    d$horizon <- factor(d$horizon, c("1 hour", "3 hours", "6 hours"))
    ggplot(d, aes(model, brier, fill = model)) +
      geom_col(show.legend = FALSE) + geom_errorbar(aes(ymin = brier_lo, ymax = brier_hi), width = .25) +
      facet_wrap(~horizon) + coord_flip() +
      labs(x = NULL, y = "Brier score (lower is better); bars: 95% interval from resampling test days") + theme_minimal()
  })
  output$fc_table <- renderTable({
    d <- forecast_all(); req(nrow(d) > 0)
    d %>% select(horizon, model, base_rate, brier, auc, ece)
  })
  output$fc_calib <- renderPlot({
    d <- md_table("forecast_results.md", "F5. Calibration: gbm"); req(d)
    ggplot(d, aes(mean_pred, obs_rate, size = n)) + geom_abline(linetype = 2, colour = "grey50") + geom_point() +
      coord_equal(xlim = c(0, 1), ylim = c(0, 1)) + labs(x = "Predicted probability", y = "Observed share", size = "Station-hours") +
      theme_minimal()
  })

  output$sim_avoided <- renderPlot({
    d <- md_table("simulation_results.md", "E3"); req(d)
    d <- d %>% filter(policy != "none") %>% mutate(policy = factor(policy_labels[policy], policy_labels))
    ggplot(d, aes(policy, avoided_vs_none)) + geom_col(fill = "#4a7ab0") +
      geom_errorbar(aes(ymin = avoided_ci_lo, ymax = avoided_ci_hi), width = .25) +
      labs(x = NULL, y = "Lost pickups avoided per day") + theme_minimal()
  })
  output$sim_vs_reactive <- renderPlot({
    d <- md_table("simulation_results.md", "E3b"); req(d)
    d <- d %>% mutate(policy = factor(policy_labels[policy], policy_labels))
    ggplot(d, aes(policy, extra_lost_pickups_avoided_per_day_vs_reactive)) +
      geom_hline(yintercept = 0) + geom_pointrange(aes(ymin = lo95, ymax = hi95)) +
      labs(x = NULL, y = "Pickups avoided per day relative to reactive\n(positive = better than reactive)") + theme_minimal()
  })
  output$sim_grid <- renderPlot({
    d <- md_table("simulation_results.md", "E4"); req(d)
    d <- d %>% filter(demand_scale == as.numeric(input$sim_scale))
    ggplot(d, aes(factor(transfers_per_round), forecast_3h_beats_reactive_by)) +
      geom_hline(yintercept = 0) + geom_pointrange(aes(ymin = fc_lo95, ymax = fc_hi95), colour = "#4a7ab0") +
      labs(x = "Transfers per round", y = "Forecast 3 h beats reactive by\n(lost pickups per day)") + theme_minimal()
  })
  output$sim_valid <- renderTable({
    md_table("simulation_results.md", "E2b. Does")
  })

  output$health <- renderPlot({
    req(hlth)
    hlth$snapshot_ts <- as.POSIXct(hlth$snapshot_ts, tz = "UTC")
    ggplot(hlth, aes(snapshot_ts, gap_minutes)) + geom_point(alpha = .5) +
      scale_y_log10() +
      labs(x = NULL, y = "Minutes since previous run (log scale)") + theme_minimal()
  })
}

shinyApp(ui, server)
