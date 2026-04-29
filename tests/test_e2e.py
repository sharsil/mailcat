"""End-to-end tests with real network requests.

Run with:  python -m pytest tests/test_e2e.py --e2e -v
"""

import pytest

import mailcat

e2e = pytest.mark.e2e


# --- alex (common username, many providers have it) ---


@e2e
@pytest.mark.asyncio
async def test_gmail_alex():
    result, error = await mailcat.gmail("alex", mailcat.simple_session)
    assert not error
    assert result == {"Google": "alex@gmail.com"}


@e2e
@pytest.mark.asyncio
async def test_yandex_alex():
    result, error = await mailcat.yandex("alex", mailcat.simple_session)
    assert not error
    assert "Yandex" in result
    assert "alex@yandex.ru" in result["Yandex"]


@e2e
@pytest.mark.asyncio
async def test_proton_alex():
    """Proton may rate-limit or require captcha — treat empty as acceptable."""
    result = await mailcat.proton("alex", mailcat.simple_session)
    if result:
        assert "Proton" in result
        assert "alex@protonmail.com" in result["Proton"]


@e2e
@pytest.mark.asyncio
async def test_posteo_alex():
    result = await mailcat.posteo("alex", mailcat.simple_session)
    assert "Posteo" in result
    assert "alex@posteo.net" in result["Posteo"]


@e2e
@pytest.mark.asyncio
async def test_duckgo_alex():
    result = await mailcat.duckgo("alex", mailcat.simple_session)
    assert result == {"DuckGo": "alex@duck.com"}


@e2e
@pytest.mark.asyncio
async def test_emailn_alex():
    result = await mailcat.emailn("alex", mailcat.simple_session)
    assert result == {"emailn": "alex@emailn.de"}


@e2e
@pytest.mark.asyncio
async def test_vivaldi_alex():
    result = await mailcat.vivaldi("alex", mailcat.simple_session)
    assert result == {"Vivaldi": "alex@vivaldi.net"}


@e2e
@pytest.mark.asyncio
async def test_ukrnet_alex():
    result = await mailcat.ukrnet("alex", mailcat.simple_session)
    assert result == {"UkrNet": "alex@ukr.net"}


@e2e
@pytest.mark.asyncio
async def test_mailDe_alex():
    """SMTP check — MX server may silently refuse."""
    result, error = await mailcat.mailDe("alex", mailcat.simple_session)
    if result:
        assert result == {"mail.de": "alex@mail.de"}


@e2e
@pytest.mark.asyncio
async def test_firemail_alex():
    result = await mailcat.firemail("alex", mailcat.simple_session)
    assert "Firemail" in result
    assert "alex@firemail.de" in result["Firemail"]


@e2e
@pytest.mark.asyncio
async def test_eclipso_alex():
    result = await mailcat.eclipso("alex", mailcat.simple_session)
    assert "Eclipso" in result
    assert len(result["Eclipso"]) > 0


@e2e
@pytest.mark.asyncio
async def test_startmail_alex():
    result = await mailcat.startmail("alex", mailcat.simple_session)
    assert result == {"StartMail": "alex@startmail.com"}


@e2e
@pytest.mark.asyncio
async def test_runbox_alex():
    result = await mailcat.runbox("alex", mailcat.simple_session)
    assert "Runbox" in result
    assert any(addr.startswith("alex@") for addr in result["Runbox"])


@e2e
@pytest.mark.asyncio
async def test_aikq_alex():
    """aikq.de uses a self-signed-style cert chain that fails on some hosts;
    treat empty as acceptable."""
    result = await mailcat.aikq("alex", mailcat.simple_session)
    if result:
        assert "Aikq" in result
        assert any(addr.startswith("alex@") for addr in result["Aikq"])


@e2e
@pytest.mark.asyncio
async def test_tpl_alex():
    result = await mailcat.tpl("alex", mailcat.simple_session)
    assert "T.pl" in result
    assert "alex@t.pl" in result["T.pl"]


@e2e
@pytest.mark.asyncio
async def test_zoho_alex():
    result = await mailcat.zoho("alex", mailcat.simple_session)
    assert result == {"Zoho": "alex@zohomail.com"}


@e2e
@pytest.mark.asyncio
async def test_rambler_alex():
    result = await mailcat.rambler("alex", mailcat.simple_session)
    assert "Rambler" in result
    assert "alex@rambler.ru" in result["Rambler"]


@e2e
@pytest.mark.asyncio
async def test_interia_alex():
    """Interia rate-limits — at least one of its 11 domains should match alex."""
    result = await mailcat.interia("alex", mailcat.simple_session)
    if result:
        assert "Interia" in result
        assert any(addr.startswith("alex@") for addr in result["Interia"])


@e2e
@pytest.mark.asyncio
async def test_yahoo_alex():
    """Yahoo cookies/crumb expire periodically; if they did, treat as inconclusive."""
    result = await mailcat.yahoo("alex", mailcat.simple_session)
    if result:
        assert result == {"Yahoo": "alex@yahoo.com"}


@e2e
@pytest.mark.asyncio
async def test_outlook_alex():
    """Headless Chromium drives signup.live.com — alex@outlook.com is taken."""
    result = await mailcat.outlook("alex", mailcat.simple_session)
    assert "Live" in result
    assert "alex@outlook.com" in result["Live"]


@e2e
@pytest.mark.asyncio
async def test_intpl_alex():
    """Headless Chromium drives int.pl/#/register — alex@int.pl is taken."""
    result = await mailcat.intpl("alex", mailcat.simple_session)
    assert result == {"int.pl": "alex@int.pl"}


@e2e
@pytest.mark.asyncio
async def test_fastmail_alex():
    """Headless Chromium captures JMAP /signup/api response — alex@fastmail.com is taken."""
    result = await mailcat.fastmail("alex", mailcat.simple_session)
    assert result == {"Fastmail": "alex@fastmail.com"}


@e2e
@pytest.mark.asyncio
async def test_onet_alex():
    """Headless Chromium drives konto.onet.pl/register — alex is taken on every onet domain."""
    result = await mailcat.onet("alex", mailcat.simple_session)
    assert "Onet" in result
    assert "alex@onet.pl" in result["Onet"]


# --- soxoj ---


@e2e
@pytest.mark.asyncio
async def test_proton_soxoj():
    result = await mailcat.proton("soxoj", mailcat.simple_session)
    if result:
        assert "Proton" in result
        assert "soxoj@protonmail.com" in result["Proton"]


@e2e
@pytest.mark.asyncio
async def test_mailru_soxoj():
    result = await mailcat.mailRu("soxoj", mailcat.simple_session)
    assert "MailRU" in result
    assert "soxoj@bk.ru" in result["MailRU"]


@e2e
@pytest.mark.asyncio
async def test_gmail_soxoj():
    """soxoj@gmail.com should not exist."""
    result, error = await mailcat.gmail("soxoj", mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_duckgo_soxoj():
    """soxoj@duck.com should not exist."""
    result = await mailcat.duckgo("soxoj", mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_vivaldi_soxoj():
    """soxoj@vivaldi.net should not exist."""
    result = await mailcat.vivaldi("soxoj", mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_emailn_soxoj():
    """soxoj@emailn.de should not exist."""
    result = await mailcat.emailn("soxoj", mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_mailum_admin():
    result = await mailcat.mailum("admin", mailcat.simple_session)
    assert "Mailum" in result
    assert "admin@cyberfear.com" in result["Mailum"]


# --- random non-existent username (should return empty for working checkers) ---


RANDOM_USERNAME = "f3h53h54hdrg9rkz"


@e2e
@pytest.mark.asyncio
async def test_posteo_random_empty():
    result = await mailcat.posteo(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_startmail_random_empty():
    result = await mailcat.startmail(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_firemail_random_empty():
    result = await mailcat.firemail(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_runbox_random_empty():
    result = await mailcat.runbox(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_eclipso_random_empty():
    result = await mailcat.eclipso(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_tpl_random_empty():
    result = await mailcat.tpl(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_zoho_random_empty():
    result = await mailcat.zoho(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_proton_random_empty():
    result = await mailcat.proton(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_mailRu_random_empty():
    result = await mailcat.mailRu(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_rambler_random_empty():
    result = await mailcat.rambler(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_interia_random_empty():
    result = await mailcat.interia(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_yahoo_random_empty():
    result = await mailcat.yahoo(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_outlook_random_empty():
    result = await mailcat.outlook(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_intpl_random_empty():
    result = await mailcat.intpl(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_fastmail_random_empty():
    result = await mailcat.fastmail(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}


@e2e
@pytest.mark.asyncio
async def test_onet_random_empty():
    result = await mailcat.onet(RANDOM_USERNAME, mailcat.simple_session)
    assert result == {}
