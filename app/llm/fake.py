import json
import re

from app.enums import TaskType
from app.llm.base import LLMError, LLMProvider

GENERIC_TERMS = ["protocol", "database", "compiler"]
GENERIC_WORDS = ["purple", "seven", "wooden"]
GENERIC_DEFINITIONS = [
    "A named storage place for files inside an operating system.",
    "A device that converts digital signals into sound.",
    "A rule that sets the colour scheme of a website.",
]


class FakeProvider(LLMProvider):
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
        card = json.loads(re.search(r"<card>\s*(.*?)\s*</card>", user, re.DOTALL).group(1))
        task_type = TaskType(re.search(r"Task type: (\w+)", user).group(1))
        if task_type == TaskType.GAP_FILL:
            return self._gap_fill(card)
        if task_type == TaskType.COLLOCATION_CHOICE:
            return self._collocation(card)
        return self._definition(card)

    def _gap_fill(self, card: dict) -> dict:
        term = card["term"]
        pattern = re.compile(rf"\b{re.escape(term)}\w*", re.IGNORECASE)
        sentence = next(
            (pattern.sub("____", e) for e in card["examples"] if pattern.search(e)),
            "The team discussed ____ during the meeting.",
        )
        distractors = [card["contrast_term"], *GENERIC_TERMS]
        options = [term, *[d for d in distractors if d.lower() != term.lower()][:3]]
        return {"prompt": sentence, "options": options, "correct_answer": term}

    def _collocation(self, card: dict) -> dict:
        term = card["term"].lower()
        for collocation in card["collocations"]:
            words = collocation.split()
            if len(words) == 2 and term in (w.lower() for w in words):
                index = 0 if words[0].lower() == term else 1
                hidden = words[1 - index]
                prompt = f"{words[0]} ____" if index == 0 else f"____ {words[1]}"
                return {"prompt": prompt, "options": [hidden, *GENERIC_WORDS], "correct_answer": hidden}
        return {"prompt": f"____ {card['term']}", "options": ["security", *GENERIC_WORDS], "correct_answer": "security"}

    def _definition(self, card: dict) -> dict:
        definition = card["definition_en"]
        return {
            "prompt": card["term"],
            "options": [definition, *GENERIC_DEFINITIONS],
            "correct_answer": definition,
        }
