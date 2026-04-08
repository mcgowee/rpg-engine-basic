"""llm.text — normalize invoke results."""

from llm.text import llm_result_to_text


def test_llm_result_to_text_plain_str():
    assert llm_result_to_text("hello") == "hello"


def test_llm_result_to_text_aimessage_like():
    class Msg:
        content = "x"

    assert llm_result_to_text(Msg()) == "x"


def test_llm_result_to_text_content_list():
    class Msg:
        content = [{"text": "a"}, "b", {"foo": 1}]

    assert llm_result_to_text(Msg()) == "ab"
