import json
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from sqlalchemy import func, select, update
from app.dictionary.base import DictionaryEntry
from app.dictionary.fake import FakeDictionary
from app.llm.base import LLMError
from app.llm.fake import FakeProvider
from app.models import Card, CardDraft, CardProgress, Deck, DeckCard, LlmUsage, ReviewHistory, User
from app.seed import load_cards
from tests.conftest import login

TODAY = date(2026, 1, 10)

JITTER = DictionaryEntry(
    transcription="/ˈdʒɪtə/", part_of_speech="noun",
    definition="The delay before a transfer of data begins.",
    examples=["High jitter ruins video calls.", "Jitter is measured in milliseconds."],
    audio_url="https://audio.test/jitter.mp3",
)

JITTER_FULL = DictionaryEntry(
    transcription="/x/", part_of_speech="noun", definition="Variation in delay.",
    examples=["Jitter hurts calls.", "Measure the jitter."],
)

SUGGESTION = {
    "translation_ru": "задержка",
    "collocations": ["low jitter", "network jitter", "reduce jitter"],
    "common_mistakes": ["Confusing jitter with throughput."],
    "contrast_term": "throughput",
    "transcription": None, "part_of_speech": None, "definition_en": None,
    "general_definition_fits": True, "examples": [],
}


def llm_reply(**overrides):
    return json.dumps({**SUGGESTION, **overrides}, ensure_ascii=False)


@pytest.fixture(autouse=True)
def fixed_today(clock):
    clock.today = TODAY


@pytest.fixture
async def cards(db):
    await load_cards(db)
    (await db.execute(update(Card).values({Card.verified: True})))
    await db.commit()
    return {c.term: c for c in (await db.scalars(select(Card).where(Card.owner_id.is_(None)))).all()}


async def create(client, headers, term="jitter", domain="IT"):
    return await client.post("/me/drafts", headers=headers, json={"term": term, "domain": domain})


def draft_of(response):
    assert response.status_code == 200, response.text
    return response.json()["draft"]


@pytest.fixture
def full(dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider([llm_reply()])


async def test_endpoints_require_login(client):
    for method, path in (("post", "/me/drafts"), ("get", "/me/drafts"), ("get", "/me/cards")):
        assert (await getattr(client, method)(path)).status_code == 401


async def test_draft_combines_dictionary_and_model_with_sources(client, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    assert draft["fields"]["transcription"] == "/ˈdʒɪtə/"
    assert draft["fields"]["translation_ru"] == "задержка"
    assert draft["fields"]["contrast_term"] == "throughput"
    assert draft["audio_url"] == "https://audio.test/jitter.mp3"
    assert draft["sources"] == {
        "transcription": "dictionary", "part_of_speech": "dictionary", "definition_en": "dictionary",
        "examples": "dictionary", "translation_ru": "llm", "contrast_term": "llm",
        "collocations": "llm", "common_mistakes": "llm",
    }
    assert draft["missing"] == [] and draft["notices"] == []
    assert draft["domain"] == "IT"


async def test_model_receives_only_the_term_domain_and_dictionary_data(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider([llm_reply()])
    await create(client, student_headers)
    system, user = llm.provider.calls[0]
    assert "Term: jitter" in user and "Domain: IT" in user
    assert "<dictionary>" in user and "student" not in user.lower()
    assert "JSON" in system


async def test_dictionary_unavailable_falls_back_to_the_model_without_failing(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary(unavailable=True)
    llm.provider = FakeProvider([llm_reply(
        transcription="/ˈdʒɪtə/", part_of_speech="noun", definition_en="Delay before data transfer starts.",
        examples=["Jitter matters for games.", "We measured the jitter twice."])])
    draft = draft_of(await create(client, student_headers))
    assert any("Внешний словарь недоступен" in n for n in draft["notices"])
    assert draft["sources"]["definition_en"] == "llm" and draft["sources"]["examples"] == "llm"
    assert draft["fields"]["examples"] == ["Jitter matters for games.", "We measured the jitter twice."]
    assert draft["missing"] == []


async def test_word_not_found_in_the_dictionary_is_noted(client, student_headers, cards, dictionary, llm):
    llm.provider = FakeProvider([llm_reply(definition_en="Delay.", transcription="/x/", part_of_speech="noun",
                                           examples=["The jitter is high.", "Reduce jitter."])])
    draft = draft_of(await create(client, student_headers))
    assert any("не найдено" in n for n in draft["notices"])


async def test_no_model_leaves_dictionary_fields_and_lists_the_missing_ones(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = None
    draft = draft_of(await create(client, student_headers))
    assert any("Модель не настроена" in n for n in draft["notices"])
    assert draft["missing"] == ["translation_ru", "collocations", "common_mistakes"]
    assert draft["fields"]["definition_en"].startswith("The delay")


async def test_model_error_is_reported_and_the_draft_is_still_created(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider([LLMError("down")])
    draft = draft_of(await create(client, student_headers))
    assert any("Модель сейчас недоступна" in n for n in draft["notices"])
    assert draft["sources"].get("translation_ru") is None


async def test_invalid_model_json_is_retried(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider(["garbage", "{broken", llm_reply()])
    draft = draft_of(await create(client, student_headers))
    assert draft["fields"]["translation_ru"] == "задержка" and draft["notices"] == []
    assert len(llm.provider.calls) == 3


async def test_model_that_never_answers_validly_gives_a_notice(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider(["garbage"] * 3)
    draft = draft_of(await create(client, student_headers))
    assert any("не вернула корректный ответ" in n for n in draft["notices"])


async def test_every_attempt_counts_against_the_daily_limit(client, db, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider(["garbage", "garbage", llm_reply()])
    draft = draft_of(await create(client, student_headers))
    assert draft["llm_calls_left"] == 30 - 3


async def test_exhausted_limit_skips_the_model_but_keeps_the_dictionary(client, db, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider([llm_reply()])
    user = (await db.scalars(select(User).filter_by(name="student"))).one()
    db.add(LlmUsage(user_id=user.id, day=TODAY, calls=30))
    await db.commit()
    draft = draft_of(await create(client, student_headers))
    assert llm.provider.calls == []
    assert any("лимит" in n for n in draft["notices"]) and draft["llm_calls_left"] == 0
    assert draft["fields"]["transcription"] == "/ˈdʒɪtə/"


async def test_limit_in_the_middle_of_retries_stops_further_calls(client, db, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider(["garbage", "garbage", "garbage"])
    user = (await db.scalars(select(User).filter_by(name="student"))).one()
    db.add(LlmUsage(user_id=user.id, day=TODAY, calls=29))
    await db.commit()
    draft = draft_of(await create(client, student_headers))
    assert len(llm.provider.calls) == 1 and any("лимит" in n for n in draft["notices"])


async def test_limit_is_per_student_and_per_day(client, db, clock, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider([llm_reply(), llm_reply(), llm_reply()])
    await create(client, student_headers, "jitter")
    other = await login(client, name="other")
    assert draft_of(await create(client, other, "jitter"))["llm_calls_left"] == 29
    clock.today = date(2026, 1, 11)
    assert draft_of(await create(client, student_headers, "bandwidth"))["llm_calls_left"] == 29


async def test_model_fields_are_filtered(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": DictionaryEntry(
        transcription="/x/", part_of_speech="noun", definition="Delay.", examples=["One jitter example."])})
    llm.provider = FakeProvider([llm_reply(
        collocations=["low jitter", "unrelated phrase", "network jitter", "low jitter"],
        examples=["Nothing relevant here.", "Another jitter sentence.", "Third jitter sentence."],
        contrast_term="Jitter")])
    draft = draft_of(await create(client, student_headers))
    assert draft["fields"]["collocations"] == ["low jitter", "network jitter"]
    assert draft["fields"]["examples"] == ["One jitter example.", "Another jitter sentence.", "Third jitter sentence."]
    assert draft["fields"]["contrast_term"] is None


async def test_professional_definition_replaces_a_general_one_and_keeps_the_original(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider([llm_reply(general_definition_fits=False, definition_en="Time between a request and its response.")])
    draft = draft_of(await create(client, student_headers))
    assert draft["fields"]["definition_en"] == "Time between a request and its response."
    assert draft["sources"]["definition_en"] == "llm"
    assert draft["general_definition"] == "The delay before a transfer of data begins."


async def test_fitting_dictionary_definition_is_kept(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider([llm_reply(general_definition_fits=True, definition_en="Ignored proposal.")])
    draft = draft_of(await create(client, student_headers))
    assert draft["fields"]["definition_en"].startswith("The delay") and draft["general_definition"] is None


async def test_existing_shared_card_is_offered_instead_of_a_draft(client, db, student_headers, cards, dictionary, llm):
    llm.provider = FakeProvider([llm_reply()])
    body = (await create(client, student_headers, "VULNERABILITY")).json()
    assert body["draft"] is None
    duplicate = body["duplicate"]
    assert duplicate["term"] == "vulnerability" and duplicate["personal"] is False
    assert duplicate["decks"] == [{"id": (await db.scalars(select(Deck))).one().id, "name": "IT & Security basics", "selected": True}]
    assert llm.provider.calls == [] and dictionary.provider.calls == []


async def test_duplicate_shows_decks_that_are_not_selected(client, db, student_headers, cards):
    await client.put("/me/decks", headers=student_headers, json={"deck_ids": []})
    duplicate = (await create(client, student_headers, "patch")).json()["duplicate"]
    assert duplicate["decks"][0]["selected"] is False


async def test_unverified_shared_cards_do_not_count_as_duplicates(client, db, student_headers, cards, dictionary, llm):
    cards["patch"].verified = False
    await db.commit()
    llm.provider = FakeProvider([llm_reply()])
    assert (await create(client, student_headers, "patch")).json()["draft"] is not None


async def test_own_personal_card_is_a_duplicate_but_someone_elses_is_not(client, db, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)
    again = (await create(client, student_headers, "Jitter")).json()
    assert again["duplicate"]["personal"] is True
    other = await login(client, name="other")
    assert (await create(client, other, "jitter")).json()["draft"] is not None


async def test_repeated_request_returns_the_same_draft_without_new_model_calls(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = FakeProvider([llm_reply()])
    first = draft_of(await create(client, student_headers))
    second = draft_of(await create(client, student_headers, "JITTER"))
    assert first["id"] == second["id"] and len(llm.provider.calls) == 1


async def test_unknown_domain_and_empty_term_are_rejected(client, student_headers, cards):
    assert (await create(client, student_headers, domain="Astrology")).status_code == 422
    assert (await create(client, student_headers, term="  ")).status_code == 422
    assert (await create(client, student_headers, term="x" * 101)).status_code == 422


async def test_term_whitespace_is_normalized(client, student_headers, cards, full):
    assert draft_of(await create(client, student_headers, "  jitter  "))["term"] == "jitter"


async def test_open_drafts_are_capped(client, db, student_headers, cards):
    user = (await db.scalars(select(User).filter_by(name="student"))).one()
    for index in range(50):
        db.add(CardDraft(owner_id=user.id, term=f"t{index}", domain_id=1, data={}, sources={}, notices=[]))
    await db.commit()
    assert (await create(client, student_headers, "jitter")).status_code == 409


async def test_editing_a_draft_marks_changed_fields_as_user_edits(client, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    fields = draft["fields"]
    fields["translation_ru"] = "латентность"
    fields["collocations"] = ["low jitter", " network jitter ", ""]
    updated = (await client.put(f"/me/drafts/{draft['id']}", headers=student_headers, json={"fields": fields, "domain": "Engineering"})).json()
    assert updated["sources"]["translation_ru"] == "user" and updated["sources"]["collocations"] == "user"
    assert updated["sources"]["common_mistakes"] == "llm" and updated["sources"]["definition_en"] == "dictionary"
    assert updated["fields"]["collocations"] == ["low jitter", "network jitter"]
    assert updated["domain"] == "Engineering"


async def test_resending_unchanged_values_keeps_their_sources(client, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    updated = (await client.put(f"/me/drafts/{draft['id']}", headers=student_headers, json={"fields": draft["fields"]})).json()
    assert updated["sources"] == draft["sources"]


async def test_clearing_a_field_makes_it_missing_again(client, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    updated = (await client.put(f"/me/drafts/{draft['id']}", headers=student_headers, json={"fields": {"translation_ru": "  "}})).json()
    assert updated["fields"]["translation_ru"] is None and "translation_ru" in updated["missing"]


async def test_unknown_domain_in_update_is_rejected(client, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    assert (await client.put(f"/me/drafts/{draft['id']}", headers=student_headers, json={"domain": "Nope", "fields": {}})).status_code == 422


async def test_drafts_are_private(client, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    other = await login(client, name="other")
    assert (await client.get("/me/drafts", headers=other)).json() == []
    assert (await client.put(f"/me/drafts/{draft['id']}", headers=other, json={"fields": {}})).status_code == 404
    assert (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=other)).status_code == 404
    assert (await client.delete(f"/me/drafts/{draft['id']}", headers=other)).status_code == 404


async def test_draft_can_be_deleted(client, db, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    assert (await client.delete(f"/me/drafts/{draft['id']}", headers=student_headers)).status_code == 204
    assert (await client.get("/me/drafts", headers=student_headers)).json() == []


async def test_incomplete_draft_cannot_be_confirmed_and_errors_name_the_fields(client, db, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = None
    draft = draft_of(await create(client, student_headers))
    response = await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)
    assert response.status_code == 422
    text = response.text
    assert "translation_ru" in text and "collocations" in text and "common_mistakes" in text
    assert (await db.scalar(select(func.count()).select_from(select(Card).where(Card.owner_id.isnot(None)).subquery()))) == 0
    assert (await client.get("/me/drafts", headers=student_headers)).json()[0]["id"] == draft["id"]


async def test_confirm_with_edits_in_one_request(client, db, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    llm.provider = None
    draft = draft_of(await create(client, student_headers))
    fields = {**draft["fields"], "translation_ru": "задержка", "collocations": ["low jitter", "high jitter"], "common_mistakes": ["Mixing it up with throughput."]}
    response = await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers, json={"fields": fields})
    assert response.status_code == 201, response.text
    card = response.json()
    assert card["term"] == "jitter" and card["sources"]["translation_ru"] == "user"
    assert card["sources"]["definition_en"] == "dictionary" and card["audio_url"] == "https://audio.test/jitter.mp3"


async def test_confirmed_card_is_personal_and_the_draft_is_gone(client, db, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    assert (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)).status_code == 201
    card = (await db.scalars(select(Card).where(Card.owner_id.isnot(None)))).one()
    assert (card.confirmed_by_owner, card.verified) == (True, False)
    assert card.owner_id == (await db.scalars(select(User).filter_by(name="student"))).one().id
    assert card.field_sources["translation_ru"] == "llm"
    assert (await db.scalar(select(func.count()).select_from(select(CardDraft).subquery()))) == 0
    mine = (await client.get("/me/cards", headers=student_headers)).json()
    assert [c["term"] for c in mine] == ["jitter"]


async def test_unconfirmed_draft_never_reaches_the_session(client, db, student_headers, cards, full):
    draft_of(await create(client, student_headers))
    await client.put("/me/decks", headers=student_headers, json={"deck_ids": []})
    assert (await client.get("/session/next", headers=student_headers)).json()["remaining"] == 0


async def test_personal_card_enters_the_session_as_a_new_term_even_without_decks(client, db, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)
    await client.put("/me/decks", headers=student_headers, json={"deck_ids": []})
    queue = (await client.get("/session/next", headers=student_headers)).json()
    assert queue["remaining"] == 1 and queue["task"]["card_id"] == (await db.scalars(select(Card).where(Card.owner_id.isnot(None)))).one().id


async def test_personal_cards_are_invisible_to_other_students_and_teachers_card_list(client, db, student_headers, teacher_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)
    card = (await db.scalars(select(Card).where(Card.owner_id.isnot(None)))).one()
    other = await login(client, name="other")
    assert (await client.get("/me/cards", headers=other)).json() == []
    assert "jitter" not in (await client.get("/me/dictionary", headers=other)).text
    assert "jitter" not in (await client.get("/me/progress", headers=other)).text
    assert "jitter" not in {c["term"] for c in (await client.get("/cards", headers=teacher_headers)).json()}
    for call in (
        await client.get(f"/cards/{card.id}", headers=teacher_headers),
        await client.put(f"/cards/{card.id}", headers=teacher_headers, json={}),
        await client.patch(f"/cards/{card.id}/verify", headers=teacher_headers),
        await client.delete(f"/cards/{card.id}", headers=teacher_headers),
    ):
        assert call.status_code in (404, 422)
    assert (await client.get(f"/cards/{card.id}", headers=teacher_headers)).status_code == 404


async def test_other_students_never_see_a_personal_card_as_an_answer_option(client, db, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    fields = {**draft["fields"], "definition_en": "SECRET-DEFINITION-OF-A-PRIVATE-WORD"}
    await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers, json={"fields": fields})
    other = await login(client, name="other")
    seen = ""
    for _ in range(12):
        data = (await client.get("/session/next", headers=other)).json()
        if data["task"] is None:
            break
        seen += json.dumps(data["task"])
        await client.post("/session/answer", headers=other, json={
            "card_id": data["task"]["card_id"], "task_type": data["task"]["task_type"],
            "task_id": data["task"]["task_id"], "answer": "x"})
    assert "SECRET" not in seen and "jitter" not in seen.lower()


async def test_owner_can_edit_a_personal_card_and_changed_fields_become_user_edits(client, db, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    card_id = (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)).json()["id"]
    payload = {
        "term": "jitter", "transcription": "/ˈdʒɪtə/", "part_of_speech": "noun",
        "definition_en": "Delay before a transfer of data begins.", "translation_ru": "латентность",
        "collocations": ["low jitter", "network jitter"], "examples": ["High jitter ruins video calls.", "Jitter is measured in ms."],
        "common_mistakes": ["Confusing jitter with throughput."], "contrast_term": "throughput", "domain": "IT",
    }
    updated = (await client.put(f"/me/cards/{card_id}", headers=student_headers, json=payload)).json()
    assert updated["translation_ru"] == "латентность" and updated["sources"]["translation_ru"] == "user"
    assert updated["sources"]["definition_en"] == "user" and updated["sources"]["common_mistakes"] == "llm"
    assert (await db.get(Card, card_id)).confirmed_by_owner is True


async def test_personal_card_edit_and_delete_are_owner_only(client, db, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    card_id = (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)).json()["id"]
    other = await login(client, name="other")
    assert (await client.delete(f"/me/cards/{card_id}", headers=other)).status_code == 404
    assert (await client.put(f"/me/cards/{card_id}", headers=other, json={})).status_code in (404, 422)
    shared = cards["patch"].id
    assert (await client.delete(f"/me/cards/{shared}", headers=student_headers)).status_code == 404


async def test_deleting_a_personal_card_removes_its_traces(client, db, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    card_id = (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)).json()["id"]
    user = (await db.scalars(select(User).filter_by(name="student"))).one()
    db.add(CardProgress(user_id=user.id, card_id=card_id, interval=1, ease=2.5, repetitions=1,
                        first_seen_on=TODAY, due_date=TODAY))
    db.add(ReviewHistory(user_id=user.id, card_id=card_id, task_type="write_term", answer="x", is_correct=False,
                         error_type="form", is_retry=False, answered_on=TODAY))
    await db.commit()
    assert (await client.delete(f"/me/cards/{card_id}", headers=student_headers)).status_code == 204
    assert (await db.scalar(select(func.count()).select_from(select(Card).where(Card.owner_id.isnot(None)).subquery()))) == 0
    assert (await db.scalar(select(func.count()).select_from(select(CardProgress).filter_by(card_id=card_id).subquery()))) == 0
    assert (await db.scalar(select(func.count()).select_from(select(ReviewHistory).filter_by(card_id=card_id).subquery()))) == 0


async def test_shared_card_added_meanwhile_blocks_confirmation(client, db, student_headers, teacher_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    new = {"term": "jitter", "transcription": "/x/", "part_of_speech": "noun", "definition_en": "d", "translation_ru": "з",
           "collocations": ["a b", "c d"], "examples": ["Jitter one.", "Jitter two."], "common_mistakes": ["m"],
           "contrast_term": None, "domain": "IT"}
    card_id = (await client.post("/cards", headers=teacher_headers, json=new)).json()["id"]
    await client.patch(f"/cards/{card_id}/verify", headers=teacher_headers)
    assert (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)).status_code == 409


async def test_database_enforces_term_uniqueness_per_scope(db, cards):
    shared = (await db.scalars(select(Card).where(Card.owner_id.is_(None)))).first()
    shared_term, shared_domain_id = shared.term, shared.domain_id
    values = dict(
        transcription="/x/", part_of_speech="noun", definition_en="d", translation_ru="т", collocations=["a b", "c d"],
        examples=["x", "y"], common_mistakes=["m"], contrast_term=None, domain_id=shared_domain_id,
    )
    db.add(Card(term=shared_term, **values))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
    users = [User(name="u1", role="student"), User(name="u2", role="student")]
    db.add_all(users)
    await db.commit()
    db.add(Card(term=shared_term, owner_id=users[0].id, confirmed_by_owner=True, **values))
    db.add(Card(term=shared_term, owner_id=users[1].id, confirmed_by_owner=True, **values))
    await db.commit()
    db.add(Card(term=shared_term, owner_id=users[0].id, confirmed_by_owner=True, **values))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_fake_provider_can_drive_the_whole_flow_without_scripts(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary()
    llm.provider = FakeProvider()
    draft = draft_of(await create(client, student_headers, "invoice", "Economics"))
    assert draft["missing"] == []
    assert (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)).status_code == 201


async def test_personal_words_come_first_among_new_terms(client, db, student_headers, cards, full):
    draft = draft_of(await create(client, student_headers))
    card_id = (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)).json()["id"]
    first = (await client.get("/session/next", headers=student_headers)).json()
    assert first["task"]["card_id"] == card_id and first["remaining"] == 5


async def test_phrases_skip_the_dictionary_and_say_why(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"packet loss": JITTER})
    llm.provider = FakeProvider([llm_reply(
        collocations=["high packet loss", "reduce packet loss"], definition_en="Share of packets that never arrive.",
        transcription="/x/", part_of_speech="noun", examples=["Packet loss hurts calls.", "We measured packet loss."])])
    draft = draft_of(await create(client, student_headers, "packet loss"))
    assert dictionary.provider.calls == []
    assert any("только отдельные слова" in n for n in draft["notices"])
    assert draft["sources"]["definition_en"] == "llm" and draft["missing"] == []


async def test_prompt_demands_the_fields_the_dictionary_could_not_give(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary()
    llm.provider = FakeProvider([llm_reply()])
    await create(client, student_headers, "jitter")
    user = llm.provider.calls[0][1]
    assert "You MUST fill these fields" in user
    for field in ('"definition_en"', '"part_of_speech"', '"transcription"', '"examples"'):
        assert field in user.split("You MUST fill")[1].split("Rules:")[0]
    assert 'exact words "jitter"' in user


async def test_prompt_demands_only_what_is_missing(client, student_headers, cards, dictionary, llm):
    dictionary.provider = FakeDictionary({"jitter": JITTER_FULL})
    llm.provider = FakeProvider([llm_reply()])
    await create(client, student_headers, "jitter")
    assert "You MUST fill" not in llm.provider.calls[0][1]
