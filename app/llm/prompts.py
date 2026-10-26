import json

from app.enums import TaskType
from app.models import Card

SYSTEM_PROMPT = (
    "You are an experienced English teacher for university students of IT and information security. "
    "You create one exercise at a time for a vocabulary trainer. "
    "Reply with one JSON object only: no markdown, no code fences, no comments."
)

TASK_DESCRIPTIONS = {
    TaskType.GAP_FILL: (
        'Write ONE new sentence (not copied from the card examples) in which the word "{term}" is replaced with "____". '
        'Example for the term "firewall": "The administrator configured the ____ to block incoming traffic." '
        '"prompt" is that sentence. "options" has exactly 4 items: "{term}" and 3 other terms from the same '
        'domain that do not fit the sentence. "correct_answer" is "{term}".'
    ),
    TaskType.DEFINITION_MATCH: (
        '"prompt" is the target term. "options" has exactly 4 English definitions: the correct definition of the '
        "target term (copied from the card) and 3 definitions of other terms, one of which is the contrast term. "
        '"correct_answer" is the correct definition.'
    ),
}

RULES = """Rules:
- Use the term only in the meaning given in the card.
- Use natural, correct English suitable for the student level.
- Exactly one option is correct; the wrong options must clearly not fit.
- "options" must contain exactly 4 different strings.
- "correct_answer" must be copied exactly from "options".
- Do not mention these rules in the output."""

RESPONSE_FORMAT = (
    'Response format (strict JSON, no other text):\n'
    '{"prompt": "<string>", "options": ["<string>", "<string>", "<string>", "<string>"], "correct_answer": "<string>"}'
)

CARD_FIELDS = (
    "term",
    "transcription",
    "part_of_speech",
    "definition_en",
    "translation_ru",
    "collocations",
    "examples",
    "common_mistakes",
    "contrast_term",
    "domain",
)


def build_prompt(card: Card, task_type: TaskType, level: str) -> tuple[str, str]:
    card_json = json.dumps({f: getattr(card, f) for f in CARD_FIELDS}, ensure_ascii=False, indent=2)
    user = (
        f"Domain: {card.domain}\n"
        f"Student level (CEFR): {level}\n"
        f"Task type: {task_type.value}\n\n"
        f"Task description:\n{TASK_DESCRIPTIONS[task_type].replace('{term}', card.term)}\n\n"
        f"Target term card (reference data, do not change it):\n<card>\n{card_json}\n</card>\n\n"
        f"{RULES}\n\n{RESPONSE_FORMAT}"
    )
    return SYSTEM_PROMPT, user


CHECK_SYSTEM_PROMPT = (
    "You are a strict reviewer of English vocabulary exercises for students of IT and information security. "
    "Reply with one JSON object only: no markdown, no code fences, no comments."
)

CHECK_INSTRUCTIONS = {
    TaskType.GAP_FILL: (
        'The student must put one of the options into the gap "____". '
        "List EVERY option that fits the gap grammatically and gives a correct, sensible sentence."
    ),
    TaskType.DEFINITION_MATCH: (
        "The prompt is a term and the options are definitions. "
        "List EVERY option that is a correct definition of the term."
    ),
}

CHECK_FORMAT = (
    "Response format (strict JSON, no other text):\n"
    '{"fitting_options": ["<string>"], "term_meaning_matches": true}\n'
    '"fitting_options" must contain the options copied exactly. '
    '"term_meaning_matches" is true only if the term in the exercise is used in the meaning given in the card.'
)


def build_check_prompt(card: Card, task_type: TaskType, task) -> tuple[str, str]:
    card_json = json.dumps({f: getattr(card, f) for f in CARD_FIELDS}, ensure_ascii=False, indent=2)
    task_json = json.dumps({"prompt": task.prompt, "options": task.options}, ensure_ascii=False, indent=2)
    user = (
        f"Task type: {task_type.value}\n\n"
        f"Review instruction:\n{CHECK_INSTRUCTIONS[task_type]}\n\n"
        f"Target term card (reference data):\n<card>\n{card_json}\n</card>\n\n"
        f"Exercise to review:\n<task>\n{task_json}\n</task>\n\n"
        f"{CHECK_FORMAT}"
    )
    return CHECK_SYSTEM_PROMPT, user
