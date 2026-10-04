# Website Monitor

A dashboard that checks up to 1,000+ websites on a schedule (every 10 minutes by default)
and shows which ones are broken and how:

| Status | What it means | How it is detected |
|---|---|---|
| **DNS error** | Domain does not resolve (expired domain, deleted DNS record) | System DNS lookup fails |
| **Down / unreachable** | Server refuses connections or times out | Connection error or timeout, after one retry |
| **Database error** | Site is up but its database is not | Page text such as "Error establishing a database connection", `SQLSTATE[…]`, `mysqli_connect(`, "Too many connections", CodeIgniter / Joomla DB errors |
| **500 server error** | HTTP 500 Internal Server Error | Status code 500 |
| **5xx (502/503/504)** | Bad gateway, unavailable, gateway timeout | Status code 501–599 |
| **Internal error page** | Page shows a crash but returns 200 | WordPress "critical error", PHP `Fatal error … on line N`, Laravel "Whoops", ASP.NET "Server Error in '/' Application", Heroku "Application error", "Internal Server Error" text |
| **404 not found** | Page missing | Status 404/410, or a "soft 404" (status 200 with a *Not Found* title) |
| **Blank screen** | White screen of death | Status 200 but fewer than 30 characters of visible text and no images/video/forms. Pages that are an empty JavaScript app shell are labelled as such; `--render-blank` re-checks them in headless Chromium |
| **SSL certificate** | Expired, self-signed or wrong-host certificate | TLS verification fails (the page is then fetched anyway so other errors are still found) |
| **Other 4xx / redirect** | 401, 403, 429, redirect loops | Other 4xx status codes, too many redirects |
| **Live / OK** | Everything above passed | |

Generic error phrases (e.g. "Internal Server Error", `SQLSTATE`) only count on short pages, so a
blog post that *talks about* SQL errors is not reported as an outage.

## Run it

```bash
pip install -r requirements.txt
python -m webmonitor serve --sites my_sites.txt
# open http://localhost:8080
```

`my_sites.txt` has one URL or domain per line (see `sites.example.txt`); a CSV export also works.
Sites are stored in `data/monitor.db`, so `--sites` is only needed when you have new ones — you
can also paste URLs into **Add sites** on the dashboard.

Useful options:

| Option | Default | |
|---|---|---|
| `--interval 5` | 10 | Minutes between check runs |
| `--workers 100` | 50 | Parallel checks. 1,000 sites at 50 workers take about 1–3 minutes |
| `--timeout 20` | 15 | Seconds per request before a site counts as down |
| `--webhook URL` | — | Slack/Discord/Teams incoming-webhook URL (or `MONITOR_WEBHOOK`) for alerts |
| `--alert-after 3` | 2 | Consecutive failed runs before alerting (avoids one-off blips); a recovery message is sent when the site is OK again |
| `--password …` | — | Protect the dashboard with HTTP Basic auth, any username (or `MONITOR_PASSWORD`) |
| `--host 0.0.0.0 --port 80` | 127.0.0.1:8080 | Expose on the network |
| `--keep-days 30` | 7 | History retention |
| `--render-blank` | off | Re-check blank JavaScript pages in a real browser (`pip install playwright && playwright install chromium`) |

One-off check from the command line (exit code 1 if anything is broken — handy for cron/CI):

```bash
python -m webmonitor check example.com https://shop.example.org/
python -m webmonitor check --sites my_sites.txt --json > results.jsonl
```

## The dashboard

- Summary tiles per status — click one to filter the table.
- Bar chart of problem sites per check run (last 48 runs), split by severity.
- Table sorted worst-first: status, HTTP code, response time, last 24 checks, 24-hour uptime,
  how long the site has been in its current state, and the error detail. Search by URL, IP or error text.
- Click a row for the full check history, IP, final URL after redirects and page title.
- **Check now** starts a run immediately; **Export CSV** downloads the current status of every site.

## Keep it running on a server (systemd)

```ini
# /etc/systemd/system/webmonitor.service
[Unit]
Description=Website Monitor
After=network-online.target

[Service]
WorkingDirectory=/opt/500Websites-Monitoring
ExecStart=/usr/bin/python3 -m webmonitor serve --host 0.0.0.0 --port 8080
Environment=MONITOR_PASSWORD=change-me
Environment=MONITOR_WEBHOOK=https://hooks.slack.com/services/...
Restart=always

[Install]
WantedBy=multi-user.target
```

`sudo systemctl enable --now webmonitor`
