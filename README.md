# Construction Contract Generator

A rule-based LegalTech prototype that turns the answers of a construction company
(the Contractor) about a house-building project for a private Client into the right
contract clauses, explains why each clause was chosen, and creates the construction
contract as a Word file. Swiss law: contract for work, Code of Obligations (CO / OR)
art. 363 ff. Contract language: English.

> **Academic prototype for seminar demonstration.** The generated contract may contain
> incomplete sections and requires completion and legal review before use. It is not
> legal advice. Use fictional data only.

**Status (iteration 1):** topic 1 "Price and payment" is complete (4 clauses, 11 rules).
Topics 2–5 (completion date and delay penalty, acceptance and defects, liability,
termination) appear in the contract as "Not generated in this prototype".

No AI is used inside the app: every decision comes from a written rule in `data/rules.yaml`
with its legal source.

---

## 1. Install (once)

You need Python 3.12. From the project folder:

```bash
python3.12 -m venv .venv            # create a virtual environment (skip if .venv already exists)
source .venv/bin/activate           # activate it (macOS / Linux); on Windows: .venv\Scripts\activate
pip install -r requirements.txt     # install the pinned libraries
```

## 2. Run the app

```bash
source .venv/bin/activate
streamlit run app.py
```

The browser opens at <http://localhost:8501>. Fill in the questionnaire, click
**Check answers** (once; afterwards the check runs after every change), read the review
screen and click **Download contract (Word)**. Stop the app with `Ctrl+C`.

After changing a YAML file in `data/`, restart the app (the files are loaded once).

## 3. Run the tests

```bash
source .venv/bin/activate
python -m pytest -v
```

All tests must pass. They cover the data files, the placeholders and rounding, every rule
of the engine, the test scenarios P1–P15 and the Word generator.

Quick check of the data files only (useful after editing a YAML file):

```bash
python data_loader.py
```

It prints `All data files are OK: ...` or a list of mistakes with file, rule and line.

---

## 4. Project structure

```
app.py                     Streamlit user interface: questionnaire, messages, review screen, download
engine.py                  rule engine: answers in -> errors, warnings, selected and filled clauses out
checks.py                  the 4 special checks that rules.yaml refers to by name
placeholders.py            fills the {placeholders} of a clause; CHF / date formats; milestone rounding
generator.py               fills the Word template and returns the contract as bytes
data_loader.py             reads the 4 YAML files and checks them for mistakes
data/
  sources.yaml             legal sources (S1, S2, S4) and article citations
  parameters.yaml          the questions: types, allowed answers, help texts, when shown / required
  clauses.yaml             topics, slots, the clause texts, derived texts (VAT sentence, milestone rows)
  rules.yaml               the rules: R_ (errors), W_ (warnings), SEL_ (clause selection)
templates/
  make_template.py         builds the Word template from the law student's contract skeleton
  contract_template.docx   the Word template (generated; do not edit by hand)
tests/
  test_data_loader.py      the data files load; typical YAML mistakes are caught
  test_placeholders.py     formats, rounding (amounts add up exactly), derived texts
  test_engine.py           at least one test per rule, the conditions, the review records
  test_scenarios.py        runs every scenario file through the engine
  test_generator.py        real Word contracts for P1 and P2; refusal on errors
  scenarios/               base_project.yaml + P1.yaml ... P15.yaml (expected results)
.streamlit/config.toml     colours of the app
requirements.txt           pinned library versions
```

## 5. How it works

```
data/*.yaml ──> data_loader.py ──> knowledge
                                       │
answers (app.py) ──> engine.evaluate(answers, knowledge)
                        step 0  ignore inactive and unknown answers
                        step 1  input errors      R_SCOPE, R_REQUIRED, R_PRICE, R_PAY   (uses checks.py)
                        step 2  warnings          W_PRICE, W_CONSUMER                    (uses checks.py)
                                -> stop here if step 1 found an error
                        step 3  select clauses    SEL_ rules
                        step 4  fill placeholders                                        (uses placeholders.py)
                        step 5  final checks      R_CROSS (one clause per slot)
                     ──> result: can_generate, errors, warnings, selected_clauses (review records), ...
                                       │
                     generator.generate_contract(result, answers) ──> contract.docx
```

The legal knowledge is in the YAML files, not in the Python code. If the law changes,
the law side changes `rules.yaml` or `clauses.yaml`, not the program.

---

## 6. How to change or add legal content

Always: edit the YAML file → `python data_loader.py` → `python -m pytest -v` → restart the app.
Every YAML entry has a comment; copy an existing entry and change it.

### Change a clause text
1. Edit `text` of the clause in `data/clauses.yaml` (only with the law student's approval).
2. Raise its `version` (e.g. `"1.0"` → `"1.1"`).
3. Every `{placeholder}` in the text must be listed in `inputs`.

### Add a clause
1. `data/clauses.yaml`: add the clause with `id`, `topic`, `slot`, `title`, `version`, `text`,
   `inputs`, `citations`, `basis_note` and the six `metadata` flags.
2. `data/rules.yaml`: add exactly one selection rule with the ID `SEL_` + clause ID,
   `type: select`, `step: 3`, `clause`, `when` and `reason`.
3. If the clause goes into a new place of the contract, add the slot to `slots:` in
   `clauses.yaml` and a `{{ slot_name }}` to `templates/make_template.py`, then run
   `python templates/make_template.py`.
4. New citations go into `data/sources.yaml`.

### Add a simple error or warning
Add a rule to `data/rules.yaml` with `type` (`error` / `warning`), `step` (1 = error,
2 = warning), `category` (LAW / PRODUCT), `citations`, `message` and one or more `cases`.
A condition compares one answer with a value, for example:

```yaml
cases:
  - when: {field: contract_price, op: at_most, value: 0}
    field: contract_price
```

Operators: `equals`, `not_equals`, `less_than`, `at_most`, `greater_than`, `at_least`,
`one_of`, `is_empty`, `is_filled`; combine with `all`, `any`, `not`. No Python code is needed.
A check that has to go through a table or count things needs a small function in
`checks.py` (listed in `CHECKS` at the end of the file) that the rule names with `check:`.

### Add a question
Add a field to `data/parameters.yaml` (`id`, `section`, `type`, `question`, `required`,
optional `help_text` and `active_when`). The app shows it automatically.

### Add a test scenario
Copy a file in `tests/scenarios/`, give it the next ID (e.g. `P16.yaml`), list the answers
that differ from `base_project.yaml` and the `expected` result. Write amounts in quotes
(`"100000.00"`). `python -m pytest tests/test_scenarios.py -v` runs it.

---

## 7. Deploy online (Streamlit Community Cloud)

1. Push the code to GitHub.
2. Go to <https://share.streamlit.io>, sign in with GitHub and choose **Create app**.
3. Repository `naomifeldmann777/Project_LegalTech`, the branch to publish, main file `app.py`;
   under **Advanced settings** choose Python **3.12**. Click **Deploy**.
4. Share the app URL. Every push to that branch updates the app automatically.

Use fictional data only: what is typed into the hosted app is processed on Streamlit's servers.

---

## 8. Documents and team

The legal specification (legal handoff), the diagrams (flowcharts, ER diagram), the
10-week plan, the contract skeleton and the law student's decision packet are kept by
the team outside this repository. Decisions and open questions are recorded in
`docs/decision_log.md`.

Team: one law student and two business informatics students (master course, Legal Tech).
