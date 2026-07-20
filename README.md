# VisaPolicyWatch

Audit-ready monitoring of official UK Skilled Worker, UK Graduate visa, and US H-1B policy pages.

VisaPolicyWatch fetches official GOV.UK and USCIS guidance, extracts the main policy text, stores a reproducible snapshot, compares future runs, and produces Markdown and JSON evidence reports. It flags changes involving salary, eligibility, fees, duration, sponsorship, registration, selection, caps, and deadlines.

> This tool detects changes to official webpages. It does not provide legal advice, and a webpage edit does not always represent a legal-policy change. Verify important findings in the linked official guidance.

## What it monitors

- UK Skilled Worker visa overview
- UK Skilled Worker job and salary rules
- UK Skilled Worker English-language requirements
- UK Graduate visa
- USCIS H-1B specialty occupations
- USCIS H-1B electronic registration
- USCIS H-1B cap season

The monitored URLs are defined in [`sources.json`](sources.json).

## How it works

```text
Official GOV.UK / USCIS pages
              ↓
      Main-content extraction
              ↓
       Normalized text snapshot
              ↓
       Deterministic comparison
              ↓
  Keyword + line-count + similarity rules
              ↓
 Markdown / JSON evidence report
              ↓
 GitHub issue or optional email alert
```

The first run creates a baseline and does not send a change alert. Later runs compare the current official text with the saved baseline.

## Quick start

Requires Python 3.10 or newer.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python visa_monitor.py
```

macOS or Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python visa_monitor.py
```

Generated files:

```text
data/state.json
reports/latest.md
reports/latest.json
```

## GitHub Actions

The workflow in [`.github/workflows/visa-monitor.yml`](.github/workflows/visa-monitor.yml):

- runs manually through `workflow_dispatch`;
- runs monthly on day 1 at 00:00 UTC, which is 08:00 in Taiwan;
- installs dependencies;
- checks all configured official sources;
- commits updated snapshots and reports;
- opens a GitHub issue when a meaningful change is detected.

Run the workflow manually once to establish the first baseline.

The repository may need this setting:

**Settings → Actions → General → Workflow permissions → Read and write permissions**

## Windows monthly task

Open PowerShell in the repository folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_windows_task.ps1
```

This installs a Windows Task Scheduler job for the first day of every month at 08:00.

Choose another time with:

```powershell
.\install_windows_task.ps1 -RunTime "09:30"
```

Run the monitor manually with:

```powershell
.\run_monitor.ps1
```

## Optional email alerts

Set these environment variables:

```text
SMTP_HOST
SMTP_PORT          default: 465
SMTP_USER
SMTP_PASSWORD
ALERT_TO
ALERT_FROM         optional; defaults to SMTP_USER
```

Then run:

```bash
python visa_monitor.py --email
```

For Gmail, use an app password rather than your normal account password.

## Detection controls

```bash
python visa_monitor.py \
  --min-changed-lines 8 \
  --similarity-threshold 0.985
```

A change is marked meaningful when at least one condition applies:

- changed text contains a tracked policy keyword;
- added plus removed lines reach the configured threshold;
- the page is broadly rewritten below the similarity threshold.

Use `--fail-on-change` to return exit code `2` when a meaningful change is found.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests run without live internet access and cover main-content extraction and core change detection.

## Security and privacy

- No credentials are stored in the repository.
- TLS verification remains enabled.
- SMTP passwords are read only from environment variables.
- Official sources are fetched at a low frequency.
- Downloaded webpage content is treated as text and is never executed.

## Limitations

- Deterministic rules can still produce false positives or miss subtle legal changes.
- GOV.UK or USCIS layout changes may require extractor updates.
- A changed guidance page may reflect editorial wording rather than a binding legal change.
- The project currently monitors selected UK and US routes, not every immigration program.

## License

MIT License. See [`LICENSE`](LICENSE).
