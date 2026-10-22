# FDAF Monitoring Dashboard

Pulls data from KoboToolbox and shows, in one dashboard:

1. **Daily surveys** by enumerator/CF, role (title), area (region, province, municipality, barangay), with the number of surveys per enumerator per day and totals per municipality, barangay, day and overall.
2. **Quality & compliance monitoring** scores (per enumerator, per section, per question), from the monitoring form.
3. **Accuracy / data-integrity checker** - 94 automated checks (see `RULES.md`) that test the FDAF for: skip-rule violations (it reads the form's own skip logic and tests every answer against it), contradictions between related answers, member and respondent **name format** ("Last Name, First Name, Middle Name"), gibberish / test / copy-pasted text, outliers and data-entry errors (ages, dates, income, GPS, contact numbers, interview times), straight-lining, multi-select conflicts, and whether the **Section 9 assessment and referral** follow from the system score and flags. Results appear as **Table 1 (summary)** and **Table 2 (flagged-submissions log)**.
4. **Enumerator confidence level** (High / Medium / Low) combining monitoring and integrity scores.
5. **Deeper logic and fabrication checks** (new): age vs grade with graded severity (an adult in Grade 2 is Critical), attainment vs age, civil status vs spouse, occupation vs employment, roster-derived counts vs stored counts, edited records, GPS far from the barangay, impossible travel between interviews, enumerator pattern warnings (age/DOB/income rounding, unusually fast interviews), a monitoring back-check against the FDAF data, and a **data-quality dimension scorecard** (completeness, validity, consistency, relevance, plausibility, uniqueness, timeliness, integrity).

Everything refreshes automatically: the dashboard re-pulls from Kobo every 10 minutes (`cache_minutes` in `config.yaml`).

## 1. One-time setup  (about 5 minutes)
0. **Extract the zip first** (right-click > Extract All). Running it from inside the zip causes errors.
1. Install Python 3.10+ and, in the extracted folder, run: `pip install -r requirements.txt`
2. In KoboToolbox: **Account Settings > Security > API token** - copy the token.
3. Copy `.env.example` to a new file named `.env` and paste the token after `KOBO_TOKEN=` (no quotes, no spaces).
   (Alternative: set it in the terminal - PowerShell `$env:KOBO_TOKEN="..."`, Mac/Linux `export KOBO_TOKEN=...`.)
4. `config.yaml` already lists the four projects (3 FDAF versions + the Monitoring form). **Order does not matter** - the
   dashboard looks each project up in Kobo and works out by itself which is FDAF and which is Monitoring, then combines
   all FDAF versions into one dashboard. To add another FDAF version later, just add its UID to the `projects:` list.
   If your account is on the EU server, change `server` to `https://eu.kobotoolbox.org`.
5. **Test the connection:** `python check_kobo.py` - it checks the token, the server and each project, and tells you what to
   fix. Do this first whenever the dashboard shows an error.
6. Start the dashboard: `streamlit run app.py` (or double-click `run_dashboard.bat` on Windows) and open http://localhost:8501.
   It shows demo data until the token is set. Want to see the demo anyway? `python run_daily.py --demo`.

**Automatic updates:** while the page is open it re-pulls from Kobo every `cache_minutes` (10 by default) and redraws by itself;
**Refresh now** in the sidebar forces it immediately. If Kobo is briefly unreachable it shows the last saved copy (marked *cached*
on the Data status tab) instead of failing.

**Several FDAF versions:** the sidebar has a *Kobo form / project* filter. Submissions are de-duplicated by Kobo's `_uuid`.
**Enumerators typed as names (MINSOC forms):** where a form has no enumerator code, the typed name is matched to
`reference/FDAF_Enumerator_Directory.xlsx` regardless of word order, capitalisation, commas or small typos. People not found in the
directory still appear (title *Not in directory*, ID starting `X-`); **add them to the directory** to give them a proper code, role and area.

## 2. Running it
- **Dashboard:** `streamlit run app.py` (opens in the browser). Use the sidebar filters; each table has a CSV download.
- **Daily report job:** `python run_daily.py` writes an Excel report and CSV files to `output/` (daily surveys, confidence, monitoring scores, integrity flags). Schedule it:
  - Windows: Task Scheduler > Create Basic Task > Daily > Start a program > `python` with argument `run_daily.py`, start in this folder.
  - Mac/Linux cron: `0 18 * * * cd /path/to/fdaf_dashboard && python run_daily.py`
- **Power BI / Looker Studio / Excel:** point them at the CSV files in `output/` (refreshed by the daily job).
- **Sharing with the team:** host `app.py` on Streamlit Community Cloud (keep the repo private, add `KOBO_TOKEN` under Secrets) or on any office server/PC that stays on.

## 3. Auditing an export file (no API needed)
In Kobo: **Downloads > Export**, format XLS (or CSV), value and header format **XML values and headers**, then:
`python audit_export.py my_export.xlsx`  (CSV export: `python audit_export.py main.csv --members hh_members.csv`).
It prints Table 1 and Table 2 and saves `audit_report.xlsx`. Table 2 columns: *Submission ID / _id | Question Name / Label | Submitted Value | Error Category | Flag Reason & Recommended Action | Severity (High / Medium / Low)*. Mapping: Critical = High, Major = Medium, Minor = Low. The same tables appear in the dashboard tab **Audit log (Tables 1 & 2)**.

**Limits to know:** (a) the skip-rule test needs the form's calculated fields (e.g. member_age, member_is_learner) in the export - Kobo includes them; a question whose condition uses a field missing from the export is left untested, and Table 1 shows how many were tested; (b) "off-topic" text is detected only by simple signs (filler words, links, numbers, questions, keyboard patterns) - real off-topic answers still need a human read; (c) answers must be exported as codes (XML values), not labels.

## 4. How the scores work
- **Monitoring score** = points / questions applicable, per section and overall (Yes = 1, Partly = 0.5, No = 0; questions skipped by a filter are excluded).
- **Integrity score** per survey = 100 - 25 x Critical - 10 x Major - 3 x Minor flags. Enumerator score = average of their surveys.
- **Confidence score** = 60% monitoring + 40% integrity. High >= 90, Medium >= 75, else Low. A failed consent item (consent script or informed consent rated *No*) caps the level at Low. Fewer than 2 monitored surveys shows as *provisional*. An enumerator never monitored is scored on integrity only and labelled so.
- All weights and thresholds are in `config.yaml`.

## 5. When the forms change
The code reads field names exactly as in the XLSForms. The skip-logic checks use `reference/FDAF_master.xlsx` as the reference form; if a MINSOC/other version differs in its skip rules, swap in that form's XLSForm (or expect extra skip-rule flags for it). If you add, rename or remove FDAF questions: update `reference/FDAF_master.xlsx`, and adjust the affected rule in `src/integrity.py`. If you change enumerators or CFs, update `reference/FDAF_Enumerator_Directory.xlsx` (code, name, role, area) - this is what turns codes into names and roles on every screen.

## 6. Privacy
Flags show the Family ID and member number, never family or respondent names. The dashboard shows staff names only. Keep the app, the CSVs and the Kobo token restricted to authorised staff; don't commit `.env`, `data/` or `output/`.

## 7. Tests
`python -m tests.test_pipeline` - builds fake submissions with planted errors and confirms every one is caught.
`python -m tests.test_rules_unit` - unit tests for the name-format and gibberish detectors.
`python -m tests.test_new_rules` - age-vs-grade (35 in Grade 2), attainment, civil-status, roster-count, pattern and monitoring-link tests, plus a zero-false-positive check on clean data.
`python -m tests.test_export_cli` - audits a fake Kobo export file end to end.
`python -m tests.test_app_smoke` - runs the dashboard code against a stubbed Streamlit to catch runtime errors.
`python -m tests.test_multi_project` - mocked Kobo API with several projects, typed enumerator names and a wrong UID.

## Folder layout
`app.py` dashboard | `check_kobo.py` connection doctor | `audit_export.py` audit an export file | `run_daily.py` scheduled job | `config.yaml` settings | `src/` code (`kobo_client`, `loader`, `integrity`, `skiplogic`, `audit`, `monitoring`, `pipeline`, `demo_data`) | `reference/` form and directory files | `RULES.md` rule list.
