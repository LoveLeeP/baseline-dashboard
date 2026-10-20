# Accuracy-checker rules

Each rule compares answers that should agree with each other. Severity: **Critical** = data cannot be trusted (shown as *High* in the audit log), **Major** = likely wrong (*Medium*), **Minor** = please verify (*Low*).
Integrity score per survey = 100 minus 25 per Critical, 10 per Major, 3 per Minor flag (weights in `config.yaml`).

| ID | Severity | Level | Audit category | What it checks |
|---|---|---|---|---|
| HH01 | Critical | household | Outliers & Data Entry Errors | Duplicate Family ID |
| HH02 | Critical | household | Logic & Skip Rule Violations | Members recorded although consent not given |
| HH03 | Critical | household | Logic & Skip Rule Violations | Not exactly one Family Head in roster |
| HH04 | Major | household | Logic & Skip Rule Violations | Family head name differs from roster head |
| HH05 | Major | household | Logic & Skip Rule Violations | Family head gender differs from roster head sex |
| HH06 | Major | household | Logic & Skip Rule Violations | Respondent relationship does not match respondent name |
| HH07 | Major | household | Outliers & Data Entry Errors | Interview too short for household size |
| HH08 | Minor | household | Outliers & Data Entry Errors | Interview unusually long |
| HH09 | Major | household | Outliers & Data Entry Errors | Device date inconsistent with submission |
| HH10 | Minor | household | Outliers & Data Entry Errors | Late submission |
| HH11 | Major | household | Logic & Skip Rule Violations | IP family flag inconsistent with ICC/IP group |
| HH12 | Major | household | Outliers & Data Entry Errors | GPS missing |
| HH13 | Minor | household | Outliers & Data Entry Errors | Poor GPS accuracy |
| HH14 | Critical | household | Outliers & Data Entry Errors | GPS outside the Philippines |
| HH15 | Major | household | Outliers & Data Entry Errors | Same GPS point used by different families |
| HH16 | Major | household | Logic & Skip Rule Violations | Household size calculation does not match roster |
| HH17 | Major | household | Logic & Skip Rule Violations | No adult (18+) in household |
| HH18 | Major | household | Logic & Skip Rule Violations | More than one spouse in roster |
| LV01 | Major | household | Logic & Skip Rule Violations | Primary livelihood not among livelihood sources |
| LV02 | Major | household | Logic & Skip Rule Violations | 'No livelihood' selected together with other sources |
| LV03 | Minor | household | Logic & Skip Rule Violations | Income does not match livelihood |
| LV04 | Major | household | Outliers & Data Entry Errors | Implausible monthly income |
| LV05 | Minor | household | Logic & Skip Rule Violations | Income per person does not match 'basic needs' answer |
| LV06 | Major | household | Logic & Skip Rule Violations | Farmland answers inconsistent with livelihood |
| LV07 | Major | household | Outliers & Data Entry Errors | Farm size missing or implausible |
| LV08 | Major | household | Logic & Skip Rule Violations | Harvest proportions add up to more than 100% |
| LV09 | Major | household | Logic & Skip Rule Violations | Food insecurity contradicts 'basic needs' answer |
| LV10 | Major | household | Logic & Skip Rule Violations | Own-food production inconsistent with food types |
| LV11 | Minor | household | Logic & Skip Rule Violations | Livestock / fishing recorded without matching livelihood |
| WS01 | Major | household | Logic & Skip Rule Violations | Water source inconsistent with collection time |
| WS02 | Minor | household | Logic & Skip Rule Violations | Unsafe water source but full confidence in water safety |
| SO01 | Major | household | Multi-Select Conflicts | 'None' selected together with other options |
| SO02 | Minor | household | Multi-Select Conflicts | More than 3 family challenges selected |
| SO03 | Minor | household | Outliers & Data Entry Errors | Identical answers across many scale questions |
| SO05 | Major | household | Outliers & Data Entry Errors | Possible duplicate interview (same head name, barangay and birth date) |
| SO06 | Major | household | Outliers & Data Entry Errors | Identical answer set in different surveys (possible copy-paste) |
| SO07 | Minor | household | Outliers & Data Entry Errors | Interview outside working hours |
| SO08 | Minor | household | Outliers & Data Entry Errors | Very high number of surveys by one enumerator in a day |
| SO09 | Major | household | Outliers & Data Entry Errors | Overlapping interviews by the same enumerator |
| SO11 | Minor | household | Outliers & Data Entry Errors | Survey outside the enumerator's home area |
| MB01 | Critical | member | Outliers & Data Entry Errors | Date of birth missing, in the future or implausible |
| MB02 | Major | member | Logic & Skip Rule Violations | Recorded age differs from age calculated from date of birth |
| MB03 | Major | member | Logic & Skip Rule Violations | Age does not fit the grade / schooling level |
| MB04 | Major | member | Logic & Skip Rule Violations | Education attainment inconsistent with schooling status or age |
| MB05 | Major | member | Logic & Skip Rule Violations | Child with occupation or employment |
| MB06 | Major | member | Logic & Skip Rule Violations | Employment status inconsistent with age or schooling |
| MB07 | Critical | member | Logic & Skip Rule Violations | Pregnant/lactating status impossible for sex or age |
| MB08 | Major | member | Logic & Skip Rule Violations | Civil status impossible for age |
| MB09 | Major | member | Logic & Skip Rule Violations | Relationship inconsistent with sex |
| MB10 | Major | member | Logic & Skip Rule Violations | Relationship inconsistent with age gap to the family head |
| MB11 | Major | member | Outliers & Data Entry Errors | Family head is a minor |
| MB12 | Major | member | Logic & Skip Rule Violations | Disability answers inconsistent |
| MB13 | Major | member | Logic & Skip Rule Violations | Leadership roles inconsistent with age or 'None' |
| MB14 | Major | member | Logic & Skip Rule Violations | Learner answers inconsistent with schooling status |
| MB15 | Major | member | Logic & Skip Rule Violations | Scholarship answers inconsistent |
| MB16 | Major | member | Outliers & Data Entry Errors | Duplicate member names or same birthday for many members |
| MB17 | Minor | member | Open-Text Quality & Gibberish | Invalid or placeholder member name |
| MB18 | Major | member | Logic & Skip Rule Violations | Child nutrition answer recorded for a child aged 6 or above |
| MB19 | Major | member | Logic & Skip Rule Violations | 'Not in same ICC/IP group' without a specification |
| MB20 | Minor | member | Open-Text Quality & Gibberish | Member name not in the required format (Last Name, First Name, Middle Name) |
| HH19 | Minor | household | Open-Text Quality & Gibberish | Family head / respondent name not in the required format |
| TX01 | Major | any | Open-Text Quality & Gibberish | Gibberish, keyboard smash or test entry in a text answer |
| TX02 | Minor | household | Open-Text Quality & Gibberish | Identical free-text copied across many surveys, or repetitive text |
| TX03 | Minor | any | Open-Text Quality & Gibberish | Text answer is a non-answer, too short, or not an answer (URL / number / question) |
| CT01 | Minor | household | Outliers & Data Entry Errors | Invalid or placeholder contact number |
| CT02 | Minor | household | Outliers & Data Entry Errors | Same contact number used by many different families |
| HH20 | Major | household | Outliers & Data Entry Errors | Impossible or out-of-range interview dates/times |
| HH21 | Minor | household | Outliers & Data Entry Errors | Unusually large household |
| MB21 | Major | member | Multi-Select Conflicts | 'None' selected together with other options (member questions) |
| LV12 | Major | household | Logic & Skip Rule Violations | Members employed but family reports no livelihood (or the reverse) |
| S901 | Minor | household | Logic & Skip Rule Violations | Final family priority is lower than the system-suggested priority |
| S902 | Major | household | Logic & Skip Rule Violations | Urgent flags raised but no immediate referral recorded |
| S903 | Minor | household | Logic & Skip Rule Violations | Referral recorded without any urgent flag or critical/at-risk score |
| S904 | Minor | household | Logic & Skip Rule Violations | Recommended programs omit programs the system suggested |
| S905 | Major | household | Logic & Skip Rule Violations | Score band or suggested priority does not match the recorded score/flags |
| S906 | Minor | household | Logic & Skip Rule Violations | Referral reason not supported by the system flags |
| SKIP01 | Major | any | Logic & Skip Rule Violations | An answer exists for a question that should have been skipped (tests all skip rules in the form) |
| SKIP02 | Major | any | Logic & Skip Rule Violations | A required question that applies is blank |

To add a rule, copy any function in `src/integrity.py`, change the `@rule(...)` line and the logic, and add its entry (category, fields, recommended action) to `META`. It is picked up automatically.
