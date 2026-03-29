from steelclaw.api.voice import split_into_chunks


def test_split_basic_sentences():
    text = "Hello world. How are you? I am fine!"
    chunks = split_into_chunks(text)
    assert chunks == ["Hello world.", "How are you?", "I am fine!"]


def test_split_merges_short_chunks():
    text = "Hi. OK. This is a longer sentence that should stand alone."
    chunks = split_into_chunks(text, min_length=10)
    assert chunks == ["Hi. OK.", "This is a longer sentence that should stand alone."]


def test_split_single_sentence():
    text = "Just one sentence here"
    chunks = split_into_chunks(text)
    assert chunks == ["Just one sentence here"]


def test_split_empty():
    assert split_into_chunks("") == []
    assert split_into_chunks("   ") == []
