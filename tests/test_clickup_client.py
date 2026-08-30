import responses

from clickup.client import ClickUpClient, TaskRef

CREATE_URL = "https://api.clickup.com/api/v2/list/900100/task"


@responses.activate
def test_create_task_returns_ref():
    responses.add(
        responses.POST,
        CREATE_URL,
        json={"id": "abc123", "url": "https://app.clickup.com/t/abc123"},
        status=200,
    )

    client = ClickUpClient(token="pk_test")
    ref = client.create_task("900100", "Meeting minutes — Jun 7", "## Minutes\n- ship POC")

    assert isinstance(ref, TaskRef)
    assert ref.id == "abc123"
    assert ref.url == "https://app.clickup.com/t/abc123"
    sent = responses.calls[0].request
    assert sent.headers["Authorization"] == "pk_test"
    assert b"markdown_description" in sent.body


COMMENT_URL = "https://api.clickup.com/api/v2/task/abc123/comment"


@responses.activate
def test_add_comment_posts_text():
    responses.add(responses.POST, COMMENT_URL, json={"id": "c1"}, status=200)

    client = ClickUpClient(token="pk_test")
    client.add_comment("abc123", "Recorded from Fathom.")

    sent = responses.calls[0].request
    assert sent.headers["Authorization"] == "pk_test"
    assert b"comment_text" in sent.body
