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
