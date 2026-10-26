import json
import re

from app.enums import TaskType
from app.llm.base import LLMError, LLMProvider

GENERIC_TERMS = ["process", "method", "system"]
GENERIC_DEFINITIONS = [
    "A named storage place for files inside an operating system.",
    "A device that converts digital signals into sound.",
    "A rule that sets the colour scheme of a website.",
]


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, responses: list[str | Exception] | None = None):
        self.responses = list(responses) if responses is not None else None
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.responses is None:
            return json.dumps(self._auto(user), ensure_ascii=False)
        if not self.responses:
            raise LLMError("No scripted responses left")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def _auto(self, user: str) -> dict:
        if "<dictionary>" in user:
            return self._draft(user)
        card = json.loads(re.search(r"<card>\s*(.*?)\s*</card>", user, re.DOTALL).group(1))
        task_type = TaskType(re.search(r"Task type: (\w+)", user).group(1))
        if "<student_answer>" in user:
            answer = re.search(r"<student_answer>\n(.*?)\n</student_answer>", user, re.DOTALL).group(1)
            return self._classify(card, task_type, answer)
        if "<task>" in user:
            task = json.loads(re.search(r"<task>\s*(.*?)\s*</task>", user, re.DOTALL).group(1))
            return self._review(card, task_type, task)
        if task_type == TaskType.GAP_FILL:
            return self._gap_fill(card)
        return self._definition(card)

    def _gap_fill(self, card: dict) -> dict:
        term = card["term"]
        pattern = re.compile(rf"\b{re.escape(term)}\w*", re.IGNORECASE)
        sentence = next(
            (pattern.sub("____", e) for e in card["examples"] if pattern.search(e)),
            "The team discussed ____ during the meeting.",
        )
        distractors = [*([card["contrast_term"]] if card["contrast_term"] else []), *GENERIC_TERMS]
        options = [term, *[d for d in distractors if d.lower() != term.lower()][:3]]
        return {"prompt": sentence, "options": options, "correct_answer": term}

    def _definition(self, card: dict) -> dict:
        definition = card["definition_en"]
        return {
            "prompt": card["term"],
            "options": [definition, *GENERIC_DEFINITIONS],
            "correct_answer": definition,
        }

    def _review(self, card: dict, task_type: TaskType, task: dict) -> dict:
        term = card["term"].lower()
        options = task["options"]
        if task_type == TaskType.GAP_FILL:
            fitting = [o for o in options if o.lower() == term]
        else:
            fitting = [o for o in options if o == card["definition_en"]]
        return {"fitting_options": fitting, "term_meaning_matches": True}

    def _classify(self, card: dict, task_type: TaskType, answer: str) -> dict:
        words = lambda text: {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3}
        if task_type == TaskType.EXPLAIN_MEANING:
            ok = len(words(answer) & words(card["definition_en"])) >= 2
            error = "meaning"
        else:
            ok = card["term"].lower() in answer.lower() and len(answer.split()) >= 4
            error = "usage"
        return {
            "is_correct": ok,
            "error_type": None if ok else error,
            "comment": "Ответ засчитан." if ok else "Ответ не раскрывает термин.",
        }

    def _draft(self, user: str) -> dict:
        term = re.search(r"Term: (.+)", user).group(1).strip()
        known = json.loads(re.search(r"<dictionary>\s*(.*?)\s*</dictionary>", user, re.DOTALL).group(1))
        return {
            "translation_ru": f"перевод: {term}",
            "collocations": [f"key {term}", f"{term} system", f"common {term}"],
            "common_mistakes": [f"Confusing {term} with a similar term."],
            "contrast_term": None,
            "transcription": None if known.get("transcription") else f"/{term}/",
            "part_of_speech": None if known.get("part_of_speech") else "noun",
            "definition_en": None if known.get("definition_en") else f"A professional term: {term}.",
            "general_definition_fits": True,
            "examples": [] if len(known.get("examples") or []) >= 2 else [f"We discussed the {term} yesterday.", f"The {term} was important."],
        }
