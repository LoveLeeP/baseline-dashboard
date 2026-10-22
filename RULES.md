# Accuracy-checker rules

Each rule compares answers that should agree with each other. Severity: **Critical** = data cannot be trusted (shown as *High* in the audit log), **Major** = likely wrong (*Medium*), **Minor** = please verify (*Low*). A few rules raise a higher severity when the mismatch is extreme (noted in the rule text).
Integrity score per survey = 100 minus 25 per Critical, 10 per Major, 3 per Minor flag (weights in `config.yaml`).
Every rule also belongs to one **data-quality dimension** (Completeness, Validity, Consistency, Relevance, Plausibility, Uniqueness, Timeliness, Integrity); the dashboard and Table 1 summarise flags by dimension.

**94 checks in total.** Rules MB22-MB28, HH22-HH29 and SO12 are new in this version.

| ID | Severity | Level | Audit category | Quality dimension | What it checks |
|---|---|---|---|---|---|
| HH01 | Critical | household | Outliers & Data Entry Errors | Uniqueness | Duplicate Family ID |
| HH02 | Critical | household | Logic & Skip Rule Violations | Consistency | Members recorded although consent not given |
| HH03 | Critical | household | Logic & Skip Rule Violations | Consistency | Not exactly one Family Head in roster |
| HH04 | Major | household | Logic & Skip Rule Violations | Consistency | Family head name differs from roster head |
| HH05 | Major | household | Logic & Skip Rule Violations | Consistency | Family head gender differs from roster head sex |
| HH06 | Major | household | Logic & Skip Rule Violations | Consistency | Respondent relationship does not match respondent name |
| HH07 | Major | household | Outliers & Data Entry Errors | Integrity | Interview too short for household size |
| HH08 | Minor | household | Outliers & Data Entry Errors | Plausibility | Interview unusually long |
| HH09 | Major | household | Outliers & Data Entry Errors | Timeliness | Device date inconsistent with submission |
| HH10 | Minor | household | Outliers & Data Entry Errors | Timeliness | Late submission |
| HH11 | Major | household | Logic & Skip Rule Violations | Consistency | IP family flag inconsistent with ICC/IP group |
| HH12 | Major | household | Outliers & Data Entry Errors | Completeness | GPS missing |
| HH13 | Minor | household | Outliers & Data Entry Errors | Validity | Poor GPS accuracy |
| HH14 | Critical | household | Outliers & Data Entry Errors | Integrity | GPS outside the Philippines |
| HH15 | Major | household | Outliers & Data Entry Errors | Integrity | Same GPS point used by different families |
| HH16 | Major | household | Logic & Skip Rule Violations | Consistency | Household size calculation does not match roster |
| HH17 | Major | household | Logic & Skip Rule Violations | Consistency | No adult (18+) in household |
| HH18 | Major | household | Logic & Skip Rule Violations | Consistency | More than one spouse in roster |
| LV01 | Major | household | Logic & Skip Rule Violations | Consistency | Primary livelihood not among livelihood sources |
| LV02 | Major | household | Logic & Skip Rule Violations | Consistency | 'No livelihood' selected together with other sources |
| LV03 | Minor | household | Logic & Skip Rule Violations | Consistency | Income does not match livelihood |
| LV04 | Major | household | Outliers & Data Entry Errors | Plausibility | Implausible monthly income |
| LV05 | Minor | household | Logic & Skip Rule Violations | Consistency | Income per person does not match 'basic needs' answer |
| LV06 | Major | household | Logic & Skip Rule Violations | Consistency | Farmland answers inconsistent with livelihood |
| LV07 | Major | household | Outliers & Data Entry Errors | Plausibility | Farm size missing or implausible |
| LV08 | Major | household | Logic & Skip Rule Violations | Consistency | Harvest proportions add up to more than 100% |
| LV09 | Major | household | Logic & Skip Rule Violations | Consistency | Food insecurity contradicts 'basic needs' answer |
| LV10 | Major | household | Logic & Skip Rule Violations | Consistency | Own-food production inconsistent with food types |
| LV11 | Minor | household | Logic & Skip Rule Violations | Consistency | Livestock / fishing recorded without matching livelihood |
| WS01 | Major | household | Logic & Skip Rule Violations | Consistency | Water source inconsistent with collection time |
| WS02 | Minor | household | Logic & Skip Rule Violations | Consistency | Unsafe water source but full confidence in water safety |
| SO01 | Major | household | Multi-Select Conflicts | Consistency | 'None' selected together with other options |
| SO02 | Minor | household | Multi-Select Conflicts | Plausibility | More than 3 family challenges selected |
| SO03 | Minor | household | Outliers & Data Entry Errors | Integrity | Identical answers across many scale questions |
| SO05 | Major | household | Outliers & Data Entry Errors | Uniqueness | Possible duplicate interview (same head name, barangay and birth date) |
| SO06 | Major | household | Outliers & Data Entry Errors | Uniqueness | Identical answer set in different surveys (possible copy-paste) |
| SO07 | Minor | household | Outliers & Data Entry Errors | Integrity | Interview outside working hours |
| SO08 | Minor | household | Outliers & Data Entry Errors | Integrity | Very high number of surveys by one enumerator in a day |
| SO09 | Major | household | Outliers & Data Entry Errors | Integrity | Overlapping interviews by the same enumerator |
| SO11 | Minor | household | Outliers & Data Entry Errors | Integrity | Survey outside the enumerator's home area |
| MB01 | Critical | member | Outliers & Data Entry Errors | Validity | Date of birth missing, in the future or implausible |
| MB02 | Major | member | Logic & Skip Rule Violations | Consistency | Recorded age differs from age calculated from date of birth |
| MB03 | Major | member | Logic & Skip Rule Violations | Consistency | Age does not fit the grade / schooling level (Critical when grossly out of range, e.g. an adult in Grade 2) |
| MB04 | Major | member | Logic & Skip Rule Violations | Consistency | Education attainment inconsistent with schooling status or age |
| MB05 | Major | member | Logic & Skip Rule Violations | Consistency | Child with occupation or employment |
| MB06 | Major | member | Logic & Skip Rule Violations | Consistency | Employment status inconsistent with age or schooling |
| MB07 | Critical | member | Logic & Skip Rule Violations | Consistency | Pregnant/lactating status impossible for sex or age |
| MB08 | Major | member | Logic & Skip Rule Violations | Consistency | Civil status impossible for age |
| MB09 | Major | member | Logic & Skip Rule Violations | Consistency | Relationship inconsistent with sex |
| MB10 | Major | member | Logic & Skip Rule Violations | Consistency | Relationship inconsistent with age gap to the family head |
| MB11 | Major | member | Outliers & Data Entry Errors | Consistency | Family head is a minor |
| MB12 | Major | member | Logic & Skip Rule Violations | Consistency | Disability answers inconsistent |
| MB13 | Major | member | Logic & Skip Rule Violations | Consistency | Leadership roles inconsistent with age or 'None' |
| MB14 | Major | member | Logic & Skip Rule Violations | Consistency | Learner answers inconsistent with schooling status |
| MB15 | Major | member | Logic & Skip Rule Violations | Consistency | Scholarship answers inconsistent |
| MB16 | Major | member | Outliers & Data Entry Errors | Uniqueness | Duplicate member names or same birthday for many members |
| MB17 | Minor | member | Open-Text Quality & Gibberish | Validity | Invalid or placeholder member name |
| MB18 | Major | member | Logic & Skip Rule Violations | Relevance | Child nutrition answer recorded for a child aged 6 or above |
| MB19 | Major | member | Logic & Skip Rule Violations | Completeness | 'Not in same ICC/IP group' without a specification |
| MB20 | Minor | member | Open-Text Quality & Gibberish | Validity | Member name not in the required format (Last Name, First Name, Middle Name) |
| HH19 | Minor | household | Open-Text Quality & Gibberish | Validity | Family head / respondent name not in the required format |
| TX01 | Major | any | Open-Text Quality & Gibberish | Validity | Gibberish, keyboard smash or test entry in a text answer |
| TX02 | Minor | household | Open-Text Quality & Gibberish | Uniqueness | Identical free-text copied across many surveys, or repetitive text |
| TX03 | Minor | any | Open-Text Quality & Gibberish | Validity | Text answer is a non-answer, too short, or not an answer (URL / number / question) |
| CT01 | Minor | household | Outliers & Data Entry Errors | Validity | Invalid or placeholder contact number |
| CT02 | Minor | household | Outliers & Data Entry Errors | Uniqueness | Same contact number used by many different families |
| HH20 | Major | household | Outliers & Data Entry Errors | Validity | Impossible or out-of-range interview dates/times |
| HH21 | Minor | household | Outliers & Data Entry Errors | Plausibility | Unusually large household |
| MB21 | Major | member | Multi-Select Conflicts | Consistency | 'None' selected together with other options (member questions) |
| LV12 | Major | household | Logic & Skip Rule Violations | Consistency | Members employed but family reports no livelihood (or the reverse) |
| S901 | Minor | household | Logic & Skip Rule Violations | Consistency | Final family priority is lower than the system-suggested priority |
| S902 | Major | household | Logic & Skip Rule Violations | Consistency | Urgent flags raised but no immediate referral recorded |
| S903 | Minor | household | Logic & Skip Rule Violations | Consistency | Referral recorded without any urgent flag or critical/at-risk score |
| S904 | Minor | household | Logic & Skip Rule Violations | Consistency | Recommended programs omit programs the system suggested |
| S905 | Major | household | Logic & Skip Rule Violations | Consistency | Score band or suggested priority does not match the recorded score/flags |
| S906 | Minor | household | Logic & Skip Rule Violations | Consistency | Referral reason not supported by the system flags |
| MB22 | Major | member | Logic & Skip Rule Violations | Consistency | Age too young for the highest educational attainment recorded (Critical when more than 3 years below the minimum age) |
| MB23 | Major | member | Logic & Skip Rule Violations | Consistency | Occupation inconsistent with employment status |
| MB24 | Major | member | Logic & Skip Rule Violations | Consistency | Civil status inconsistent with the spouse listed in the roster |
| MB25 | Minor | member | Logic & Skip Rule Violations | Plausibility | Solo-parent status without a child in the household |
| MB26 | Minor | member | Logic & Skip Rule Violations | Plausibility | Lactating without a young child in the household |
| MB27 | Minor | member | Logic & Skip Rule Violations | Plausibility | Learner answers contradict each other (extreme scale answers) |
| MB28 | Minor | member | Logic & Skip Rule Violations | Plausibility | Farming/fishing occupation but no matching family livelihood |
| HH22 | Major | household | Logic & Skip Rule Violations | Consistency | Household counts do not match the roster |
| HH23 | Major | household | Logic & Skip Rule Violations | Consistency | Section 8 shock answers differ from Section 3 (record may have been edited) |
| HH24 | Major | household | Logic & Skip Rule Violations | Consistency | Housing tenure contradicts land tenure |
| HH25 | Minor | household | Logic & Skip Rule Violations | Plausibility | Assets owned do not fit the reported income |
| HH26 | Minor | household | Logic & Skip Rule Violations | Plausibility | 4Ps beneficiary with a very high per-person income |
| HH27 | Major | household | Logic & Skip Rule Violations | Consistency | Nutrition ability contradicts severe food insecurity |
| HH28 | Minor | household | Outliers & Data Entry Errors | Integrity | Interview spans two calendar days |
| HH29 | Major | household | Outliers & Data Entry Errors | Integrity | GPS far from the other surveys of the same barangay / municipality |
| SO12 | Major | household | Outliers & Data Entry Errors | Integrity | Impossible travel between consecutive interviews of one enumerator |
| SKIP01 | Major | any | Logic & Skip Rule Violations | Relevance | An answer exists for a question that should have been skipped (tests all skip rules in the form) |
| SKIP02 | Major | any | Logic & Skip Rule Violations | Completeness | A required question that applies is blank |

## Enumerator pattern checks (not scored per survey)
These look at an enumerator's whole body of work and appear in the dashboard under *Data integrity*. They are warnings for a conversation, not errors in a single survey.

| Check | Severity | Triggers when |
|---|---|---|
| Age heaping | Minor | 35% or more of an enumerator's adult ages (23-62, at least 30 members) end in 0 or 5 (expected about 20%) |
| Default date of birth | Minor | 15% or more of members (at least 30) are born on 1 January |
| Income rounding | Minor | 85% or more of incomes (at least 15 surveys) are exact multiples of 1,000 |
| Consistently faster than peers | Major | Median minutes per member (at least 8 surveys) is below half of the overall median |

## Monitoring back-check
Each monitoring visit is matched to the FDAF data (dashboard tab *Quality & compliance*): the Family ID must exist (Major), the monitored enumerator must be the one who conducted that survey (Critical), the interview date must match (Major), and the monitoring date cannot be earlier than the interview (Major).

All thresholds are in `config.yaml` under `thresholds:`.
To add a rule, copy any function in `src/integrity.py`, change the `@rule(...)` line and the logic, add its entry (category, fields, recommended action) to `META`, and (optionally) its quality dimension to `DIMENSION`. It is picked up automatically. Plant a matching error in `src/demo_data.py` (`_inject` and `RULE_IDS`) so `tests/test_pipeline.py` proves it is caught.
