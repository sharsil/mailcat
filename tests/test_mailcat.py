import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import mailcat


# --- Pure function tests ---


def test_randstr_length():
    result = mailcat.randstr(10)
    assert len(result) == 10


def test_randstr_unique_chars():
    # random.sample never repeats characters
    result = mailcat.randstr(15)
    assert len(result) == len(set(result))


def test_randstr_charset():
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    for _ in range(20):
        for ch in mailcat.randstr(10):
            assert ch in allowed


def test_stub_progress():
    p = mailcat.stub_progress(total=100)
    p.update(1)
    p.close()


def test_create_task_func():
    func = mailcat.create_task_func()
    assert func is asyncio.create_task


def test_checkers_list_not_empty():
    assert len(mailcat.CHECKERS) > 0


def test_checkers_are_coroutines():
    for checker in mailcat.CHECKERS:
        assert asyncio.iscoroutinefunction(checker), f"{checker.__name__} is not async"


def test_target_at_sign_stripping():
    """Verify the '@' stripping logic used in start()."""
    target = "user@example.com"
    if "@" in target:
        target = target.split("@")[0]
    assert target == "user"


# --- Helper to build a mock aiohttp session ---


def make_mock_session(status=200, json_data=None, text_data=""):
    """Return a factory function that produces a mock aiohttp session."""
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=json_data)
    response.text = AsyncMock(return_value=text_data)
    response.headers = {}
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.get = AsyncMock(return_value=response)
    session.post = AsyncMock(return_value=response)
    session.put = AsyncMock(return_value=response)
    session.close = AsyncMock()
    session.cookie_jar = True

    def factory():
        return session

    return factory


# --- Checker tests with mocked HTTP ---


@pytest.mark.asyncio
async def test_proton_found():
    session_fun = make_mock_session(
        status=409,
        json_data={"Error": "Username already used"},
    )
    result = await mailcat.proton("testuser", session_fun)
    assert "Proton" in result
    emails = result["Proton"]
    assert "testuser@protonmail.com" in emails
    assert "testuser@proton.me" in emails


@pytest.mark.asyncio
async def test_proton_not_found():
    session_fun = make_mock_session(status=200, json_data={})
    result = await mailcat.proton("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_zoho_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"error": {"username": "This username is taken"}},
    )
    result = await mailcat.zoho("testuser", session_fun)
    assert result == {"Zoho": "testuser@zohomail.com"}


@pytest.mark.asyncio
async def test_zoho_not_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"error": {"username": ""}},
    )
    result = await mailcat.zoho("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_yahoo_found():
    session_fun = make_mock_session(
        status=200,
        text_data='{"errors":[{"name":"yid","error":"IDENTIFIER_EXISTS"}]}',
    )
    result = await mailcat.yahoo("testuser", session_fun)
    assert result == {"Yahoo": "testuser@yahoo.com"}


@pytest.mark.asyncio
async def test_yahoo_not_found():
    session_fun = make_mock_session(
        status=200,
        text_data='{"errors":[]}',
    )
    result = await mailcat.yahoo("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_startmail_found():
    session_fun = make_mock_session(status=404)
    result = await mailcat.startmail("testuser", session_fun)
    assert result == {"StartMail": "testuser@startmail.com"}


@pytest.mark.asyncio
async def test_startmail_not_found():
    session_fun = make_mock_session(status=200)
    result = await mailcat.startmail("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_vivaldi_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"error": "User exists [1007]"},
    )
    result = await mailcat.vivaldi("testuser", session_fun)
    assert result == {"Vivaldi": "testuser@vivaldi.net"}


@pytest.mark.asyncio
async def test_vivaldi_not_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"status": "ok"},
    )
    result = await mailcat.vivaldi("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_duckgo_found():
    session_fun = make_mock_session(
        status=200,
        text_data='{"error":"unavailable_username"}',
    )
    result = await mailcat.duckgo("testuser", session_fun)
    assert result == {"DuckGo": "testuser@duck.com"}


@pytest.mark.asyncio
async def test_duckgo_not_found():
    session_fun = make_mock_session(
        status=200,
        text_data='{"error":"invalid_code"}',
    )
    result = await mailcat.duckgo("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_posteo_found():
    session_fun = make_mock_session(status=200, text_data="false")
    result = await mailcat.posteo("testuser", session_fun)
    assert "Posteo" in result
    assert "testuser@posteo.net" in result["Posteo"]


@pytest.mark.asyncio
async def test_posteo_not_found():
    session_fun = make_mock_session(status=200, text_data="true")
    result = await mailcat.posteo("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_mailbox_found():
    session_fun = make_mock_session(
        status=200,
        text_data="Der Accountname existiert bereits.",
    )
    result = await mailcat.mailbox("testuser", session_fun)
    assert result == {"MailBox": "testuser@mailbox.org"}


@pytest.mark.asyncio
async def test_mailbox_not_found():
    session_fun = make_mock_session(status=200, text_data="ok")
    result = await mailcat.mailbox("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_emailn_found():
    session_fun = make_mock_session(status=200, text_data="<result>0</result>")
    result = await mailcat.emailn("testuser", session_fun)
    assert result == {"emailn": "testuser@emailn.de"}


@pytest.mark.asyncio
async def test_emailn_not_found():
    session_fun = make_mock_session(status=200, text_data="<result>1</result>")
    result = await mailcat.emailn("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_xmail_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"username": False},
    )
    result = await mailcat.xmail("testuser", session_fun)
    assert result == {"Xmail": "testuser@xmail.net"}


@pytest.mark.asyncio
async def test_xmail_not_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"username": True},
    )
    result = await mailcat.xmail("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_ctemplar_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"exists": True},
    )
    result = await mailcat.ctemplar("testuser", session_fun)
    assert result == {"CTemplar": "testuser@ctemplar.com"}


@pytest.mark.asyncio
async def test_ctemplar_not_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"exists": False},
    )
    result = await mailcat.ctemplar("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_ctemplar_invalid_username():
    """Usernames not matching the regex should return empty immediately."""
    session_fun = make_mock_session(status=200)
    result = await mailcat.ctemplar("a.", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_fastmail_invalid_username():
    """Usernames not matching the regex should return empty immediately."""
    session_fun = make_mock_session(status=200)
    result = await mailcat.fastmail("1abc", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_wp_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"errors": [{"message": "Podany login jest niedostępny."}]},
    )
    # wp() uses .json() via content_type=None, but our mock returns text too
    # The checker does str(body) and looks for the Polish string
    result = await mailcat.wp("testuser", session_fun)
    assert result == {"Wirtualna Polska": "testuser@wp.pl"}


@pytest.mark.asyncio
async def test_wp_not_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"errors": []},
    )
    result = await mailcat.wp("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_gazeta_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"available": "0"},
    )
    result = await mailcat.gazeta("testuser", session_fun)
    assert result == {"Gazeta.pl": "testuser@gazeta.pl"}


@pytest.mark.asyncio
async def test_gazeta_not_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"available": "1"},
    )
    result = await mailcat.gazeta("testuser", session_fun)
    assert result == {}


# --- print_results / orchestration tests ---


@pytest.mark.asyncio
async def test_print_results_with_result():
    async def fake_checker(target, req_session_fun, timeout):
        return {"FakeProvider": "user@fake.com"}

    fake_checker.__name__ = "fake_checker"
    res = await mailcat.print_results(fake_checker, "user", None, False, 10)
    assert res == {"fake_checker": {"FakeProvider": "user@fake.com"}}


@pytest.mark.asyncio
async def test_print_results_with_error():
    async def fake_checker(target, req_session_fun, timeout):
        return {}, "connection refused"

    fake_checker.__name__ = "fake_checker"
    res = await mailcat.print_results(fake_checker, "user", None, False, 10)
    assert res == {"fake_checker": "connection refused"}


@pytest.mark.asyncio
async def test_print_results_empty():
    async def fake_checker(target, req_session_fun, timeout):
        return {}

    fake_checker.__name__ = "fake_checker"
    res = await mailcat.print_results(fake_checker, "user", None, False, 10)
    assert res == {"fake_checker": None}


# --- AsyncioProgressbarQueueExecutor tests ---


@pytest.mark.asyncio
async def test_executor_runs_tasks():
    results_collector = []

    async def task_fn(value, default=None):
        results_collector.append(value)
        return value

    executor = mailcat.AsyncioProgressbarQueueExecutor(
        logger=mailcat.logger,
        in_parallel=2,
        timeout=5,
        progress_func=mailcat.stub_progress,
    )

    tasks = [
        (task_fn, [], {"value": i}) for i in range(5)
    ]

    results = await executor.run(tasks)
    assert len(results) == 5
    assert set(results) == {0, 1, 2, 3, 4}
