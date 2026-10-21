"""Design 0001 §6.3 and design 0004 §2: a request reaches each engine in that engine's own fields. Thinking on or off
is `chat_template_kwargs.enable_thinking` for KVMem (llama.cpp's form), and the reasoning budget is
`reasoning_budget_tokens`: a request in the other common form (`enable_thinking`, `reasoning_budget`) reaches KVMem in
its own, with a note for each change; a request already in llama.cpp's form, or one that says nothing of these, is
left as it is. (NInfer took the other form and refused llama.cpp's, until decision 0034 retired it.)"""

from clank.components.runtime.adapters.kvmem import KvmemLlamacpp

ASKED = {"model": "agent", "messages": [{"role": "user", "content": "Hi"}], "temperature": 0.6}
KVMEM = KvmemLlamacpp("v0.16.0-rc1")


def test_kvmem_gets_thinking_and_its_budget_in_llamacpps_fields() -> None:
    asked = {**ASKED, "enable_thinking": False, "reasoning_budget": 256}
    body, notes = KVMEM.translate(asked)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["reasoning_budget_tokens"] == 256
    assert "enable_thinking" not in body
    assert "reasoning_budget" not in body
    assert notes == [
        "enable_thinking became chat_template_kwargs.enable_thinking",
        "reasoning_budget became reasoning_budget_tokens",
    ]
    assert asked["enable_thinking"] is False, "the request as sent is not changed"


def test_a_request_already_in_llamacpps_form_reaches_kvmem_as_it_is() -> None:
    asked = {**ASKED, "chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget_tokens": 512}
    assert KVMEM.translate(asked) == (asked, [])


def test_a_request_that_says_nothing_of_thinking_is_left_as_it_is() -> None:
    assert KVMEM.translate(dict(ASKED)) == (ASKED, [])
