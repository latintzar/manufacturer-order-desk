#!/usr/bin/env python3
"""Check a company's questionnaire against its catalogue, at build time.

    python3 pipeline/ask.py <company>      print the questions, the paths and the articles they reach

A questionnaire is data under `"questionnaire"` in company.json; `widget/README.md` documents it and
`widget/ask.js` runs it. This file holds the same rules in Python and walks every path a customer can
take. The build stops with one sentence when the data names an unknown id, a question nobody can reach,
an option that matches no article or is never offered, a result group without articles, or a path that
ends with no article.

The rules, shared with ask.js:
  when    a question, an option or a result group shows when every question it names holds one of
          the listed options ("?" stands for the unsure choice)
  match   a row stays unless it carries the attribute with none of the listed values; the chosen
          options of a multiple-choice question widen, never narrow each other
  offer   an option is offered while an article left carries one of its values and every result
          group it leads to still holds an article
  auto    a question with one offered option answers itself; one with none is passed over

Reads   companies/<slug>/company.json and the catalogue the build made
Writes  nothing
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

UNSURE = "?"
KINDS = ("single", "multiple")
SHOWS = ("rows", "cells", "tiles")
DRAWINGS = ("hole-pz", "hole-bb", "hole-wc", "lever", "knob", "backset", "centres", "measures")   # ask.js GLYPH and DRAW


class Invalid(ValueError):
    """The questionnaire and the catalogue disagree; the message is one sentence."""


def listed(value) -> list:
    return value if isinstance(value, list) else [] if value is None else [value]


def rows(catalogue: dict) -> list[dict]:
    """Every catalogue item that carries attributes, with its group and its type."""
    return [{"c": item["c"], "a": item["a"], "form": category["form"], "type": category["code"]}
            for category in catalogue["cats"] for item in category["items"] if item.get("a")]


def when_ok(when: dict | None, answers: dict) -> bool:
    return not when or all(any(choice in allowed for choice in answers.get(question, ()))
                           for question, allowed in when.items())


def keeps(row: dict, match: dict | None) -> bool:
    return not match or all(row["a"].get(key) is None or any(value in allowed for value in listed(row["a"][key]))
                            for key, allowed in match.items())


def has(row: dict, key: str, allowed: list) -> bool:
    """The row carries this attribute with one of the listed values."""
    return row["a"].get(key) is not None and any(value in allowed for value in listed(row["a"][key]))


def option(question: dict, choice: str) -> dict:
    return next(o for o in question["options"] if o["id"] == choice)


def narrow(left: list[dict], question: dict, chosen: list[str]) -> list[dict]:
    if chosen[0] == UNSURE:
        return left
    matches = [option(question, choice).get("match") for choice in chosen]
    return [row for row in left if any(keeps(row, match) for match in matches)]


def in_group(row: dict, group: dict) -> bool:
    return row["form"] in listed(group["category"]) or row["type"] in listed(group["category"])


def groups(definition: dict, answers: dict, decided_only: bool = False) -> list[dict]:
    found = []
    for group in definition["result"]["groups"]:
        when = group.get("when")
        if decided_only and when and any(question not in answers for question in when):
            continue
        if when_ok(when, answers):
            found.append(group)
    return found


def live(definition: dict, left: list[dict], answers: dict, question: dict) -> list[dict]:
    offered = []
    for choice in question["options"]:
        if not when_ok(choice.get("when"), answers):
            continue
        match = choice.get("match")
        after = [row for row in left if keeps(row, match)]
        then = {**answers, question["id"]: [choice["id"]]}
        if match and not any(has(row, key, allowed) for row in after for key, allowed in match.items()):
            continue
        if all(any(in_group(row, group) for row in after) for group in groups(definition, then, True)):
            offered.append(choice)
    return offered


def walk(definition: dict, all_rows: list[dict], given: dict) -> dict:
    """The questions in order with the stored answers: asked, answered by themselves, and what is left."""
    answers, steps, left, following = {}, [], all_rows, None
    for question in definition["questions"]:
        if not when_ok(question.get("when"), answers):
            continue
        offered = live(definition, left, answers, question)
        if not offered:
            continue
        chosen, auto = None, False
        if len(offered) == 1:
            chosen, auto = [offered[0]["id"]], True
        else:
            stored = listed(given.get(question["id"]))
            if stored[:1] == [UNSURE]:
                chosen = [UNSURE] if question.get("unsure") else None
            else:
                kept = [choice for choice in stored if any(o["id"] == choice for o in offered)]
                if kept:
                    chosen = kept if question["kind"] == "multiple" else kept[:1]
        steps.append({"q": question, "live": offered, "ids": chosen, "auto": auto})
        if not chosen:
            following = question
            break
        answers[question["id"]] = chosen
        left = narrow(left, question, chosen)
    return {"steps": steps, "answers": answers, "rows": left, "next": following}


def result(definition: dict, walked: dict) -> list[dict]:
    """Per visible group its articles, best first: the rows that carry the most of what was asked."""
    asked = [option(step["q"], choice).get("match") for step in walked["steps"] if step["ids"]
             for choice in step["ids"] if choice != UNSURE]
    asked = [match for match in asked if match]

    def score(row: dict) -> int:
        return sum(1 for match in asked for key, allowed in match.items() if has(row, key, allowed))

    found = []
    for group in groups(definition, walked["answers"]):
        inside = [row for row in walked["rows"] if in_group(row, group)]
        ranked = [row for _, _, row in sorted(((-score(row), index, row) for index, row in enumerate(inside)),
                                              key=lambda entry: entry[:2])]
        if ranked:
            found.append({"group": group, "rows": ranked})
    return found


def _words(value, where: str) -> None:
    if not isinstance(value, dict) or not value.get("bg"):
        raise Invalid(f"{where} needs its words as {{\"bg\": …, \"en\": …}}.")


def static(definition: dict, all_rows: list[dict], catalogue: dict, pictures: set[str] | None) -> None:
    for key in ("id", "title", "start", "questions", "result"):
        if not definition.get(key):
            raise Invalid(f"The questionnaire needs \"{key}\".")
    _words(definition["title"], "The questionnaire's title")
    _words(definition["start"], "The questionnaire's start button")
    carried: dict[str, set] = {}
    for row in all_rows:
        for key, value in row["a"].items():
            carried.setdefault(key, set()).update(listed(value))
    seen: dict[str, dict] = {}

    def check_when(when, where: str) -> None:
        for question, allowed in (when or {}).items():
            if question not in seen:
                raise Invalid(f"{where} depends on \"{question}\", which is not an earlier question.")
            known = {o["id"] for o in seen[question]["options"]} | ({UNSURE} if seen[question].get("unsure") else set())
            unknown = [choice for choice in allowed if choice not in known]
            if unknown:
                raise Invalid(f"{where} depends on \"{unknown[0]}\", which is not an option of \"{question}\".")

    for question in definition["questions"]:
        name = question.get("id")
        where = f"Question \"{name}\""
        if not name or name in seen:
            raise Invalid(f"{where} needs an id of its own.")
        if question.get("kind") not in KINDS:
            raise Invalid(f"{where} is \"single\" or \"multiple\".")
        if question.get("show", "rows") not in SHOWS:
            raise Invalid(f"{where} shows as rows, cells or tiles.")
        if question.get("draw") and question["draw"] not in DRAWINGS:
            raise Invalid(f"{where} names the drawing \"{question['draw']}\", which the widget does not hold.")
        _words(question.get("title"), where)
        check_when(question.get("when"), where)
        if len(question.get("options") or []) < 2:
            raise Invalid(f"{where} needs at least two options.")
        ids = set()
        for choice in question["options"]:
            spot = f"Option \"{choice.get('id')}\" of \"{name}\""
            if not choice.get("id") or choice["id"] in ids or choice["id"] == UNSURE:
                raise Invalid(f"{spot} needs an id of its own.")
            ids.add(choice["id"])
            _words(choice.get("label"), spot)
            check_when(choice.get("when"), spot)
            if choice.get("draw") and choice["draw"] not in DRAWINGS:
                raise Invalid(f"{spot} names the drawing \"{choice['draw']}\", which the widget does not hold.")
            if choice.get("picture") and pictures is not None and choice["picture"].lstrip("/") not in pictures:
                raise Invalid(f"{spot} shows {choice['picture']}, which is not a picture of the catalogue.")
            for key, allowed in (choice.get("match") or {}).items():
                if key not in carried:
                    raise Invalid(f"{spot} matches on \"{key}\", which no article carries.")
                if not carried[key] & set(allowed):
                    raise Invalid(f"{spot} matches zero articles: no article has \"{key}\" in {allowed}.")
        seen[name] = question
    known = {form["id"] for form in catalogue["forms"]} | {category["code"] for category in catalogue["cats"]}
    if not definition["result"].get("groups"):
        raise Invalid("The result needs at least one group.")
    for group in definition["result"]["groups"]:
        where = f"Result group \"{(group.get('title') or {}).get('bg', '')}\""
        _words(group.get("title"), "A result group")
        unknown = [category for category in listed(group.get("category")) if category not in known]
        if unknown or not group.get("category"):
            raise Invalid(f"{where} names \"{(unknown or [''])[0]}\", which is not a group or a type of the catalogue.")
        check_when(group.get("when"), where)
        if not any(in_group(row, group) for row in all_rows):
            raise Invalid(f"{where} holds no article.")


def paths(definition: dict, all_rows: list[dict]) -> dict:
    """Every path a customer can take. Returns the count, the shortest and longest, and what was reached."""
    questions = definition["questions"]
    index = {id(row): number for number, row in enumerate(all_rows)}
    deciding = {key for question in questions for key in (question.get("when") or {})} \
        | {key for question in questions for choice in question["options"] for key in (choice.get("when") or {})} \
        | {key for group in definition["result"]["groups"] for key in (group.get("when") or {})}
    reached, offered_ever, memo = set(), set(), {}
    trouble: list[str] = []

    def end(left: list[dict], answers: dict, trail: tuple) -> None:
        shown = groups(definition, answers)
        said = ", ".join(f"{question}: {'/'.join(chosen)}" for question, chosen in trail) or "the start"
        if not shown:
            trouble.append(f"The path {said} ends with zero articles: no result group shows.")
        for group in shown:
            if not any(in_group(row, group) for row in left):
                trouble.append(f"The path {said} ends with zero articles in \"{group['title']['bg']}\".")

    def step(at: int, left: list[dict], answers: dict, trail: tuple) -> tuple[int, int, int]:
        while at < len(questions):
            question = questions[at]
            if not when_ok(question.get("when"), answers):
                at += 1
                continue
            offered = live(definition, left, answers, question)
            if not offered:
                at += 1
                continue
            reached.add(question["id"])
            offered_ever.update((question["id"], choice["id"]) for choice in offered)
            if len(offered) == 1:
                chosen = [offered[0]["id"]]
                answers = {**answers, question["id"]: chosen}
                left = narrow(left, question, chosen)
                at += 1
                continue
            key = (at, frozenset(index[id(row)] for row in left),
                   tuple(sorted((name, tuple(chosen)) for name, chosen in answers.items() if name in deciding)))
            if key in memo:
                return memo[key]
            choices = [[choice["id"]] for choice in offered] + ([[UNSURE]] if question.get("unsure") else [])
            total, shortest, longest = 0, 10**9, 0
            for chosen in choices:
                count, low, high = step(at + 1, narrow(left, question, chosen), {**answers, question["id"]: chosen},
                                        trail + ((question["id"], chosen),))
                total, shortest, longest = total + count, min(shortest, low + 1), max(longest, high + 1)
            memo[key] = (total, shortest, longest)
            return memo[key]
        end(left, answers, trail)
        return 1, 0, 0

    total, shortest, longest = step(0, all_rows, {}, ())
    return {"paths": total, "shortest": shortest, "longest": longest, "reached": reached,
            "offered": offered_ever, "trouble": trouble}


def check(config: dict, catalogue: dict, pictures: set[str] | None = None) -> dict | None:
    """Validate the company's questionnaire against its catalogue. None when the company has none."""
    definition = config.get("questionnaire")
    if not definition:
        return None
    try:
        all_rows = rows(catalogue)
        if not all_rows:
            raise Invalid("The catalogue has no article with attributes for the questionnaire to narrow.")
        static(definition, all_rows, catalogue, pictures)
        if definition.get("mode") == "sections":
            # Independent sections remain reachable regardless of previous answers. Each
            # choice must have a source-backed article; combinations are proposal inputs.
            for question in definition["questions"]:
                if not question.get("unsure"):
                    raise Invalid(f"Section \"{question['id']}\" needs an unsure choice.")
                for choice in question["options"]:
                    if not any(keeps(row, choice.get("match")) for row in all_rows):
                        raise Invalid(f"Option \"{choice['id']}\" has no matching article.")
            return {"mode": "sections", "questions": len(definition["questions"]),
                    "paths": 0, "shortest": 0, "longest": len(definition["questions"]), "rows": len(all_rows)}
        walked = paths(definition, all_rows)
        if walked["trouble"]:
            raise Invalid(walked["trouble"][0])
        for question in definition["questions"]:
            if question["id"] not in walked["reached"]:
                raise Invalid(f"Question \"{question['id']}\" is one nobody can reach.")
            for choice in question["options"]:
                if (question["id"], choice["id"]) not in walked["offered"]:
                    raise Invalid(f"Option \"{choice['id']}\" of \"{question['id']}\" is never offered: "
                                  "no path leaves it an article.")
    except Invalid as problem:
        raise SystemExit(f"{config.get('slug', 'company')}: questionnaire: {problem}") from problem
    return {"questions": len(definition["questions"]), "paths": walked["paths"],
            "shortest": walked["shortest"], "longest": walked["longest"], "rows": len(all_rows)}


def line(report: dict | None) -> str:
    if not report:
        return ""
    if report.get("mode") == "sections":
        return f"questionnaire: {report['questions']} independent sections over {report['rows']} articles"
    return (f"questionnaire: {report['questions']} questions over {report['rows']} articles, "
            f"{report['paths']} paths of {report['shortest']} to {report['longest']} asked questions, "
            "every one ending in an article")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    from pipeline import catalog, common

    config = common.company(argv[1])
    made, _, _ = catalog.build(config, common.site_dir(config["slug"]), common.prefix_of(config))
    report = check(config, made, catalog.photos(made, common.prefix_of(config)))
    print(line(report) or f"{config['slug']} has no questionnaire")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
