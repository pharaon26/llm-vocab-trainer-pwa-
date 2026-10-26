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
        'Write ONE new sentence (not copied from the card examples) in which the target term is replaced with "____". '
        '"prompt" is that sentence. "options" has exactly 4 items: the target term and 3 other terms from the same '
        'domain that do not fit the sentence. "correct_answer" is the target term.'
    ),
    TaskType.COLLOCATION_CHOICE: (
        'Make a short two-word phrase from the target term and one more word, and replace that word with "____" '
        '(for example "____ vulnerability"). "prompt" is that phrase. "options" has exactly 4 words: the word that '
        "forms a natural collocation with the term (preferably one from the card collocations) and 3 words that "
        'do not collocate with it. "correct_answer" is the collocating word.'
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
        f"Task description:\n{TASK_DESCRIPTIONS[task_type]}\n\n"
        f"Target term card (reference data, do not change it):\n<card>\n{card_json}\n</card>\n\n"
        f"{RULES}\n\n{RESPONSE_FORMAT}"
    )
    return SYSTEM_PROMPT, user
