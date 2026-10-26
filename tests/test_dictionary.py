import httpx
import pytest

from app.config import Settings
from app.dictionary.base import DictionaryUnavailable
from app.dictionary.dictionaryapi import DictionaryApiProvider, contains_word, parse_entries
from app.dictionary.factory import DisabledDictionary, get_dictionary

LATENCY = [
    {
        "word": "latency",
        "phonetic": "/ˈleɪtənsi/",
        "phonetics": [
            {"text": "/ˈleɪtənsi/", "audio": ""},
            {"text": "/ˈleɪtənsi/", "audio": "//ssl.gstatic.com/dictionary/static/sounds/latency.mp3"},
        ],
        "meanings": [
            {
                "partOfSpeech": "noun",
                "definitions": [
                    {"definition": "The delay before a transfer of data begins.", "example": "High latency ruins video calls."},
                    {"definition": "The state of being latent.", "example": "A period of latency followed."},
                    {"definition": "Another sense.", "example": "Unrelated sentence without the word."},
                ],
            }
        ],
    }
]


def provider(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return DictionaryApiProvider("https://dict.test/api/entries/en/", 3.0, client)


def test_parse_full_entry():
    entry = parse_entries(LATENCY, "latency")
    assert entry.transcription == "/ˈleɪtənsi/"
    assert entry.part_of_speech == "noun"
    assert entry.definition == "The delay before a transfer of data begins."
    assert entry.audio_url == "https://ssl.gstatic.com/dictionary/static/sounds/latency.mp3"
    assert entry.examples == ["High latency ruins video calls.", "A period of latency followed."]


def test_transcription_gets_slashes_and_bad_audio_is_dropped():
    payload = [{"phonetic": "ˈleɪtənsi", "phonetics": [{"audio": "javascript:alert(1)"}, {"audio": "ftp://x/y.mp3"}],
                "meanings": [{"partOfSpeech": "noun", "definitions": [{"definition": "d"}]}]}]
    entry = parse_entries(payload, "latency")
    assert entry.transcription == "/ˈleɪtənsi/"
    assert entry.audio_url is None


@pytest.mark.parametrize("payload", [None, [], {}, "text", [{"word": "x"}], [{"meanings": []}], ["str"]])
def test_unusable_payloads_give_none(payload):
    assert parse_entries(payload, "x") is None


def test_examples_are_capped_at_three():
    definitions = [{"definition": "d", "example": f"Sentence {i} with latency."} for i in range(6)]
    payload = [{"meanings": [{"partOfSpeech": "noun", "definitions": definitions}]}]
    assert len(parse_entries(payload, "latency").examples) == 3


def test_contains_word():
    assert contains_word("Network latencies grow", "latency") is False
    assert contains_word("Low latency matters", "latency")
    assert contains_word("LATENCY matters", "latency")


def test_lookup_success_builds_the_url_from_the_word():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=LATENCY)

    assert provider(handler).lookup("latency").definition.startswith("The delay")
    assert seen == ["https://dict.test/api/entries/en/latency"]


def test_word_is_url_quoted():
    seen = []

    def handler(request):
        seen.append(request.url.raw_path.decode())
        return httpx.Response(404)

    provider(handler).lookup("man in the middle/../x")
    assert "/../" not in seen[0] and "%20" in seen[0]


def test_404_means_not_found():
    assert provider(lambda r: httpx.Response(404, json={"title": "No Definitions Found"})).lookup("zzz") is None


@pytest.mark.parametrize("status", [429, 500, 503])
def test_server_errors_mean_unavailable(status):
    with pytest.raises(DictionaryUnavailable):
        provider(lambda r: httpx.Response(status)).lookup("latency")


def test_timeout_means_unavailable():
    def handler(request):
        raise httpx.ConnectTimeout("blocked", request=request)

    with pytest.raises(DictionaryUnavailable):
        provider(handler).lookup("latency")


def test_connection_error_means_unavailable():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(DictionaryUnavailable):
        provider(handler).lookup("latency")


def test_invalid_json_means_unavailable():
    with pytest.raises(DictionaryUnavailable):
        provider(lambda r: httpx.Response(200, content=b"<html>blocked</html>")).lookup("latency")


def test_timeout_value_is_passed_to_the_request():
    captured = {}

    def handler(request):
        captured["timeout"] = request.extensions["timeout"]
        return httpx.Response(404)

    provider(handler).lookup("x")
    assert captured["timeout"]["connect"] == 3.0


def test_factory_selects_provider_from_settings():
    assert isinstance(get_dictionary(Settings(_env_file=None, dictionary_provider="dictionaryapi")), DictionaryApiProvider)
    disabled = get_dictionary(Settings(_env_file=None, dictionary_provider="none"))
    assert isinstance(disabled, DisabledDictionary)
    with pytest.raises(DictionaryUnavailable):
        disabled.lookup("x")
