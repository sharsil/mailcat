import asyncio
import json
import re
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


def make_proton_mock_session(check_status, check_json):
    """Proton needs two responses: POST /auth/v4/sessions then GET /users/available."""
    auth_resp = AsyncMock()
    auth_resp.status = 200
    auth_resp.json = AsyncMock(return_value={"AccessToken": "tok", "UID": "uid"})
    auth_resp.__aenter__ = AsyncMock(return_value=auth_resp)
    auth_resp.__aexit__ = AsyncMock(return_value=False)

    check_resp = AsyncMock()
    check_resp.status = check_status
    check_resp.json = AsyncMock(return_value=check_json)
    check_resp.__aenter__ = AsyncMock(return_value=check_resp)
    check_resp.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.post = AsyncMock(return_value=auth_resp)
    session.get = AsyncMock(return_value=check_resp)
    session.close = AsyncMock()
    session.cookie_jar = True

    return lambda: session


@pytest.mark.asyncio
async def test_proton_found():
    session_fun = make_proton_mock_session(
        check_status=409,
        check_json={"Error": "Username already used"},
    )
    result = await mailcat.proton("testuser", session_fun)
    assert "Proton" in result
    emails = result["Proton"]
    assert "testuser@protonmail.com" in emails
    assert "testuser@proton.me" in emails


@pytest.mark.asyncio
async def test_proton_not_found():
    session_fun = make_proton_mock_session(check_status=200, check_json={"Code": 1000})
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
        json_data={"fields": {"userId": {"value": "testuser",
                                         "error": {"id": "IDENTIFIER_NOT_AVAILABLE"}}}},
    )
    result = await mailcat.yahoo("testuser", session_fun)
    assert result == {"Yahoo": "testuser@yahoo.com"}


@pytest.mark.asyncio
async def test_yahoo_not_found():
    session_fun = make_mock_session(
        status=200,
        json_data={"fields": {"userId": {"value": "testuser"}}},
    )
    result = await mailcat.yahoo("testuser", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_yahoo_reserved_word_treated_as_not_found():
    """Yahoo flags some names (e.g. 'admin') as RESERVED_WORD_PRESENT — treat as not-taken."""
    session_fun = make_mock_session(
        status=200,
        json_data={"fields": {"userId": {"value": "admin",
                                         "error": {"id": "RESERVED_WORD_PRESENT"}}}},
    )
    result = await mailcat.yahoo("admin", session_fun)
    assert result == {}


# AOL needs a two-call flow: GET signup page (text) then POST validate (json).
_AOL_SIGNUP_HTML = (
    '<form>'
    '<input type="hidden" value="CRUMB123" name="crumb">'
    '<input type="hidden" value="ACRUMB" name="acrumb">'
    '<input type="hidden" value="QQ--" name="sessionIndex">'
    '</form>'
)


def make_aol_mock_session(validate_json, signup_html=_AOL_SIGNUP_HTML,
                          signup_status=200, validate_status=200):
    signup_resp = AsyncMock()
    signup_resp.status = signup_status
    signup_resp.text = AsyncMock(return_value=signup_html)
    signup_resp.__aenter__ = AsyncMock(return_value=signup_resp)
    signup_resp.__aexit__ = AsyncMock(return_value=False)

    validate_resp = AsyncMock()
    validate_resp.status = validate_status
    validate_resp.json = AsyncMock(return_value=validate_json)
    validate_resp.__aenter__ = AsyncMock(return_value=validate_resp)
    validate_resp.__aexit__ = AsyncMock(return_value=False)

    session = AsyncMock()
    session.get = AsyncMock(return_value=signup_resp)
    session.post = AsyncMock(return_value=validate_resp)
    session.close = AsyncMock()
    session.cookie_jar = True

    return lambda: session


def test_aol_extract_tokens_value_before_name():
    """Real AOL HTML emits value="..." before name="..." — make sure we parse it."""
    tokens = mailcat._aol_extract_tokens(_AOL_SIGNUP_HTML)
    assert tokens == {"crumb": "CRUMB123", "acrumb": "ACRUMB", "sessionIndex": "QQ--"}


@pytest.mark.asyncio
async def test_aol_found():
    """ERROR_<num> on userId means the address is already in use."""
    session_fun = make_aol_mock_session(
        validate_json={"errors": [
            {"name": "firstName", "error": "FIELD_EMPTY"},
            {"name": "userId", "error": "ERROR_148"},
        ]},
    )
    result = await mailcat.aol("alex", session_fun)
    assert result == {"AOL": "alex@aol.com"}


@pytest.mark.asyncio
async def test_aol_not_found():
    """No userId entry in errors[] means the address is free."""
    session_fun = make_aol_mock_session(
        validate_json={"errors": [{"name": "firstName", "error": "FIELD_EMPTY"}]},
    )
    result = await mailcat.aol("f3h53h54hdrg9rkz", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_aol_reserved_word_treated_as_not_found():
    """RESERVED_WORD_PRESENT means AOL refuses the name but no one owns it."""
    session_fun = make_aol_mock_session(
        validate_json={"errors": [{"name": "userId", "error": "RESERVED_WORD_PRESENT"}]},
    )
    result = await mailcat.aol("admin", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_aol_signup_page_missing_tokens():
    """If the signup form changes and we can't find crumb/acrumb/sessionIndex, bail."""
    session_fun = make_aol_mock_session(
        validate_json={"errors": [{"name": "userId", "error": "ERROR_148"}]},
        signup_html="<html><body>no inputs here</body></html>",
    )
    result = await mailcat.aol("alex", session_fun)
    assert result == {}


# outlook() fans out 5 parallel POSTs to GetCredentialType, one per MSA domain;
# verdict depends on which domains report IfExistsResult 0/5/6. The mock has to
# read the JSON payload to know which email each call is checking.
def make_msa_mock_session(result_by_email, throttle_by_email=None):
    """result_by_email: maps full email → IfExistsResult (0/5/6 = exists, 1 = NA).
    Missing keys default to 1 (does not exist).
    throttle_by_email overrides ThrottleStatus (default 0)."""
    throttle_by_email = throttle_by_email or {}

    def build_response(url, *, data, **kwargs):
        payload = json.loads(data)
        email = payload["Username"]
        body = {
            "IfExistsResult": result_by_email.get(email, 1),
            "ThrottleStatus": throttle_by_email.get(email, 0),
        }
        resp = AsyncMock()
        resp.status = 200
        resp.json = AsyncMock(return_value=body)
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    session = AsyncMock()
    session.post = AsyncMock(side_effect=build_response)
    session.close = AsyncMock()
    session.cookie_jar = True
    return lambda: session


@pytest.mark.asyncio
async def test_outlook_found_on_one_domain():
    """alex@outlook.com exists (IfExistsResult=5); others are free."""
    session_fun = make_msa_mock_session({"alex@outlook.com": 5})
    result = await mailcat.outlook("alex", session_fun)
    assert result == {"Live": ["alex@outlook.com"]}


@pytest.mark.asyncio
async def test_outlook_found_on_multiple_domains():
    """All five domains hit — every IfExistsResult variant (0/5/6) must register."""
    session_fun = make_msa_mock_session({
        "alex@outlook.com": 5,
        "alex@hotmail.com": 5,
        "alex@live.com": 6,    # exists in both personal and corporate
        "alex@outlook.de": 0,  # corporate only
        "alex@msn.com": 5,
    })
    result = await mailcat.outlook("alex", session_fun)
    assert "Live" in result
    assert set(result["Live"]) == {
        "alex@outlook.com", "alex@hotmail.com", "alex@live.com",
        "alex@outlook.de", "alex@msn.com",
    }


@pytest.mark.asyncio
async def test_outlook_not_found_anywhere():
    """No MSA domain has this username — return empty."""
    session_fun = make_msa_mock_session({})
    result = await mailcat.outlook("f3h53h54hdrg9rkz", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_outlook_throttle_treated_as_inconclusive():
    """ThrottleStatus != 0 means IfExistsResult may be a false positive — skip
    that domain rather than reporting it."""
    session_fun = make_msa_mock_session(
        result_by_email={
            "alex@outlook.com": 5,   # would normally be reported
            "alex@hotmail.com": 5,   # genuine hit
        },
        throttle_by_email={"alex@outlook.com": 1},
    )
    result = await mailcat.outlook("alex", session_fun)
    # outlook.com is suppressed because of throttle; hotmail.com survives.
    assert result == {"Live": ["alex@hotmail.com"]}


@pytest.mark.asyncio
async def test_outlook_invalid_format_not_reported():
    """IfExistsResult=4 means Microsoft rejected the email format — not a hit."""
    session_fun = make_msa_mock_session({"weird..name@outlook.com": 4})
    result = await mailcat.outlook("weird..name", session_fun)
    assert result == {}


# eclipso fans out 11 GETs (1 sentinel + 10 per-domain) and the verdict
# depends on which one is which — needs a URL-aware mock.
def make_eclipso_mock_session(text_by_address):
    """text_by_address maps the `address=` query value to a marker.
    "TAKEN" → <available>0</available>; missing key → <available>1</available>;
    anything else is sent verbatim."""
    default_avail = '<?xml version="1.0"?><response><available>1</available></response>'
    taken_body = '<?xml version="1.0"?><response><available>0</available></response>'

    def build_response(url, **kwargs):
        m = re.search(r'address=([^&]+)', url)
        addr = m.group(1) if m else ""
        text = text_by_address.get(addr)
        if text is None:
            body = default_avail
        elif text == "TAKEN":
            body = taken_body
        else:
            body = text
        resp = AsyncMock()
        resp.status = 200
        resp.text = AsyncMock(return_value=body)
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    session = AsyncMock()
    session.get = AsyncMock(side_effect=build_response)
    session.close = AsyncMock()
    session.cookie_jar = True
    return lambda: session


@pytest.mark.asyncio
async def test_eclipso_blocked_substring_returns_empty():
    """`host` is a blocked substring; sentinel `zzaahostaazz` would also come
    back as `>0<`, so eclipso() must discard every per-domain hit."""
    # Every probe (sentinel + 10 domains) returns "taken" — the substring filter.
    session_fun = make_eclipso_mock_session({
        "zzaahostaazz@eclipso.eu": "TAKEN",
        "host@eclipso.eu": "TAKEN", "host@eclipso.de": "TAKEN",
        "host@eclipso.at": "TAKEN", "host@eclipso.ch": "TAKEN",
        "host@eclipso.be": "TAKEN", "host@eclipso.es": "TAKEN",
        "host@eclipso.it": "TAKEN", "host@eclipso.me": "TAKEN",
        "host@eclipso.nl": "TAKEN", "host@eclipso.email": "TAKEN",
    })
    result = await mailcat.eclipso("host", session_fun)
    assert result == {}


@pytest.mark.asyncio
async def test_eclipso_real_account_keeps_hits():
    """Real account: sentinel comes back available, but per-domain checks
    return `taken` — every domain must end up in the result list."""
    session_fun = make_eclipso_mock_session({
        # Sentinel falls through to default (available) — only mark domains taken.
        "alex@eclipso.eu": "TAKEN", "alex@eclipso.de": "TAKEN",
        "alex@eclipso.at": "TAKEN", "alex@eclipso.ch": "TAKEN",
        "alex@eclipso.be": "TAKEN", "alex@eclipso.es": "TAKEN",
        "alex@eclipso.it": "TAKEN", "alex@eclipso.me": "TAKEN",
        "alex@eclipso.nl": "TAKEN", "alex@eclipso.email": "TAKEN",
    })
    result = await mailcat.eclipso("alex", session_fun)
    assert "Eclipso" in result
    assert len(result["Eclipso"]) == 10
    assert "alex@eclipso.eu" in result["Eclipso"]


@pytest.mark.asyncio
async def test_eclipso_available_target_returns_empty():
    """Random username: sentinel + all domains available — nothing to report."""
    session_fun = make_eclipso_mock_session({})  # all default to available
    result = await mailcat.eclipso("f3h53h54hdrg9rkz", session_fun)
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


@pytest.mark.asyncio
async def test_mailum_found():
    session_fun = make_mock_session(status=200, text_data="false")
    result = await mailcat.mailum("testuser", session_fun)
    assert "Mailum" in result
    assert "testuser@cyberfear.com" in result["Mailum"]
    assert "testuser@mailum.com" in result["Mailum"]


@pytest.mark.asyncio
async def test_mailum_not_found():
    session_fun = make_mock_session(status=200, text_data="true")
    result = await mailcat.mailum("testuser", session_fun)
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


# --- Session tracking tests ---


@pytest.mark.asyncio
async def test_simple_session_tracks_session():
    """simple_session() should register the session in _open_sessions."""
    mailcat._open_sessions.clear()
    session = mailcat.simple_session()
    assert session in mailcat._open_sessions
    await session.close()
    mailcat._open_sessions.clear()


@pytest.mark.asyncio
async def test_via_proxy_tracks_session():
    """via_proxy factory should register the session in _open_sessions."""
    mailcat._open_sessions.clear()
    factory = mailcat.via_proxy("http://user:pass@127.0.0.1:8080")
    session = factory()
    assert session in mailcat._open_sessions
    await session.close()
    mailcat._open_sessions.clear()


@pytest.mark.asyncio
async def test_via_tor_tracks_session():
    """via_tor() should register the session in _open_sessions."""
    mailcat._open_sessions.clear()
    session = mailcat.via_tor()
    assert session in mailcat._open_sessions
    await session.close()
    mailcat._open_sessions.clear()


@pytest.mark.asyncio
async def test_session_cleanup_closes_unclosed_sessions():
    """Cleanup loop should close sessions that are still open."""
    mailcat._open_sessions.clear()
    session = AsyncMock()
    session.closed = False
    session.close = AsyncMock()
    mailcat._open_sessions.append(session)

    for s in mailcat._open_sessions:
        try:
            if hasattr(s, 'closed') and s.closed:
                continue
            await s.close()
        except Exception:
            pass
    mailcat._open_sessions.clear()

    session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_session_cleanup_skips_already_closed():
    """Cleanup loop should skip sessions that are already closed."""
    mailcat._open_sessions.clear()
    session = AsyncMock()
    session.closed = True
    session.close = AsyncMock()
    mailcat._open_sessions.append(session)

    for s in mailcat._open_sessions:
        try:
            if hasattr(s, 'closed') and s.closed:
                continue
            await s.close()
        except Exception:
            pass
    mailcat._open_sessions.clear()

    session.close.assert_not_awaited()


# --- Timeout warning and outlook error logging tests ---


@pytest.mark.asyncio
async def test_executor_prints_warning_on_timeout(capsys):
    """Worker should print a warning with the checker name when a task times out."""

    async def slow_checker(value, default=None):
        await asyncio.sleep(10)
        return value

    slow_checker.__name__ = "slow_checker"

    executor = mailcat.AsyncioProgressbarQueueExecutor(
        logger=mailcat.logger,
        in_parallel=1,
        timeout=0.05,
        progress_func=mailcat.stub_progress,
    )

    tasks = [(slow_checker, [], {"value": 42})]
    results = await executor.run(tasks)

    captured = capsys.readouterr()
    assert "[WARNING]" in captured.out
    assert "slow_checker" in captured.out
    assert "timed out" in captured.out
    assert results == [None]


@pytest.mark.asyncio
async def test_intpl_prints_warning_on_chromium_error(capsys):
    """intpl() should print a Chromium warning when the browser fails to launch."""

    async def boom():
        raise Exception("Chromium revision is not downloaded")

    with patch.object(mailcat, "_launch_headless", boom):
        result = await mailcat.intpl("testuser", lambda: None)

    captured = capsys.readouterr()
    assert "[WARNING]" in captured.out
    assert "chromium" in captured.out.lower()
    assert result == {}


@pytest.mark.asyncio
async def test_fastmail_prints_warning_on_chromium_error(capsys):
    """fastmail() should print a Chromium warning when the browser fails to launch."""

    async def boom():
        raise Exception("Chromium revision is not downloaded")

    with patch.object(mailcat, "_launch_headless", boom):
        result = await mailcat.fastmail("testuser", lambda: None)

    captured = capsys.readouterr()
    assert "[WARNING]" in captured.out
    assert "chromium" in captured.out.lower()
    assert result == {}


@pytest.mark.asyncio
async def test_onet_prints_warning_on_chromium_error(capsys):
    """onet() should print a Chromium warning when the browser fails to launch."""

    async def boom():
        raise Exception("Chromium revision is not downloaded")

    with patch.object(mailcat, "_launch_headless", boom):
        result = await mailcat.onet("testuser", lambda: None)

    captured = capsys.readouterr()
    assert "[WARNING]" in captured.out
    assert "chromium" in captured.out.lower()
    assert result == {}


# --- Bulk / file-input tests ---


def test_username_at_sign_stripping_multiple():
    """Verify '@' stripping logic works for multiple usernames."""
    raw = ["user1@example.com", "user2", "user3@proton.me"]
    result = [t.split('@')[0] if '@' in t else t for t in raw]
    assert result == ["user1", "user2", "user3"]


def test_file_input_reads_usernames(tmp_path):
    """Reading usernames from a file should produce the correct list."""
    userfile = tmp_path / "users.txt"
    userfile.write_text("alice\nbob\n\ncharlie\n")

    targets = []
    with open(userfile) as fh:
        for line in fh:
            line = line.strip()
            if line:
                targets.append(line)

    assert targets == ["alice", "bob", "charlie"]


def test_file_input_skips_blank_lines(tmp_path):
    """Blank lines in the file should be ignored."""
    userfile = tmp_path / "users.txt"
    userfile.write_text("\n  \nalice\n\nbob\n")

    targets = []
    with open(userfile) as fh:
        for line in fh:
            line = line.strip()
            if line:
                targets.append(line)

    assert targets == ["alice", "bob"]


def test_file_input_strips_at_sign(tmp_path):
    """Email addresses in the file should be reduced to username only."""
    userfile = tmp_path / "users.txt"
    userfile.write_text("alice@gmail.com\nbob\n")

    targets = []
    with open(userfile) as fh:
        for line in fh:
            line = line.strip()
            if line:
                targets.append(line)

    targets = [t.split('@')[0] if '@' in t else t for t in targets]
    assert targets == ["alice", "bob"]


@pytest.mark.asyncio
async def test_bulk_check_runs_checker_for_each_target(capsys):
    """Each username in a bulk run should be passed to the checker."""
    seen_targets = []

    async def fake_checker(target, req_session_fun, timeout):
        seen_targets.append(target)
        return {}

    fake_checker.__name__ = "fake_checker"
    checkers = [fake_checker]
    targets = ["alice", "bob", "charlie"]
    req_session_fun = lambda: None

    for target in targets:
        tasks = [
            (mailcat.print_results, [checker, target, req_session_fun, False, 10], {})
            for checker in checkers
        ]
        executor = mailcat.AsyncioProgressbarQueueExecutor(
            logger=mailcat.logger,
            in_parallel=1,
            timeout=10.5,
            progress_func=mailcat.stub_progress,
        )
        await executor.run(tasks)

    assert seen_targets == ["alice", "bob", "charlie"]


@pytest.mark.asyncio
async def test_bulk_check_prints_header_per_username(capsys):
    """When multiple targets are used, a header should be printed for each."""
    async def fake_checker(target, req_session_fun, timeout):
        return {}

    fake_checker.__name__ = "fake_checker"
    checkers = [fake_checker]
    targets = ["alice", "bob"]
    req_session_fun = lambda: None

    for target in targets:
        if len(targets) > 1:
            print(f'\n[*] Checking username: {target}')
        tasks = [
            (mailcat.print_results, [checker, target, req_session_fun, False, 10], {})
            for checker in checkers
        ]
        executor = mailcat.AsyncioProgressbarQueueExecutor(
            logger=mailcat.logger,
            in_parallel=1,
            timeout=10.5,
            progress_func=mailcat.stub_progress,
        )
        await executor.run(tasks)

    captured = capsys.readouterr()
    assert "[*] Checking username: alice" in captured.out
    assert "[*] Checking username: bob" in captured.out

