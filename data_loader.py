"""data_loader.py - reads the four YAML files of the knowledge base and checks them.

What this file is for:
    The legal knowledge of the app lives in four YAML files in data/:
    sources.yaml, parameters.yaml, clauses.yaml and rules.yaml.
    This module reads them into Python and checks them for mistakes (typos in
    IDs, missing texts, wrong references between the files) BEFORE the engine
    uses them. A mistake stops the app at once with a clear message, instead of
    silently producing a wrong contract.

How it fits into the project:
    engine.py and app.py call load_knowledge() once and use the result.
    The result is a dictionary; each part is itself a dictionary {ID: entry}:
        knowledge["fields"]["contract_price"]   -> the field from parameters.yaml
        knowledge["clauses"]["PRICE_FIXED"]     -> the clause from clauses.yaml
        knowledge["rules"]["R_PRICE"]           -> the rule from rules.yaml
    This module does not import Streamlit and contains no rule logic.

Which documents it implements:
    - AI_PROMPT step 6: unique IDs, one SEL_ rule per clause, every placeholder
      is a field or a derived placeholder, every citation exists, clear errors
    - Legal handoff App. C: "Missing metadata is a PRODUCT error"
    - Decisions D6 (condition format), D10, D16, D40, D42 (clause and rule format)

What it does NOT check:
    Whether the "check" names in rules.yaml exist in checks.py. engine.py does
    that, because this module only looks at the data files.

Quick check from the terminal (prints "OK" or the list of mistakes):
    python data_loader.py
"""

from datetime import date  # the type PyYAML uses for dates written like 2026-01-01
from decimal import Decimal  # exact numbers for money and percentages (never float)
from pathlib import Path  # builds file paths that work on macOS, Windows and Linux
import re  # regular expressions: used to find the {placeholders} in clause texts

import yaml  # PyYAML: turns YAML files into Python dictionaries and lists


# ---------------------------------------------------------------------------
# Fixed values used by the checks below
# ---------------------------------------------------------------------------

# folder that holds the four YAML files: "data" next to this Python file
DEFAULT_DATA_DIR = Path(__file__).parent / "data"

# data types a field may have (see the list at the top of parameters.yaml)
FIELD_TYPES = {"date", "enum", "boolean", "text", "long_text", "decimal_chf", "decimal_percent", "integer", "list"}

# a column inside a list may have every type except "list" (no tables inside tables)
COLUMN_TYPES = FIELD_TYPES - {"list"}

# condition operators that compare the answer with a "value" (decision D6)
OPERATORS_WITH_VALUE = {"equals", "not_equals", "less_than", "at_most", "greater_than", "at_least", "one_of"}

# condition operators that only look at whether there is an answer at all
OPERATORS_WITHOUT_VALUE = {"is_empty", "is_filled"}

# what the THEN part of a rule does (handoff App. C, diagrams PDF ch. 8)
RULE_TYPES = {"select", "require", "error", "warning"}

# engine steps a rule can belong to (diagrams PDF ch. 2; step 4 has no rules of its own)
RULE_STEPS = {1, 2, 3, 5}

# why an R_ or W_ rule exists: mandatory law or a need of the app (handoff App. C)
CATEGORIES = {"LAW", "PRODUCT"}

# safety flags every clause must declare (handoff App. C, "Validators read reviewed metadata")
METADATA_FLAGS = (
    "notices_preserved",  # defect notice periods are not shortened
    "limitation_preserved",  # the 5-year limitation is not shortened
    "free_repair_preserved",  # free repair is not restricted
    "judicial_reduction_preserved",  # a court can still reduce an excessive penalty
    "own_intent_gross_preserved",  # liability for intent and gross negligence is not limited
    "statutory_exit_preserved",  # statutory termination routes stay available
)  # end of the list of flags

# finds placeholders like {contract_price} in a clause text; the name inside the braces is captured
PLACEHOLDER_PATTERN = re.compile(r"\{(\w+)\}")


class DataError(Exception):
    """Raised when a data file is missing, cannot be read or contains mistakes.

    The message lists every mistake found, one per line, so they can all be
    fixed at once.
    """


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def load_knowledge(data_dir=None):
    """Read the four YAML files, check them and return the knowledge base.

    Parameters:
        data_dir: folder with sources.yaml, parameters.yaml, clauses.yaml and
            rules.yaml. None (the default) means the "data" folder next to this
            file. Tests can pass another folder with changed copies of the files.

    Returns:
        A dictionary with the parts law_version, sources, citations, sections,
        fields, topics, slots, clauses, derived_placeholders and rules. Every
        part except law_version is a dictionary {ID: entry}, in file order.

    Raises:
        DataError: if a file is missing or unreadable, or if any check fails.

    Example:
        knowledge = load_knowledge()
        knowledge["clauses"]["PRICE_FIXED"]["version"]   # -> "1.1"
    """
    folder = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR  # the folder to read from
    problems = []  # every mistake found is added to this list as one sentence

    # read the four files; a missing file or a YAML syntax error stops here at once
    sources_file = _read_yaml(folder / "sources.yaml")  # legal sources and citations
    parameters_file = _read_yaml(folder / "parameters.yaml")  # questionnaire sections and fields
    clauses_file = _read_yaml(folder / "clauses.yaml")  # topics, slots, clauses, derived texts
    rules_file = _read_yaml(folder / "rules.yaml")  # the rules

    # turn every list of entries into a dictionary {ID: entry}; duplicate IDs are reported
    knowledge = {
        "law_version": sources_file.get("law_version"),  # e.g. "2026-10-01"
        "sources": _index(sources_file, "sources", "sources.yaml", problems),  # S1, S2, S4
        "citations": _index(sources_file, "citations", "sources.yaml", problems),  # CO_363, ...
        "sections": _index(parameters_file, "sections", "parameters.yaml", problems),  # questionnaire blocks
        "fields": _index(parameters_file, "fields", "parameters.yaml", problems),  # the questions
        "topics": _index(clauses_file, "topics", "clauses.yaml", problems),  # PRICE_PAYMENT
        "slots": _index(clauses_file, "slots", "clauses.yaml", problems),  # price_clause, payment_clause
        "clauses": _index(clauses_file, "clauses", "clauses.yaml", problems),  # the clause library
        "derived_placeholders": _index(clauses_file, "derived_placeholders", "clauses.yaml", problems),  # built texts
        "rules": _index(rules_file, "rules", "rules.yaml", problems),  # the rules
    }  # end of the knowledge base

    # check every part; the checks only add to "problems", they never stop early
    _check_sources(knowledge, problems)  # sources.yaml
    _check_parameters(knowledge, problems)  # parameters.yaml
    _check_clauses(knowledge, problems)  # clauses.yaml
    _check_rules(knowledge, problems)  # rules.yaml, including "one SEL_ rule per clause"

    if problems:  # at least one mistake was found
        raise DataError("The data files contain mistakes:\n- " + "\n- ".join(problems))  # one mistake per line
    return knowledge  # everything is fine


# ---------------------------------------------------------------------------
# Reading the files
# ---------------------------------------------------------------------------

def _read_yaml(path):
    """Read one YAML file and return its content as a dictionary.

    Raises DataError if the file is missing, has a YAML syntax error, or does
    not contain named sections (a dictionary) at the top level.
    """
    if not path.exists():  # the file is not there at all
        raise DataError(f"{path.name}: file not found in {path.parent}")  # stop with a clear message
    try:  # reading can fail because of a syntax error
        with path.open(encoding="utf-8") as file:  # UTF-8 so that characters like ’ and – are read correctly
            content = yaml.safe_load(file)  # safe_load only builds plain data, it never runs code
    except yaml.YAMLError as error:  # PyYAML found a syntax error, e.g. wrong indentation
        raise DataError(f"{path.name}: YAML syntax error: {error}") from error  # pass PyYAML's details on
    if not isinstance(content, dict):  # an empty file gives None, a file with only a list gives a list
        raise DataError(f"{path.name}: the file must contain named sections such as 'rules:'")  # say what is expected
    return content  # the file as a Python dictionary


def _index(content, key, file_name, problems):
    """Return the list content[key] as a dictionary {ID: entry}.

    Reports a missing section, entries without "id" and IDs used twice.
    Example: [{"id": "S1", ...}, {"id": "S2", ...}] -> {"S1": {...}, "S2": {...}}
    """
    entries = content.get(key)  # the list under this key; None if the key is missing
    if not isinstance(entries, list):  # missing, or not written as a list
        problems.append(f"{file_name}: section '{key}' is missing or is not a list")  # report it
        return {}  # continue with nothing, so the other checks can still run
    index = {}  # the result: ID -> entry, in file order
    for position, entry in enumerate(entries, start=1):  # position 1, 2, 3 ... for the messages
        entry_id = entry.get("id") if isinstance(entry, dict) else None  # the entry's ID, if it has one
        if not entry_id:  # no ID, or the entry is not a dictionary
            problems.append(f"{file_name}, {key}, entry {position}: 'id' is missing")  # report it
        elif entry_id in index:  # the same ID appeared earlier
            problems.append(f"{file_name}, {key}: ID '{entry_id}' is used twice")  # IDs must be unique
        else:  # a new ID
            index[entry_id] = entry  # remember the entry under its ID
    return index  # dictionary {ID: entry}


# ---------------------------------------------------------------------------
# Small helpers used by several checks
# ---------------------------------------------------------------------------

def _require_text(entry, keys, where, problems):
    """Report every key in "keys" whose value is not a non-empty text.

    Example: a clause without "title" gives "clauses.yaml, clause X: 'title' ...".
    """
    for key in keys:  # look at each required key
        value = entry.get(key)  # None if the key is missing
        if not isinstance(value, str) or not value.strip():  # missing, empty, or a number instead of text
            problems.append(f"{where}: '{key}' must be a non-empty text (write numbers like versions in quotes)")  # report


def _check_citations(citation_ids, knowledge, where, problems):
    """Report a "citations" value that is not a list, or that names an unknown citation."""
    if not isinstance(citation_ids, list):  # e.g. the key is missing
        problems.append(f"{where}: 'citations' must be a list (write [] for none)")  # say how to fix it
        return  # nothing more to check
    for citation_id in citation_ids:  # each citation ID used by the clause or rule
        if citation_id not in knowledge["citations"]:  # not defined in sources.yaml
            problems.append(f"{where}: unknown citation '{citation_id}' (not in sources.yaml)")  # report it


def _allowed_values(knowledge, field_id):
    """Return the set of allowed answers of an enum field, or None if the field is not an enum.

    Example: _allowed_values(knowledge, "price_type") -> {"fixed", "estimate"}
    """
    field = knowledge["fields"].get(field_id)  # the field, or None if it does not exist
    if field is None or field.get("type") != "enum":  # unknown field, or not an enum
        return None  # there is no list of allowed answers
    return {option.get("value") for option in field.get("allowed_values") or []}  # the stored values


# ---------------------------------------------------------------------------
# Checking conditions ("when" and "active_when", decision D6)
# ---------------------------------------------------------------------------

def _check_condition(condition, knowledge, where, problems):
    """Check one condition written in the structured YAML format.

    Allowed forms: {always: true}, {all: [...]}, {any: [...]}, {not: {...}},
    {field: X, op: OP, value: V} and {field: X, op: is_empty / is_filled}.
    Conditions inside all / any / not are checked the same way.
    """
    if not isinstance(condition, dict):  # missing, or not written as {...}
        problems.append(f"{where}: the condition must be written as {{...}}")  # report it
        return  # nothing more to check
    if "always" in condition:  # the form {always: true}
        if condition != {"always": True}:  # anything else next to it, or "always: false"
            problems.append(f"{where}: write {{always: true}} on its own")  # report it
        return  # done
    for combinator in ("all", "any"):  # the two list forms (AND, OR)
        if combinator in condition:  # this form is used
            parts = condition[combinator]  # the list of conditions inside it
            if len(condition) != 1 or not isinstance(parts, list) or not parts:  # wrong form
                problems.append(f"{where}: '{combinator}' needs a non-empty list and nothing else")  # report it
                return  # cannot check the parts
            for number, part in enumerate(parts, start=1):  # check each condition in the list
                _check_condition(part, knowledge, f"{where}, {combinator} item {number}", problems)  # same check again
            return  # done
    if "not" in condition:  # the form {not: {...}}
        if len(condition) != 1:  # something else next to "not"
            problems.append(f"{where}: 'not' must be written on its own")  # report it
        _check_condition(condition["not"], knowledge, f"{where}, not", problems)  # check the inner condition
        return  # done
    _check_comparison(condition, knowledge, where, problems)  # remaining form: {field, op, value}


def _check_comparison(condition, knowledge, where, problems):
    """Check a {field, op, value} condition and convert its value to the field's type.

    Numbers for money and percentages become Decimal, so the engine never
    compares money with a float.
    """
    field_id = condition.get("field")  # the field the condition looks at
    field = knowledge["fields"].get(field_id)  # its definition from parameters.yaml
    if field is None:  # typo or unknown field
        problems.append(f"{where}: unknown field '{field_id}' (not in parameters.yaml)")  # report it
        return  # cannot check the rest
    op = condition.get("op")  # the operator, e.g. "equals"
    if op in OPERATORS_WITHOUT_VALUE:  # is_empty / is_filled
        if "value" in condition:  # these operators do not use a value
            problems.append(f"{where}: '{op}' takes no value")  # report it
        return  # done
    if op not in OPERATORS_WITH_VALUE:  # typo or unknown operator
        problems.append(f"{where}: unknown operator '{op}'")  # report it
        return  # cannot check the value
    if "value" not in condition:  # the operator needs something to compare with
        problems.append(f"{where}: '{op}' needs a value")  # report it
        return  # nothing to convert
    if op == "one_of":  # "one_of" compares with a list of values
        if not isinstance(condition["value"], list):  # but no list was given
            problems.append(f"{where}: 'one_of' needs a list of values")  # report it
            return  # cannot convert
        condition["value"] = [_convert_value(v, field, where, problems) for v in condition["value"]]  # convert each
    else:  # every other operator compares with one value
        condition["value"] = _convert_value(condition["value"], field, where, problems)  # convert it


def _convert_value(value, field, where, problems):
    """Check that a condition value fits the field's type and return it in the right Python type.

    Example: for contract_price (decimal_chf) the YAML value 0 becomes Decimal("0").
    """
    field_type = field.get("type")  # the field's data type from parameters.yaml
    if field_type == "enum":  # one answer from a fixed list
        allowed = {option.get("value") for option in field.get("allowed_values") or []}  # the allowed answers
        if value not in allowed:  # catches typos such as "estimat"
            problems.append(f"{where}: '{value}' is not an allowed answer of {field['id']} {sorted(allowed)}")  # report
        return value  # enum values stay text
    if field_type == "boolean":  # yes / no
        if not isinstance(value, bool):  # must be written true or false
            problems.append(f"{where}: the value for {field['id']} must be true or false")  # report it
        return value  # stays True / False
    if field_type == "date":  # a calendar date
        if not isinstance(value, date):  # PyYAML gives a date only for unquoted values like 2026-01-01
            problems.append(f"{where}: the value for {field['id']} must be a date like 2026-01-01 (no quotes)")  # report
        return value  # stays a date
    if field_type in ("decimal_chf", "decimal_percent", "integer"):  # numbers
        if isinstance(value, bool) or not isinstance(value, (int, float)):  # True/False count as numbers in Python
            problems.append(f"{where}: the value for {field['id']} must be a number")  # report it
            return value  # cannot convert
        if field_type == "integer":  # whole numbers stay int
            return value  # e.g. 30
        return Decimal(str(value))  # str() first, so 0.1 becomes exactly Decimal("0.1") and not a float error
    if field_type in ("text", "long_text"):  # free text
        if not isinstance(value, str):  # must be text
            problems.append(f"{where}: the value for {field['id']} must be text")  # report it
        return value  # stays text
    problems.append(f"{where}: {field['id']} (type {field_type}) cannot be compared; use is_empty / is_filled")  # lists
    return value  # unchanged


# ---------------------------------------------------------------------------
# Checks per file
# ---------------------------------------------------------------------------

def _check_sources(knowledge, problems):
    """Check sources.yaml: law_version, sources and citations."""
    if not isinstance(knowledge["law_version"], str):  # must be text such as "2026-10-01"
        problems.append('sources.yaml: \'law_version\' must be text in quotes, e.g. "2026-10-01"')  # report it
    for source_id, source in knowledge["sources"].items():  # each source (S1, S2, S4)
        _require_text(source, ("title", "url"), f"sources.yaml, source {source_id}", problems)  # needs a title and a link
        reading_aid = source.get("reading_aid")  # optional link to another source
        if reading_aid is not None and reading_aid not in knowledge["sources"]:  # points to an unknown source
            problems.append(f"sources.yaml, source {source_id}: reading_aid '{reading_aid}' is not a known source")  # report
    for citation_id, citation in knowledge["citations"].items():  # each citation (CO_363, ...)
        where = f"sources.yaml, citation {citation_id}"  # location used in the messages
        _require_text(citation, ("article", "label"), where, problems)  # needs an article and a display label
        if citation.get("source") not in knowledge["sources"]:  # must point to S1, S2 or S4
            problems.append(f"{where}: source '{citation.get('source')}' is not a known source")  # report it


def _check_parameters(knowledge, problems):
    """Check parameters.yaml: sections and fields, including list columns and active_when."""
    for section_id, section in knowledge["sections"].items():  # each questionnaire section
        _require_text(section, ("title",), f"parameters.yaml, section {section_id}", problems)  # needs a heading
    for field_id, field in knowledge["fields"].items():  # each field
        where = f"parameters.yaml, field {field_id}"  # location used in the messages
        if field.get("section") not in knowledge["sections"]:  # must belong to a known section
            problems.append(f"{where}: unknown section '{field.get('section')}'")  # report it
        _check_field_definition(field, FIELD_TYPES, where, knowledge, problems)  # type, question, required, answers
        if field.get("type") == "list":  # a table: check its columns too
            columns = _index(field, "columns", where, problems)  # columns as {ID: column}
            for column_id, column in columns.items():  # each column
                _check_field_definition(column, COLUMN_TYPES, f"{where}, column {column_id}", knowledge, problems)  # same
        if "active_when" in field:  # the field is only shown under a condition
            _check_condition(field["active_when"], knowledge, f"{where}, active_when", problems)  # check the condition
        checked_by = field.get("checked_by")  # rule that reports this field instead of R_REQUIRED (D16)
        if checked_by is not None and checked_by not in knowledge["rules"]:  # must be a known rule
            problems.append(f"{where}: checked_by '{checked_by}' is not a rule in rules.yaml")  # report it
        depends_on = field.get("question_depends_on")  # optional: the question text changes with another answer
        if depends_on is not None:  # this field uses question variants
            allowed = _allowed_values(knowledge, depends_on)  # the answers of the other field
            if allowed is None:  # the other field is unknown or not an enum
                problems.append(f"{where}: question_depends_on '{depends_on}' must be an enum field")  # report it
            elif set(field.get("question_variants") or {}) != allowed:  # one question per answer is needed
                problems.append(f"{where}: question_variants needs exactly one question for each of {sorted(allowed)}")  # report


def _check_field_definition(definition, allowed_types, where, knowledge, problems):
    """Check what every field and every list column needs: type, question, required, enum answers."""
    field_type = definition.get("type")  # e.g. "enum"
    if field_type not in allowed_types:  # typo, or a list inside a list
        problems.append(f"{where}: unknown or not allowed type '{field_type}'")  # report it
    _require_text(definition, ("question",), where, problems)  # every field needs a question
    if not isinstance(definition.get("required"), bool):  # must be written true or false
        problems.append(f"{where}: 'required' must be true or false")  # report it
    if field_type == "enum":  # enums need their list of answers
        options = definition.get("allowed_values") or []  # the answers, or an empty list
        values = [option.get("value") for option in options]  # only the stored values
        if not values:  # no answers at all
            problems.append(f"{where}: an enum needs 'allowed_values'")  # report it
        if len(values) != len(set(values)):  # the same value written twice
            problems.append(f"{where}: an allowed value is listed twice")  # report it
        for option in options:  # each answer needs a text for the app
            _require_text(option, ("label",), f"{where}, value {option.get('value')}", problems)  # check the label


def _check_clauses(knowledge, problems):
    """Check clauses.yaml: topics, slots, derived placeholders and clauses."""
    for topic_id, topic in knowledge["topics"].items():  # each topic
        _require_text(topic, ("name",), f"clauses.yaml, topic {topic_id}", problems)  # needs a name
        if not isinstance(topic.get("order_in_contract"), int):  # position on the review screen
            problems.append(f"clauses.yaml, topic {topic_id}: 'order_in_contract' must be a whole number")  # report it
    for slot_id, slot in knowledge["slots"].items():  # each slot of the Word template
        low, high = slot.get("min"), slot.get("max")  # how many clauses the slot needs
        if not (isinstance(low, int) and isinstance(high, int) and 0 <= low <= high):  # must be 0 <= min <= max
            problems.append(f"clauses.yaml, slot {slot_id}: 'min' and 'max' must be whole numbers with 0 <= min <= max")  # report
    _check_derived_placeholders(knowledge, problems)  # the built texts
    for clause_id, clause in knowledge["clauses"].items():  # each clause
        _check_clause(clause_id, clause, knowledge, problems)  # all checks of one clause


def _check_derived_placeholders(knowledge, problems):
    """Check the derived placeholders: names, the fields they are built from, one text per answer."""
    for placeholder_id, placeholder in knowledge["derived_placeholders"].items():  # each derived placeholder
        where = f"clauses.yaml, derived placeholder {placeholder_id}"  # location used in the messages
        if placeholder_id in knowledge["fields"]:  # the name would be ambiguous
            problems.append(f"{where}: has the same name as a field in parameters.yaml")  # report it
        built_from = placeholder.get("built_from") or []  # the fields it is built from
        for field_id in built_from:  # each of them must exist
            if field_id not in knowledge["fields"]:  # unknown field
                problems.append(f"{where}: built_from field '{field_id}' is not in parameters.yaml")  # report it
        chosen_by = placeholder.get("chosen_by")  # the answer that chooses the text
        if chosen_by not in built_from:  # must be one of the fields above
            problems.append(f"{where}: chosen_by '{chosen_by}' must also be listed in built_from")  # report it
        allowed = _allowed_values(knowledge, chosen_by)  # the answers of that field
        texts = placeholder.get("text_by_answer") or placeholder.get("row_by_answer") or {}  # one text per answer
        if allowed is None:  # chosen_by is unknown or not an enum
            problems.append(f"{where}: chosen_by '{chosen_by}' must be an enum field")  # report it
        elif set(texts) != allowed:  # a text is missing, or there is a text for an unknown answer
            problems.append(f"{where}: needs exactly one text for each answer of {chosen_by}: {sorted(allowed)}")  # report


def _check_clause(clause_id, clause, knowledge, problems):
    """Check one clause: texts, topic, slot, placeholders, citations and metadata flags."""
    where = f"clauses.yaml, clause {clause_id}"  # location used in the messages
    _require_text(clause, ("title", "version", "text"), where, problems)  # needs a title, a version and a text
    if clause.get("topic") not in knowledge["topics"]:  # must belong to a known topic
        problems.append(f"{where}: unknown topic '{clause.get('topic')}'")  # report it
    if clause.get("slot") not in knowledge["slots"]:  # must go into a known slot of the Word template
        problems.append(f"{where}: unknown slot '{clause.get('slot')}'")  # report it
    inputs = clause.get("inputs")  # the placeholders the clause declares
    if not isinstance(inputs, list):  # must be a list, [] for none
        problems.append(f"{where}: 'inputs' must be a list (write [] for none)")  # report it
        inputs = []  # continue with an empty list
    text = clause.get("text") if isinstance(clause.get("text"), str) else ""  # the clause text, or "" if missing
    used = set(PLACEHOLDER_PATTERN.findall(text))  # every {name} that appears in the text
    for name in sorted(used - set(inputs)):  # in the text but not declared
        problems.append(f"{where}: placeholder {{{name}}} is in the text but not in 'inputs'")  # report it
    for name in inputs:  # each declared placeholder
        if name not in used:  # declared but never used
            problems.append(f"{where}: input '{name}' is listed but not used in the text")  # report it
        if name not in knowledge["fields"] and name not in knowledge["derived_placeholders"]:  # nothing can fill it
            problems.append(f"{where}: input '{name}' is neither a field nor a derived placeholder")  # report it
    _check_citations(clause.get("citations"), knowledge, where, problems)  # legal basis must exist
    metadata = clause.get("metadata") or {}  # the safety flags, or nothing
    for flag in METADATA_FLAGS:  # each of the six required flags
        if not isinstance(metadata.get(flag), bool):  # missing or not true/false
            problems.append(f"{where}: metadata flag '{flag}' is missing or not true/false (handoff App. C)")  # report it


def _check_rules(knowledge, problems):
    """Check rules.yaml and that every clause is selected by exactly one SEL_ rule."""
    selected_by = {}  # clause ID -> list of SEL_ rule IDs that select it
    for rule_id, rule in knowledge["rules"].items():  # each rule
        where = f"rules.yaml, {rule_id}"  # location used in the messages
        if rule.get("type") not in RULE_TYPES:  # typo or unknown type
            problems.append(f"{where}: unknown type '{rule.get('type')}'")  # report it
            continue  # the other checks depend on the type
        if rule.get("step") not in RULE_STEPS:  # must be 1, 2, 3 or 5
            problems.append(f"{where}: 'step' must be one of {sorted(RULE_STEPS)}")  # report it
        _require_text(rule, ("version",), where, problems)  # every rule has a version (handoff App. E)
        topic = rule.get("topic")  # null means "whole project"
        if topic is not None and topic not in knowledge["topics"]:  # must be a known topic
            problems.append(f"{where}: unknown topic '{topic}'")  # report it
        if rule["type"] == "select":  # SEL_ rules add a clause
            _check_select_rule(rule_id, rule, knowledge, where, problems, selected_by)  # checks for SEL_ rules
        else:  # R_ and W_ rules show a message
            _check_message_rule(rule_id, rule, knowledge, where, problems)  # checks for R_ and W_ rules
    for clause_id in knowledge["clauses"]:  # each clause in the library
        count = len(selected_by.get(clause_id, []))  # how many SEL_ rules select it
        if count != 1:  # none (the clause can never appear) or several (unclear reason)
            problems.append(f"clauses.yaml, clause {clause_id}: needs exactly one SEL_ rule, found {count}")  # report


def _check_select_rule(rule_id, rule, knowledge, where, problems, selected_by):
    """Check one SEL_ rule: its clause, its ID, its condition and its reason."""
    clause_id = rule.get("clause")  # the clause the rule adds
    if clause_id not in knowledge["clauses"]:  # must be in clauses.yaml
        problems.append(f"{where}: unknown clause '{clause_id}'")  # report it
    elif rule_id != f"SEL_{clause_id}":  # handoff App. C: the rule ID is SEL_ + clause ID
        problems.append(f"{where}: the ID must be SEL_{clause_id} (handoff App. C)")  # report it
    selected_by.setdefault(clause_id, []).append(rule_id)  # remember which rule selects which clause
    _check_condition(rule.get("when"), knowledge, f"{where}, when", problems)  # check the condition
    _require_text(rule, ("reason",), where, problems)  # the review screen needs a reason


def _check_message_rule(rule_id, rule, knowledge, where, problems):
    """Check one R_ or W_ rule: ID prefix, category, citations and every case."""
    prefix = "W_" if rule["type"] == "warning" else "R_"  # warnings start with W_, errors with R_
    if not rule_id.startswith(prefix):  # ID and type do not match
        problems.append(f"{where}: a rule of type '{rule['type']}' must have an ID starting with {prefix}")  # report it
    if rule.get("category") not in CATEGORIES:  # must be LAW or PRODUCT
        problems.append(f"{where}: 'category' must be LAW or PRODUCT")  # report it
    _check_citations(rule.get("citations"), knowledge, where, problems)  # legal basis must exist
    cases = rule.get("cases")  # the ways the rule can fire
    if not isinstance(cases, list) or not cases:  # at least one case is needed
        problems.append(f"{where}: 'cases' must be a non-empty list")  # report it
        return  # nothing more to check
    for number, case in enumerate(cases, start=1):  # each case: 1, 2, 3 ...
        case_where = f"{where}, case {number}"  # location used in the messages
        if not isinstance(case, dict):  # each case must be written as a dictionary
            problems.append(f"{case_where}: must contain 'when' and 'field' or 'check'")  # report it
            continue  # go to the next case
        _check_condition(case.get("when"), knowledge, f"{case_where}, when", problems)  # check the condition
        check = case.get("check")  # optional name of a special check in checks.py (D42)
        if check is not None and (not isinstance(check, str) or not check.strip()):  # must be a name
            problems.append(f"{case_where}: 'check' must be the name of a function in checks.py")  # report it
        field_id = case.get("field")  # the question the message is shown next to
        if check is None and field_id is not None and field_id not in knowledge["fields"]:  # unknown field
            problems.append(f"{case_where}: unknown field '{field_id}'")  # report it
        if not (case.get("message") or rule.get("message")):  # no text to show the user
            problems.append(f"{case_where}: no message (set 'message' on the rule or on the case)")  # report it


# ---------------------------------------------------------------------------
# Quick check from the terminal
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # only runs when started directly: python data_loader.py
    try:  # loading can fail with a DataError
        loaded = load_knowledge()  # read and check the default data folder
    except DataError as error:  # at least one mistake was found
        print(error)  # show the list of mistakes
        raise SystemExit(1)  # end with exit code 1, which means "failed"
    print(  # everything is fine: print a short summary
        f"All data files are OK: {len(loaded['fields'])} fields, {len(loaded['clauses'])} clauses, "  # first part
        f"{len(loaded['rules'])} rules, {len(loaded['citations'])} citations."  # second part
    )  # end of the summary
