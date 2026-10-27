import pytest
from sqlalchemy import select, update

from app.dictionary.audio import safe_audio_url
from app.dictionary.base import DictionaryEntry
from app.dictionary.fake import FakeDictionary
from app.llm.fake import FakeProvider
from app.models import Card, CardDraft
from app.seed import load_cards
from tests.test_personal_cards import JITTER, SUGGESTION, TODAY, llm_reply

DOMAINS = ["api.dictionaryapi.dev", "ssl.gstatic.com"]


@pytest.mark.parametrize(
    "url, ok",
    [
        ("https://api.dictionaryapi.dev/media/pronunciations/en/jitter-us.mp3", True),
        ("https://API.dictionaryapi.dev/x.mp3", True),
        ("https://ssl.gstatic.com/dictionary/static/sounds/jitter.mp3", True),
        ("https://api.dictionaryapi.dev:443/x.mp3", True),
        ("http://api.dictionaryapi.dev/x.mp3", False),
        ("https://evil.example/x.mp3", False),
        ("https://api.dictionaryapi.dev.evil.example/x.mp3", False),
        ("https://api.dictionaryapi.dev@evil.example/x.mp3", False),
        ("https://user:pw@api.dictionaryapi.dev/x.mp3", False),
        ("https://api.dictionaryapi.dev:8443/x.mp3", False),
        ("https://sub.api.dictionaryapi.dev/x.mp3", False),
        ("//api.dictionaryapi.dev/x.mp3", False),
        ("javascript:alert(1)", False),
        ("data:audio/mpeg;base64,AAAA", False),
        ("ftp://api.dictionaryapi.dev/x.mp3", False),
        ("https://api.dictionaryapi.dev:abc/x.mp3", False),
        ("", False),
        (None, False),
        (42, False),
    ],
)
def test_safe_audio_url(url, ok):
    assert (safe_audio_url(url, DOMAINS) is not None) is ok


def test_domains_come_from_settings_by_default(monkeypatch):
    assert safe_audio_url("https://audio.test/a.mp3") == "https://audio.test/a.mp3"
    assert safe_audio_url("https://api.dictionaryapi.dev/a.mp3") is None


@pytest.fixture
async def ready(db, dictionary, llm):
    await load_cards(db)
    await db.execute(update(Card).values(verified=True))
    await db.commit()
    llm.provider = FakeProvider([llm_reply()])


async def create_draft(client, headers):
    response = await client.post("/me/drafts", headers=headers, json={"term": "jitter", "domain": "IT"})
    assert response.status_code == 200, response.text
    return response.json()["draft"]


async def test_foreign_audio_is_dropped_when_the_draft_is_built(client, student_headers, dictionary, ready, clock):
    clock.today = TODAY
    bad = DictionaryEntry(**{**JITTER.__dict__, "audio_url": "https://evil.example/jitter.mp3"})
    dictionary.provider = FakeDictionary({"jitter": bad})
    draft = await create_draft(client, student_headers)
    assert draft["audio_url"] is None


async def test_allowed_audio_survives_and_is_saved_with_the_card(client, student_headers, ready, dictionary, clock):
    clock.today = TODAY
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    draft = await create_draft(client, student_headers)
    assert draft["audio_url"] == "https://audio.test/jitter.mp3"
    card = (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)).json()
    assert card["audio_url"] == "https://audio.test/jitter.mp3"


async def test_audio_is_rechecked_when_the_card_is_saved(client, db, student_headers, ready, dictionary, clock):
    clock.today = TODAY
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    draft = await create_draft(client, student_headers)
    row = await db.get(CardDraft, draft["id"])
    row.data = {**row.data, "audio_url": "javascript:alert(1)"}
    await db.commit()
    shown = (await client.get("/me/drafts", headers=student_headers)).json()[0]
    assert shown["audio_url"] is None
    card = (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)).json()
    assert card["audio_url"] is None
    assert await db.scalar(select(Card.audio_url).where(Card.id == card["id"])) is None


async def test_audio_already_stored_is_filtered_on_output(client, db, student_headers, teacher_headers, ready, dictionary, clock):
    clock.today = TODAY
    dictionary.provider = FakeDictionary({"jitter": JITTER})
    draft = await create_draft(client, student_headers)
    card = (await client.post(f"/me/drafts/{draft['id']}/confirm", headers=student_headers)).json()
    await db.execute(update(Card).where(Card.id == card["id"]).values(audio_url="https://evil.example/x.mp3"))
    await db.commit()
    assert (await client.get("/me/cards", headers=student_headers)).json()[0]["audio_url"] is None
    assert (await client.get("/teacher/personal-cards", headers=teacher_headers)).json()[0]["audio_url"] is None
