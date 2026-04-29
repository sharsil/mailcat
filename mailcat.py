#!/usr/bin/env python3
import aiohttp
import asyncio
import argparse
import datetime
import json
import logging
import random
import aiosmtplib
import string as s
import sys
import time
import re
from time import sleep
from typing import Iterable, Dict, List, Callable, Tuple, Any

import dns.resolver

import tqdm
# uses pyppeteer
from requests_html import AsyncHTMLSession  # type: ignore
from aiohttp_socks import ProxyConnector


# TODO: move to main function
uaLst = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.106 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36"
]

logging.getLogger('asyncio').setLevel(logging.CRITICAL)
logging.basicConfig(format='%(message)s')
logger = logging.getLogger('mailcat')
logger.setLevel(100)

QueryDraft = Tuple[Callable, List, Dict]


class stub_progress:
    def __init__(self, total):
        pass

    def update(self, *args, **kwargs):
        pass

    def close(self, *args, **kwargs):
        pass

def create_task_func():
    if sys.version_info.minor > 6:
        create_asyncio_task = asyncio.create_task
    else:
        loop = asyncio.get_event_loop()
        create_asyncio_task = loop.create_task
    return create_asyncio_task


class AsyncExecutor:
    def __init__(self, *args, **kwargs):
        self.logger = kwargs['logger']

    async def run(self, tasks: Iterable[QueryDraft]):
        start_time = time.time()
        results = await self._run(tasks)
        self.execution_time = time.time() - start_time
        self.logger.debug(f'Spent time: {self.execution_time}')
        return results

    async def _run(self, tasks: Iterable[QueryDraft]):
        await asyncio.sleep(0)


class AsyncioProgressbarQueueExecutor(AsyncExecutor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workers_count = kwargs.get('in_parallel', 10)
        self.progress_func = kwargs.get('progress_func', tqdm.tqdm)
        self.queue = asyncio.Queue(self.workers_count)
        self.timeout = kwargs.get('timeout')

    async def increment_progress(self, count):
        update_func = self.progress.update
        if asyncio.iscoroutinefunction(update_func):
            await update_func(count)
        else:
            update_func(count)
        await asyncio.sleep(0)

    async def stop_progress(self):
        stop_func = self.progress.close
        if asyncio.iscoroutinefunction(stop_func):
            await stop_func()
        else:
            stop_func()
        await asyncio.sleep(0)

    async def worker(self):
        while True:
            try:
                f, args, kwargs = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                return

            query_future = f(*args, **kwargs)
            query_task = create_task_func()(query_future)
            try:
                result = await asyncio.wait_for(query_task, timeout=self.timeout)
            except asyncio.TimeoutError:
                query_task.cancel()
                checker_name = _get_checker_name(f, args)
                print(f'[WARNING] {checker_name} check timed out after {int(self.timeout)}s. '
                      f'Use -t <seconds> to increase the timeout.')
                result = kwargs.get('default')

            self.results.append(result)
            await self.increment_progress(1)
            self.queue.task_done()

    async def _run(self, queries: Iterable[QueryDraft]):
        self.results: List[Any] = []

        queries_list = list(queries)

        min_workers = min(len(queries_list), self.workers_count)

        workers = [create_task_func()(self.worker()) for _ in range(min_workers)]

        self.progress = self.progress_func(total=len(queries_list))

        for t in queries_list:
            await self.queue.put(t)

        await self.queue.join()

        for w in workers:
            w.cancel()

        await self.stop_progress()
        return self.results


def randstr(num):
    return ''.join(random.sample((s.ascii_lowercase + s.ascii_uppercase + s.digits), num))


async def sleeper(sList, s_min, s_max):
    for ind in sList:
        if sList.index(ind) < (len(sList) - 1):
            await asyncio.sleep(random.uniform(s_min, s_max))


_open_sessions = []

_CHROMIUM_ERROR_KEYWORDS = ('chromium', 'download', 'browser', 'executable',
                             'failed to launch', 'could not find', 'pyppeteer')


def _get_checker_name(f: Callable, args: List) -> str:
    """Return the display name for a checker task given its function and positional args."""
    if args and hasattr(args[0], '__name__'):
        return args[0].__name__
    if hasattr(f, '__name__'):
        return f.__name__
    return 'unknown'


def via_proxy(proxy_str):
    def via():
        connector = ProxyConnector.from_url(proxy_str)
        session = aiohttp.ClientSession(connector=connector)
        _open_sessions.append(session)
        return session

    return via


def via_tor():
    connector = ProxyConnector.from_url('socks5://127.0.0.1:9050')
    session = aiohttp.ClientSession(connector=connector)
    _open_sessions.append(session)
    return session


def simple_session():
    session = aiohttp.ClientSession()
    _open_sessions.append(session)
    return session


async def code250(mailProvider, target, timeout=10):
    target = target
    providerLst = []

    error = ''

    randPref = ''.join(random.sample(s.ascii_lowercase, 6))
    fromAddress = f"{randPref}@{mailProvider}"
    targetMail = f"{target}@{mailProvider}"

    records = dns.resolver.Resolver().resolve(mailProvider, 'MX')
    mxRecord = records[0].exchange
    mxRecord = str(mxRecord)

    try:
        server = aiosmtplib.SMTP(timeout=timeout, validate_certs=False)
        # server.set_debuglevel(0)

        await server.connect(hostname=mxRecord)
        await server.helo()
        await server.mail(fromAddress)
        code, message = await server.rcpt(targetMail)

        if code == 250:
            providerLst.append(targetMail)

        message_str = message.lower()
        if 'ban' in message_str or 'denied' in message_str:
            error = message_str

    except aiosmtplib.errors.SMTPRecipientRefused:
        pass
    except Exception as e:
        logger.error(e, exc_info=True)
        error = str(e)

    return providerLst, error


async def gmail(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}
    gmailChkLst, error = await code250("gmail.com", target, kwargs.get('timeout', 10))
    if gmailChkLst:
        result["Google"] = gmailChkLst[0]

    await asyncio.sleep(0)
    return result, error


async def yandex(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}
    yaAliasesLst = ["yandex.by",
                    "yandex.kz",
                    "yandex.ua",
                    "yandex.com",
                    "ya.ru"]
    yaChkLst, error = await code250("yandex.ru", target, kwargs.get('timeout', 10))
    if yaChkLst:
        yaAliasesLst = [f'{target}@{yaAlias}' for yaAlias in yaAliasesLst]
        yaMails = list(set(yaChkLst + yaAliasesLst))
        result["Yandex"] = yaMails

    await asyncio.sleep(0)
    return result, error


async def proton(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    protonLst = ["protonmail.com", "protonmail.ch", "pm.me", "proton.me"]
    protonSucc = []
    sreq = req_session_fun()

    appversion = "web-account@5.0.290.0"
    base_headers = {"User-Agent": random.choice(uaLst),
                    "Accept": "application/vnd.protonmail.v1+json",
                    "x-pm-appversion": appversion}
    # Proton intentionally throttles the availability endpoint by ~10s, so the
    # request timeout has to be larger than the typical 5s default.
    outer_timeout = args[0] if args else kwargs.get('timeout', 20)
    request_timeout = max(outer_timeout - 1, 15)

    try:
        sess = await sreq.post("https://account.proton.me/api/auth/v4/sessions",
                               headers={**base_headers, "Content-Type": "application/json"},
                               json={}, timeout=request_timeout)
        async with sess:
            if sess.status != 200:
                return result
            sess_data = await sess.json()
            access_token = sess_data["AccessToken"]
            uid = sess_data["UID"]

        protonURL = f"https://account.proton.me/api/users/available?Name={target}"
        auth_headers = {**base_headers,
                        "Authorization": f"Bearer {access_token}",
                        "x-pm-uid": uid}

        chkProton = await sreq.get(protonURL, headers=auth_headers, timeout=request_timeout)
        async with chkProton:
            if chkProton.status == 409:
                resp = await chkProton.json()
                if resp.get('Error') == "Username already used":
                    protonSucc = [f"{target}@{protodomain}" for protodomain in protonLst]

    except Exception as e:
        logger.error(e, exc_info=True)

    if protonSucc:
        result["Proton"] = protonSucc

    await sreq.close()

    return result


async def mailRu(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    # headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; rv:68.0) Gecko/20100101 Firefox/68.0', 'Referer': 'https://account.mail.ru/signup?from=main&rf=auth.mail.ru'}
    mailRU = ["mail.ru", "bk.ru", "inbox.ru", "list.ru", "internet.ru"]
    mailRuSucc = []
    sreq = req_session_fun()

    for maildomain in mailRU:
        try:
            headers = {'User-Agent': random.choice(uaLst)}
            mailruMail = f"{target}@{maildomain}"
            data = {'email': mailruMail}

            chkMailRU = await sreq.post('https://account.mail.ru/api/v1/user/exists', headers=headers, data=data, timeout=5)

            async with chkMailRU:
                if chkMailRU.status == 200:
                    resp = await chkMailRU.json()
                    if resp['body']['exists']:
                        mailRuSucc.append(mailruMail)

        except Exception as e:
            logger.error(e, exc_info=True)

        await asyncio.sleep(random.uniform(0.5, 2))

    if mailRuSucc:
        result["MailRU"] = mailRuSucc

    await sreq.close()

    return result


async def rambler(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    ramblerMail = ["rambler.ru", "lenta.ru", "autorambler.ru", "myrambler.ru", "ro.ru", "rambler.ua"]
    ramblerSucc = []
    sreq = req_session_fun()
    timeout = kwargs.get('timeout', 5)
    ramblerChkURL = "https://id.rambler.ru/jsonrpc"

    async def check_one(maildomain):
        targetMail = f"{target}@{maildomain}"
        headers = {"User-Agent": random.choice(uaLst),
                   "Content-Type": "application/json",
                   "Origin": "https://id.rambler.ru",
                   "X-Client-Request-Id": randstr(20)}
        ramblerJSON = {"method": "Rambler::Id::login_available",
                       "params": [{"username": target, "realm": maildomain}],
                       "rpc": "2.0"}
        try:
            ramblerChk = await sreq.post(ramblerChkURL, headers=headers, json=ramblerJSON, timeout=timeout)
            async with ramblerChk:
                if ramblerChk.status == 200:
                    resp = await ramblerChk.json(content_type=None)
                    profile = resp.get('result', {}).get('profile')
                    if profile and profile.get('status') == 'exist':
                        return targetMail
        except Exception as e:
            logger.error(e, exc_info=True)
        return None

    checked = await asyncio.gather(*(check_one(d) for d in ramblerMail))
    ramblerSucc = [m for m in checked if m]

    if ramblerSucc:
        result["Rambler"] = ramblerSucc

    await sreq.close()

    return result


# DEPRECATED — not in CHECKERS.
# Why: the old endpoint `mail.tutanota.com/rest/sys/mailaddressavailabilityservice`
# returns 404 (tutanota → tuta migration). The new
# `MultipleMailAddressAvailabilityService` in tutao/tutanota requires a
# `signupToken` derived from solving an hCaptcha during the multi-step
# plan-selection signup. Headless can navigate to the Username step but the
# actual availability XHR only fires after hCaptcha is solved.
# How to revive: integrate a paid hCaptcha-solver to obtain a `signupToken`,
# then drive the captured XHR through the headless page context.
async def tuta(target, req_session_fun, *args, **kwargs) -> Dict:
    print('[DEPRECATED] tuta is unmaintained — needs hCaptcha-solver. See comment in mailcat.py.')
    result = {}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36'}

    tutaMail = ["tutanota.com", "tutanota.de", "tutamail.com", "tuta.io", "keemail.me"]
    tutaSucc = []
    sreq = req_session_fun()

    for maildomain in tutaMail:

        try:

            targetMail = f"{target}@{maildomain}"
            tutaURL = "https://mail.tutanota.com/rest/sys/mailaddressavailabilityservice?_body="

            tutaCheck = await sreq.get(
                f'{tutaURL}%7B%22_format%22%3A%220%22%2C%22mailAddress%22%3A%22{target}%40{maildomain}%22%7D',
                headers=headers,
                timeout=kwargs.get('timeout', 5),
            )


            async with tutaCheck:
                if tutaCheck.status == 200:
                    resp = await tutaCheck.json()
                    exists = resp['available']

                    if exists == "0":
                        tutaSucc.append(targetMail)

            await asyncio.sleep(random.uniform(2, 4))

        except Exception as e:
            logger.error(e, exc_info=True)

    if tutaSucc:
        result["Tutanota"] = tutaSucc

    await sreq.close()

    return result


# Yahoo's signup-validation endpoint requires a live session: cookies (A3/AS/A1)
# bound to a freshly-issued crumb+acrumb pair. They expire (typically within hours).
# To refresh, open https://login.yahoo.com/account/create in a browser, capture the
# request to /account/create/validate?validateField=userId from DevTools → Network,
# and update the values below from the request's Cookie header and form body.
YAHOO_COOKIE = (
    "A3=d=AQABBJK4K2UCEAWUDcjLIvEH-c6KG8c1eMIFEgABCAH-LGVdZe2Nb2UB9qMCAAcIhrgrZTGnS40&S=AQAAAkx3bsNQC6tBk4t5FhyfwjM; "
    "AS=v=1&s=JK0QUN1R&d=A69ef978c|vs7EcUH.2TpK2gUo.ZVIpkF5DCTlDJBGf00jlfYWcX2xKq5_HvBg_h9UXRF3T9c66GOoQMnFvEEizSFimaGjFx8iW7DxAU8JI4iGQ8dZ5AT5Ykl51ov.Wy0tzyXOjOO3z5kJXqG4_JqLZ4O4znc49QLFUzP7WWjFe8.TPIRZT.jtycb5UjMpawQSYRO369OeO_Ag7Rfy0FVB5P1vltnPwktxq8QzXT5lwL.n3zc3TgvrT1aZdFbytNQWsFGAcN7rSV8iReYIZ9qgi1b5Hf7vEJk1sedp.xqeLvlQ1AQm_A.91o.biw10MJrZWQFEeuqCu4vt09EehxmHIQIPh6h_XK7sS.IBznmRi0I_M2yYWsvcJ6Y._lNdC60adEb6SpHK408YwYPTBMoFa2_EePVrMPRzJIO0fxzkGn0CTBhUunt8KJ0FPENDBPFhmC8J711DD_UGamWyTKoG.38D_vRAd2hnkB_eqCDHY2ym3xO.Bpp98zl4Mhtc9O00DkRWbPeg9becHdRhAf6dJlpgTwKnHD1Ya30CeJY.etu8RU7xuEi7gIh6ZtU.Bj4n7N4xbUz6tJMwKI6AdVv2YJebFmthDixCY40F.Wkfe6nSQhS8RmfNcXpIAXGzBel5Vz1VozGfQ5042GIUE6SvD38fRqz1hcXYdiCNq9u1unnJsaZCn7gB.3OVfz63GUcQpIO2s1rXOJzYDRIllPc.GmsktUcHEbkCAIBdPr4en5I4BB_7G3LDQJZFKDJkMWivxWOiXJ0ZNU2_TFS9mkJ5AgiAtGwQOtk7aRhPH5UDJazcxR_MDKVCRelKUJl.hc1blPX6qznnQmyXXqST39Cfupr5OYQZLpJkWjuwdBKyW8f5zzLn.Lxwas51t.wocOdL.oLk.TmJ18v2NQtllTToakTUttO5dq1XrFpo2rkV.tLSITRwW1a0.iu1txVqMHweTqU6AMg9efhUtkR8UTq95rhtp_6qft35Ysq1v1pnJutIWs0HTyAud9o7a7O.fD46CwQDRKK6jhJCWtNOS099vYgu19AE9L0Wp9N5b0WG1s34jBHpP34sLY3whb8mKec8AwbBS6IFOOyUEiCPpLRMmkbCRNF654eNkvmX7K9c2NvZXiiHNCh5a7J7D9dvvDftr7XM572uPPYdxq1xGKm5hbALux7mghpbcLdkpR7i_KL247pSaqhCmi6BTTiY0Wo5AA--~A; "
    "A1=d=AQABBJK4K2UCEAWUDcjLIvEH-c6KG8c1eMIFEgABCAH-LGVdZe2Nb2UB9qMCAAcIhrgrZTGnS40&S=AQAAAkx3bsNQC6tBk4t5FhyfwjM; "
    "A1S=d=AQABBJK4K2UCEAWUDcjLIvEH-c6KG8c1eMIFEgABCAH-LGVdZe2Nb2UB9qMCAAcIhrgrZTGnS40&S=AQAAAkx3bsNQC6tBk4t5FhyfwjM"
)
YAHOO_CRUMB = "75kxC0BSq7bTHCD/60yaQ"
YAHOO_ACRUMB = "JK0QUN1R"
YAHOO_SESSION_INDEX = "QQ--"


async def yahoo(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    yahooURL = "https://login.yahoo.com/account/create/validate?validateField=userId"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://login.yahoo.com",
        "Referer": "https://login.yahoo.com/account/create",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": YAHOO_COOKIE,
    }
    data = {
        "sessionIndex": YAHOO_SESSION_INDEX,
        "acrumb": YAHOO_ACRUMB,
        "crumb": YAHOO_CRUMB,
        "specId": "yidregsimplified",
        "context": "REGISTRATION",
        "attrSetIndex": "0",
        "tos0": "oath_freereg|nl|nl-NL",
        "lastName": "r",
        "yidDomain": "yahoo.com",
        "userId": target,
    }
    sreq = req_session_fun()

    try:
        yahooChk = await sreq.post(yahooURL, headers=headers, data=data, timeout=kwargs.get('timeout', 5))
        async with yahooChk:
            if yahooChk.status == 200:
                resp = await yahooChk.json(content_type=None)
                err = resp.get("fields", {}).get("userId", {}).get("error", {})
                if err and err.get("id") == "IDENTIFIER_NOT_AVAILABLE":
                    result["Yahoo"] = f"{target}@yahoo.com"
    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result


async def _launch_headless():
    """Launch a headless Chromium instance with anti-fingerprinting flags.
    Caller is responsible for closing it."""
    from pyppeteer import launch
    return await launch(headless=True, handleSIGINT=False, handleSIGTERM=False, handleSIGHUP=False,
                        args=['--no-sandbox', '--disable-blink-features=AutomationControlled'])


def _is_chromium_error(err_str: str) -> bool:
    return any(kw in err_str.lower() for kw in _CHROMIUM_ERROR_KEYWORDS)


async def outlook(target, req_session_fun, *args, **kwargs) -> Dict:
    """Check outlook.com / hotmail.com by submitting the email through the live
    signup form in headless Chromium and inspecting the JSON response from
    /API/CheckAvailableSigninNames. The endpoint sets `isAvailable: false`
    when the address is taken."""
    result: Dict[str, List[str]] = {}
    liveLst = ["outlook.com", "hotmail.com"]

    print('[INFO] Outlook check uses Chromium (pyppeteer). '
          'On first run this downloads Chromium (~150 MB) which may take a while...')

    browser = None
    try:
        browser = await _launch_headless()
        page = await browser.newPage()
        await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36')
        captured: Dict[str, Any] = {}

        async def on_response(r):
            if 'CheckAvailableSigninNames' in r.url:
                try:
                    captured['body'] = await r.json()
                except Exception:
                    pass

        page.on('response', lambda r: asyncio.ensure_future(on_response(r)))

        liveSucc = []
        for maildomain in liveLst:
            email = f"{target}@{maildomain}"
            captured.clear()
            await page.goto('https://signup.live.com/', {'waitUntil': 'networkidle2', 'timeout': 30000})
            await page.waitForSelector('input[name=email]', {'timeout': 8000})
            await page.evaluate('document.querySelector("input[name=email]").value = ""')
            await page.type('input[name=email]', email, {'delay': 40})
            await page.click('button[type=submit]')
            for _ in range(20):
                await asyncio.sleep(0.5)
                if 'body' in captured:
                    break
            body = captured.get('body')
            if isinstance(body, dict) and body.get('isAvailable') is False:
                liveSucc.append(email)

        if liveSucc:
            result["Live"] = liveSucc
    except Exception as e:
        err_str = str(e)
        if _is_chromium_error(err_str):
            print(f'[WARNING] Outlook check failed: Chromium/browser issue detected '
                  f'({err_str[:200]}). Ensure pyppeteer can download Chromium.')
        else:
            print(f'[WARNING] Outlook check failed: {err_str[:200]}')
        logger.error(e, exc_info=True)
    finally:
        if browser is not None:
            await browser.close()

    return result


async def zoho(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    headers = {
        "User-Agent": "User-Agent: Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.7113.93 Safari/537.36",
        "Referer": "https://www.zoho.com/",
        "Origin": "https://www.zoho.com"
    }

    zohoURL = "https://accounts.zoho.com:443/accounts/validate/register.ac"
    zohoPOST = {"username": target, "servicename": "VirtualOffice", "serviceurl": "/"}
    sreq = req_session_fun()

    try:
        zohoChk = await sreq.post(zohoURL, headers=headers, data=zohoPOST, timeout=kwargs.get('timeout', 10))

        async with zohoChk:
            if zohoChk.status == 200:
                # if "IAM.ERROR.USERNAME.NOT.AVAILABLE" in zohoChk.text:
                #    print("[+] Success with {}@zohomail.com".format(target))
                resp = await zohoChk.json()
                username_err = resp.get('error', {}).get('username', '')
                if username_err == 'This username is taken' or 'already registered' in username_err:
                    result["Zoho"] = f"{target}@zohomail.com"
                                    # print("[+] Success with {}@zohomail.com".format(target))
    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result


async def lycos(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    lycosURL = f"https://registration.lycos.com/usernameassistant.php?validate=1&m_AID=0&t=1625674151843&m_U={target}&m_PR=27&m_SESSIONKEY=4kCL5VaODOZ5M5lBF2lgVONl7tveoX8RKmedGRU3XjV3xRX5MqCP2NWHKynX4YL4"


    headers = {
        "User-Agent": "User-Agent: Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.7113.93 Safari/537.36",
        "Referer": "https://registration.lycos.com/register.php?m_PR=27&m_E=7za1N6E_h_nNSmIgtfuaBdmGpbS66MYX7lMDD-k9qlZCyq53gFjU_N12yVxL01F0R_mmNdhfpwSN6Kq6bNfiqQAA",
        "X-Requested-With": "XMLHttpRequest"}
    sreq = req_session_fun()

    try:
        lycosChk = await sreq.get(lycosURL, headers=headers, timeout=kwargs.get('timeout', 10))

        async with lycosChk:
            if lycosChk.status == 200:
                resp = await lycosChk.text()
                if resp == "Unavailable":
                    result["Lycos"] = f"{target}@lycos.com"
    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result


async def eclipso(target, req_session_fun, *args, **kwargs) -> Dict:  # high ban risk + false positives after
    result = {}

    eclipsoSucc = []

    eclipsoLst = ["eclipso.eu",
                  "eclipso.de",
                  "eclipso.at",
                  "eclipso.ch",
                  "eclipso.be",
                  "eclipso.es",
                  "eclipso.it",
                  "eclipso.me",
                  "eclipso.nl",
                  "eclipso.email"]

    headers = {'User-Agent': random.choice(uaLst),
               'Referer': 'https://www.eclipso.eu/signup/tariff-5',
               'X-Requested-With': 'XMLHttpRequest'}
    sreq = req_session_fun()
    timeout = kwargs.get('timeout', 5)

    async def check_one(maildomain):
        targetMail = f"{target}@{maildomain}"
        eclipsoURL = f"https://www.eclipso.eu/index.php?action=checkAddressAvailability&address={targetMail}"
        try:
            chkEclipso = await sreq.get(eclipsoURL, headers=headers, timeout=timeout)
            async with chkEclipso:
                if chkEclipso.status == 200:
                    resp = await chkEclipso.text()
                    if '>0<' in resp:
                        return targetMail
        except Exception as e:
            logger.error(e, exc_info=True)
        return None

    checked = await asyncio.gather(*(check_one(d) for d in eclipsoLst))
    eclipsoSucc = [m for m in checked if m]

    if eclipsoSucc:
        result["Eclipso"] = eclipsoSucc

    await sreq.close()

    return result


async def posteo(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.109 Safari/537.36',
        'Referer': 'https://posteo.de/en/signup',
        'X-Requested-With': 'XMLHttpRequest'}

    sreq = req_session_fun()
    try:
        posteoURL = f"https://posteo.de/users/new/check_username?user%5Busername%5D={target}"

        chkPosteo = await sreq.get(posteoURL, headers=headers, timeout=kwargs.get('timeout', 5))

        async with chkPosteo:
            if chkPosteo.status == 200:
                resp = await chkPosteo.text()
                if resp == "false":
                    result["Posteo"] = [
                        f"{target}@posteo.net",
                        "~50 aliases: https://posteo.de/en/help/which-domains-are-available-to-use-as-a-posteo-alias-address",
                    ]

    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result


# DEPRECATED — not in CHECKERS.
# Why: /ajax 301-redirects to pricing. The actual username-check endpoint
# `/registration/stepThree/accountExists` can only be reached by completing
# step 1 (real recovery email + password) and step 2 (plan + payment-method).
# Step 1 has no XHR availability check, so even via headless we can't reach
# step 3 without submitting a complete signup with a working recovery email.
# How to revive: automate filling steps 1+2 through a throwaway recovery
# inbox (e.g. a temporary mailbox), then capture the step 3 XHR.
async def mailbox(target, req_session_fun, *args, **kwargs) -> Dict:  # tor RU
    print('[DEPRECATED] mailbox is unmaintained — multi-step form blocks the username check. See comment in mailcat.py.')
    result = {}

    mailboxURL = "https://register.mailbox.org:443/ajax"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.109 Safari/537.36"}
    mailboxJSON = {"account_name": target, "action": "validateAccountName"}

    existiert = "Der Accountname existiert bereits."
    sreq = req_session_fun()

    try:
        chkMailbox = await sreq.post(mailboxURL, headers=headers, json=mailboxJSON, timeout=kwargs.get('timeout', 10))

        async with chkMailbox:
            resp = await chkMailbox.text()
            if resp == existiert:
                result["MailBox"] = f"{target}@mailbox.org"
    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result


async def firemail(target, req_session_fun, *args, **kwargs) -> Dict:  # tor RU
    result = {}

    firemailSucc = []

    firemailDomains = ["firemail.at", "firemail.de", "firemail.eu"]

    headers = {'User-Agent': random.choice(uaLst),
               'Referer': 'https://firemail.de/E-Mail-Adresse-anmelden',
               'X-Requested-With': 'XMLHttpRequest'}
    sreq = req_session_fun()

    for firemailDomain in firemailDomains:
        try:
            targetMail = f"{target}@{firemailDomain}"

            firemailURL = f"https://firemail.de/index.php?action=checkAddressAvailability&address={targetMail}"

            chkFiremail = await sreq.get(firemailURL, headers=headers, timeout=kwargs.get('timeout', 10))

            async with chkFiremail:
                if chkFiremail.status == 200:
                    resp = await chkFiremail.text()
                    if '>0<' in resp:
                        firemailSucc.append(f"{targetMail}")
        except Exception as e:
            logger.error(e, exc_info=True)

        await asyncio.sleep(random.uniform(2, 4))

    if firemailSucc:
        result["Firemail"] = firemailSucc

    await sreq.close()

    return result


async def fastmail(target, req_session_fun, *args, **kwargs) -> Dict:
    """Drive www.fastmail.com/signup/ in headless Chromium, type the username
    into the signup form, and capture the JMAP `/signup/api` response. The
    request body includes a JS-generated `talon` anti-bot token which is why
    the old direct-curl path now returns JMAP capabilities instead of a
    real response. Only checks fastmail.com (the primary domain) — the
    legacy alias-domain list (sent.com, fastmail.fm, etc.) shares the same
    JMAP backend, but iterating each one through the form is too slow."""
    target = target.lower()
    if not re.search(r'^[a-zA-Z]\w{2,40}$', target, re.ASCII):
        return {}

    result: Dict[str, Any] = {}

    print('[INFO] Fastmail check uses Chromium (pyppeteer). '
          'On first run this downloads Chromium (~150 MB) which may take a while...')

    browser = None
    try:
        browser = await _launch_headless()
        page = await browser.newPage()
        await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36')

        captured: Dict[str, Any] = {}

        async def on_response(r):
            if 'signup/api' in r.url and r.request.method == 'POST':
                try:
                    body = await r.json()
                    method_responses = body.get('methodResponses', [])
                    for mr in method_responses:
                        if mr and mr[0] == 'Signup/getEmailAvailability':
                            captured['response'] = mr[1]
                            break
                except Exception:
                    pass

        page.on('response', lambda r: asyncio.ensure_future(on_response(r)))

        await page.goto('https://www.fastmail.com/signup/', {'waitUntil': 'networkidle2', 'timeout': 30000})
        await asyncio.sleep(2)
        # The username input has no `name` attribute — pick it as the only visible
        # text input without one.
        typed = await page.evaluate('''(val) => {
            const inps = Array.from(document.querySelectorAll("input[type=text]"))
                .filter(el => !el.name && el.offsetParent !== null);
            if (!inps.length) return false;
            const inp = inps[0];
            inp.focus();
            inp.value = val;
            inp.dispatchEvent(new Event("input", {bubbles: true}));
            inp.dispatchEvent(new Event("change", {bubbles: true}));
            inp.blur();
            return true;
        }''', target)
        if not typed:
            return result

        for _ in range(20):
            await asyncio.sleep(0.5)
            if 'response' in captured:
                break

        body = captured.get('response')
        if isinstance(body, dict) and body.get('isAvailable') is False:
            email = body.get('email') or f'{target}@fastmail.com'
            result["Fastmail"] = email
    except Exception as e:
        err_str = str(e)
        if _is_chromium_error(err_str):
            print(f'[WARNING] Fastmail check failed: Chromium/browser issue ({err_str[:200]}).')
        else:
            print(f'[WARNING] Fastmail check failed: {err_str[:200]}')
        logger.error(e, exc_info=True)
    finally:
        if browser is not None:
            await browser.close()

    return result


async def startmail(target, req_session_fun, *args, **kwargs) -> Dict:  # TOR
    result = {}

    startmailURL = f"https://mail.startmail.com:443/api/AvailableAddresses/{target}%40startmail.com"

    headers = {"User-Agent": random.choice(uaLst),
               "X-Requested-With": "1.94.0"}
    sreq = req_session_fun()

    try:
        chkStartmail = await sreq.get(startmailURL, headers=headers, timeout=kwargs.get('timeout', 10))

        async with chkStartmail:
            if chkStartmail.status == 404:
                result["StartMail"] = f"{target}@startmail.com"

    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result


async def kolab(target, req_session_fun, *args, **kwargs) -> Dict:
    result: Dict[str, List] = {}

    kolabLst = ["mykolab.com",
                "attorneymail.ch",
                "barmail.ch",
                "collaborative.li",
                "diplomail.ch",
                "freedommail.ch",
                "groupoffice.ch",
                "journalistmail.ch",
                "legalprivilege.ch",
                "libertymail.co",
                "libertymail.net",
                "mailatlaw.ch",
                "medicmail.ch",
                "medmail.ch",
                "mykolab.ch",
                "myswissmail.ch",
                "opengroupware.ch",
                "pressmail.ch",
                "swisscollab.ch",
                "swissgroupware.ch",
                "switzerlandmail.ch",
                "trusted-legal-mail.ch",
                "kolabnow.com",
                "kolabnow.ch"]

    ''' # old cool version ;(
    kolabURL = "https://kolabnow.com:443/cockpit/json.php"
    headers = { "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0",
                "Referer": "https://kolabnow.com/cockpit/signup/individual",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest"}

    try:
        kolabStatus = sreq.post(kolabURL, headers=headers)
        print(kolabStatus.status_code)

        if kolabStatus.status_code == 200:

            for kolabdomain in kolabLst:

                kolabPOST = {"validate": "username",
                            "accounttype": "individual",
                            "username": target,
                            "domain": kolabdomain,
                            "_action_": "/signup/validate"}

                try:

                    chkKolab = sreq.post(kolabURL, headers=headers, data=kolabPOST)

                    if chkKolab.status_code == 200:

                        kolabJSON = chkKolab.json()

                        if kolabJSON['errors']:
                            suc = "This email address is not available"
                            if kolabJSON['errors']['username'] == suc:
                                print("[+] Success with {}@{}".format(target, kolabdomain))

                except Exception as e:
                    pass

                sleep(random.uniform(1, 3))

    except Exception as e:
        #pass
        print e
    '''

    kolabURL = "https://kolabnow.com/api/auth/signup"
    headers = {"User-Agent": random.choice(uaLst),
               "Referer": "https://kolabnow.com/signup/individual",
               "Content-Type": "application/json;charset=utf-8",
               "X-Test-Payment-Provider": "mollie",
               "X-Requested-With": "XMLHttpRequest"}
    sreq = req_session_fun()
    timeout = kwargs.get('timeout', 10)

    kolabStatus = await sreq.post(kolabURL, headers={"User-Agent": random.choice(uaLst)}, timeout=timeout)

    if kolabStatus.status == 422:

        kolabpass = randstr(12)
        kolabsuc = "The specified login is not available."

        for kolabdomain in kolabLst:

            kolabPOST = {"login": target,
                         "domain": kolabdomain,
                         "password": kolabpass,
                         "password_confirmation": kolabpass,
                         "voucher": "",
                         "code": "bJDmpWw8sO85KlgSETPWtnViDgQ1S0MO",
                         "short_code": "VHBZX"}

            try:
                # chkKolab = sreq.post(kolabURL, headers=headers, data=kolabPOST)
                chkKolab = await sreq.post(kolabURL, headers=headers, data=json.dumps(kolabPOST), timeout=timeout)
                await chkKolab.text()

                if chkKolab.status == 200:

                    kolabJSON = chkKolab.json()
                    if (
                        kolabJSON["errors"]["login"] != kolabsuc
                        and kolabJSON["errors"]
                    ):
                        print(kolabJSON["errors"])

            except Exception as e:
                logger.error(e, exc_info=True)

    await sreq.close()

    return result


async def bigmir(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    bigmirSucc = []
    bigmirMail = ["i.ua", "ua.fm", "email.ua"]
    sreq = req_session_fun()

    for maildomain in bigmirMail:
        try:
            bigmirChkJS = "https://passport.i.ua/js/free.js?15908746259240-xml"

            headers = {
                'Pragma': 'no-cache',
                'Origin': 'https://passport.i.ua',
                'User-Agent': random.choice(uaLst),
                'Content-Type': 'application/octet-stream',
                'Referer': 'https://passport.i.ua/registration/'
            }

            bm_data = f"login={target}@{maildomain}"

            bigmirChk = await sreq.post(bigmirChkJS, headers=headers, data=bm_data, timeout=kwargs.get('timeout', 10))

            async with bigmirChk:
                if bigmirChk.status == 200:
                    resp = await bigmirChk.text()
                    if "'free': false" in resp:
                        bigmirSucc.append(f"{target}@{maildomain}")

            await asyncio.sleep(random.uniform(2, 4))

        except Exception as e:
            logger.error(e, exc_info=True)

    if bigmirSucc:
        result["Bigmir"] = bigmirSucc

    await sreq.close()

    return result



# DEPRECATED — not in CHECKERS.
# Why: /app/signup/checkusername now sits behind HTTP Basic auth
# ("Restricted Access for Signup") and returns 401 to unauthenticated
# callers.
# How to revive: discover the Basic-auth credentials (likely embedded
# somewhere in the live signup JS bundle) and pass them as the auth tuple.
async def xmail(target, req_session_fun, *args, **kwargs) -> Dict:
    print('[DEPRECATED] xmail is unmaintained — endpoint now requires HTTP Basic auth. See comment in mailcat.py.')
    result = {}

    sreq = req_session_fun()
    xmailURL = "https://xmail.net:443/app/signup/checkusername"
    headers = {"User-Agent": random.choice(uaLst),
               "Accept": "application/json, text/javascript, */*",
               "Referer": "https://xmail.net/app/signup",
               "Content-Type": "application/x-www-form-urlencoded",
               "X-Requested-With": "XMLHttpRequest",
               "Connection": "close"}

    xmailPOST = {"username": target, "firstname": '', "lastname": ''}

    try:
        xmailChk = await sreq.post(xmailURL, headers=headers, data=xmailPOST, timeout=kwargs.get('timeout', 10))

        async with xmailChk:
            resp = await xmailChk.json()
            if not resp['username']:
                result["Xmail"] = f"{target}@xmail.net"

    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result


async def ukrnet(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    ukrnet_reg_urk = "https://accounts.ukr.net:443/registration"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.103 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "close",
        "Upgrade-Insecure-Requests": "1"}

    sreq = req_session_fun()
    timeout = kwargs.get('timeout', 10)

    try:

        get_reg_ukrnet = await sreq.get(ukrnet_reg_urk, headers=headers, timeout=timeout)

        async with get_reg_ukrnet:
            if get_reg_ukrnet.status == 200:
                if sreq.cookie_jar:
                    ukrnetURL = "https://accounts.ukr.net:443/api/v1/registration/reserve_login"
                    ukrnetPOST = {"login": target}

                    ukrnetChk = await sreq.post(ukrnetURL, headers=headers, json=ukrnetPOST, timeout=timeout)

                    async with ukrnetChk:
                        if ukrnetChk.status == 200:
                            resp = await ukrnetChk.json()
                            if not resp['available']:
                                result["UkrNet"] = f"{target}@ukr.net"
    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result


async def runbox(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    runboxSucc = []
    runboxLst = ["mailhost.work",
                 "mailhouse.biz",
                 "messagebox.email",
                 "offshore.rocks",
                 "rbox.co",
                 "rbox.me",
                 "rbx.email",
                 "rbx.life",
                 "rbx.run",
                 "rnbx.uk",
                 "runbox.at",
                 "runbox.biz",
                 "runbox.bz",
                 "runbox.ch",
                 "runbox.co",
                 "runbox.co.in",
                 "runbox.com",
                 "runbox.dk",
                 "runbox.email",
                 "runbox.eu",
                 "runbox.is",
                 "runbox.it",
                 "runbox.ky",
                 "runbox.li",
                 "runbox.me",
                 "runbox.nl",
                 "runbox.no",
                 "runbox.uk",
                 "runbox.us",
                 "xobnur.uk"]

    headers = {"User-Agent": random.choice(uaLst),
               "Origin": "https://runbox.com",
               "Referer": "https://runbox.com/signup?runbox7=1"}

    sreq = req_session_fun()
    timeout = kwargs.get('timeout', 5)

    async def check_one(rboxdomain):
        data = {"type": "person", "company": "", "first_name": "", "last_name": "", "user": target,
                "userdomain": "domainyouown.com", "runboxDomain": rboxdomain, "password": "",
                "password_strength": "", "email_alternative": "", "phone_number_cellular": "",
                "referrer": "", "phone_number_home": "", "g-recaptcha-response": "",
                "h-captcha-response": "", "signup": "%A0Set+up+my+Runbox+account%A0",
                "av": "y", "as": "y", "domain": "", "accountType": "person", "domainType": "runbox",
                "account_number": "", "timezone": "undefined", "runbox7": "1"}
        try:
            chkRunbox = await sreq.post('https://runbox.com/signup/signup', headers=headers, data=data, timeout=timeout)
            if chkRunbox.status == 200:
                resp = await chkRunbox.text()
                if "The specified username is already taken" in resp:
                    return f"{target}@{rboxdomain}"
        except Exception as e:
            logger.error(e, exc_info=True)
        return None

    checked = await asyncio.gather(*(check_one(d) for d in runboxLst))
    runboxSucc = [m for m in checked if m]

    if runboxSucc:
        result["Runbox"] = runboxSucc

    await sreq.close()

    return result


# DEPRECATED — not in CHECKERS.
# Why: Apple's old endpoint /password/verify/appleid now returns HTTP 403
# unconditionally and the surrounding /getstarted flow was redesigned.
# How to revive: reverse-engineer the new iforgot widget (it involves
# anti-bot tokens issued by Apple's CDN) — likely needs headless Chromium
# to harvest those tokens.
async def iCloud(target, req_session_fun, *args, **kwargs) -> Dict:
    print('[DEPRECATED] iCloud is unmaintained — Apple endpoint changed and now returns 403. See comment in mailcat.py.')
    result: Dict[str, List] = {}

    domains = [
        'icloud.com',
        'me.com',
        'mac.com',
    ]

    sreq = req_session_fun()
    timeout= kwargs.get('timeout', 5)

    for domain in domains:
        try:
            email = f'{target}@{domain}'
            headers = {
                'User-Agent': random.choice(uaLst),
                'sstt': 'zYEaY3WeI76oAG%2BCNPhCiGcKUCU0SIQ1cIO2EMepSo8egjarh4MvVPqxGOO20TYqlbJI%2Fqs57WwAoJarOPukJGJvgOF7I7C%2B1jAE5vZo%2FSmYkvi2e%2Bfxj1od1xJOf3lnUXZlrnL0QWpLfaOgOwjvorSMJ1iuUphB8bDqjRzyb76jzDU4hrm6TzkvxJdlPCCY3JVTfAZFgXRoW9VlD%2Bv3VF3in1RSf6Er2sOS12%2FZJR%2Buo9ubA2KH9RLRzPlr1ABtsRgw6r4zbFbORaKTSVWGDQPdYCaMsM4ebevyKj3aIxXa%2FOpS6SHcx1KrvtOAUVhR9nsfZsaYfZvDa6gzpcNBF9domZJ1p8MmThEfJra6LEuc9ssZ3aWn9uKqvT3pZIVIbgdZARL%2B6SK1YCN7',
                'Content-Type': 'application/json',
            }

            data = {'id': email}
            check = await sreq.post('https://iforgot.apple.com/password/verify/appleid',
                                    headers=headers, data=json.dumps(data),
                                    allow_redirects=False,
                                    timeout=timeout
                                    )
            if check.headers and check.headers.get('Location', '').startswith('/password/authenticationmethod'):
                if not result:
                    result = {'iCloud': []}
                result['iCloud'].append(email)
        except Exception as e:
            logger.error(e, exc_info=True)

    await sreq.close()

    return result


async def duckgo(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    duckURL = "https://quack.duckduckgo.com/api/auth/signup"

    headers = {"User-Agent": random.choice(uaLst), "Origin": "https://duckduckgo.com", "Sec-Fetch-Dest": "empty",
               "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-site", "Te": "trailers", "Referer": "https://duckduckgo.com/"}

    data = {
        "code": (None, "01337"),
        "user": (None, target),
        "email": (None, "mail@example.com")

    }

    sreq = req_session_fun()

    try:
        checkDuck = await sreq.post(duckURL, headers=headers, data=data, timeout=kwargs.get('timeout', 5))

        resp = await checkDuck.text()
        # if checkDuck.json()['error'] == "unavailable_username":
        if "unavailable_username" in resp:
            result["DuckGo"] = f"{target}@duck.com"

    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result


# DEPRECATED — not in CHECKERS.
# Why: the signup endpoint returns HTTP 500 "Unknown error" because the
# hardcoded `form_token` is no longer accepted; Hushmail rotates the token
# per page-load and the request also requires a fresh
# `X-Hush-Ajax-Start-Time` paired with that token.
# How to revive: GET /signup/ first, scrape `form_token` from the HTML,
# pair it with a fresh timestamp, then POST.
async def hushmail(target, req_session_fun, *args, **kwargs) -> Dict:

    print('[DEPRECATED] hushmail is unmaintained — fixed form_token rejected with HTTP 500. See comment in mailcat.py.')
    result = {}

    hushDomains = ["hushmail.com", "hush.com", "therapyemail.com", "counselingmail.com", "therapysecure.com", "counselingsecure.com"]
    hushSucc = []
    sreq = req_session_fun()

    hush_ts = int(datetime.datetime.now().timestamp())

    hushURL = "https://secure.hushmail.com/signup/create?format=json"
    ref_header = "https://secure.hushmail.com/signup/?package=hushmail-for-healthcare-individual-5-form-monthly&source=website&tag=page_business_healthcare,btn_healthcare_popup_signup_individual&coupon_code="
    hush_UA = random.choice(uaLst)

    hushpass = randstr(15)

    for hushdomain in hushDomains:

        # hushpass = randstr(15)
        hush_ts = int(datetime.datetime.now().timestamp())

        headers = {"User-Agent": hush_UA,
                   "Accept": "application/json, text/javascript, */*; q=0.01",
                   "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                   "X-Hush-Ajax-Start-Time": str(hush_ts), "X-Requested-With": "XMLHttpRequest",
                   "Origin": "https://secure.hushmail.com", "Referer": ref_header,
                   "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin"}

        data = {"hush_customerid": '', "hush_exitmethod": "GET",
                "skin": "bootstrap311", "hush_cc_country": '',
                "trial_mode": '', "parent": '', "parent_code": '',
                "coupon_code": '', "form_token": "6e1555a603f6e762a090e6f6b885122f_dabaddeadbee",
                "__hushform_extra_fields": '', "hush_username": target, "hush_domain": hushdomain,
                "hush_pass1": hushpass, "hush_pass2": hushpass,
                "hush_exitpage": "https://secure.hushmail.com/pay?package=hushmail-for-healthcare-individual-5-form-monthly",
                "package": "hushmail-for-healthcare-individual-5-form-monthly",
                "hush_reservation_code": '', "hush_tos": '', "hush_privacy_policy": '',
                "hush_additional_tos": '', "hush_email_opt_in": '', "isValidAjax": "newaccountform"}

        try:
            hushCheck = await sreq.post(hushURL, headers=headers, data=data, timeout=kwargs.get('timeout', 5))

            if hushCheck.status == 200:
                resp = await hushCheck.json()
                if (
                    f"'{target}' is not available"
                    in resp['formValidation']['hush_username']
                ):
                    hushMail = f"{target}@{hushdomain}"
                    hushSucc.append(hushMail)

        except Exception as e:
            logger.error(e, exc_info=True)

        await sleeper(hushDomains, 1.1, 2.2)

    if hushSucc:
        result["HushMail"] = hushSucc

    await sreq.close()

    return result


async def emailn(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    emailnURL = f"https://www.emailn.de/webmail/index.php?action=checkAddressAvailability&address={target}@emailn.de"

    headers = {'User-Agent': random.choice(uaLst)}
    sreq = req_session_fun()

    try:
        emailnChk = await sreq.get(emailnURL, headers=headers, timeout=10)

        async with emailnChk:
            if emailnChk.status == 200:
                resp = await emailnChk.text()
                if ">0<" in resp:
                    result["emailn"] = f"{target}@emailn.de"
    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result


async def aikq(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}
    aikqSucc = []

    aikqLst = ["aikq.com",
               "aikq.co",
               "aikq.eu",
               "aikq.de",
               "mails.eu",
               "aikq.net",
               "aikq.org",
               "aikq.biz",
               "aikq.tv",
               "aikq.at",
               "aikq.uk",
               "aikq.co.uk",
               "aikq.fr",
               "aikq.be",
               "aikq.pl",
               "aikq.email",
               "aikq.info",
               "mailbox.info",
               "mails.info",
               "aikq.cloud",
               "aikq.chat",
               "aikq.name",
               "aikq.wiki",
               "aikq.ae",
               "aikq.asia",
               "aikq.by",
               "aikq.com.br",
               "aikq.cz",
               "aikq.ie",
               "aikq.in",
               "aikq.jp",
               "aikq.li",
               "aikq.me",
               "aikq.mx",
               "aikq.nl",
               "aikq.nz",
               "aikq.qa",
               "aikq.sk",
               "aikq.tw",
               "aikq.us",
               "aikq.ws"]


    headers = {'User-Agent': random.choice(uaLst)}
    sreq = req_session_fun()
    timeout = kwargs.get('timeout', 5)

    async def check_one(maildomain):
        targetMail = f"{target}@{maildomain}"
        aikqUrl = f"https://www.aikq.de/index.php?action=checkAddressAvailability&address={targetMail}"
        try:
            chkAikq = await sreq.get(aikqUrl, headers=headers, timeout=timeout)
            async with chkAikq:
                if chkAikq.status == 200:
                    resp = await chkAikq.text()
                    if '>0<' in resp:
                        return targetMail
        except Exception as e:
            logger.error(e, exc_info=True)
        return None

    checked = await asyncio.gather(*(check_one(d) for d in aikqLst))
    aikqSucc = [m for m in checked if m]

    if aikqSucc:
        result["Aikq"] = aikqSucc

    await sreq.close()

    return result


async def vivaldi(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}

    vivaldiURL = "https://login.vivaldi.net:443/profile/validateField"
    headers = {
        "User-Agent": random.choice(uaLst),
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://login.vivaldi.net",
        "Referer": "https://login.vivaldi.net/profile/id/signup"
    }

    vivaldiPOST = {"field": "username", "value": target}

    sreq = req_session_fun()

    try:
        vivaldiChk = await sreq.post(vivaldiURL, headers=headers, data=vivaldiPOST, timeout=kwargs.get('timeout', 5))

        body = await vivaldiChk.json(content_type=None)

        if 'error' in body and body['error'] == "User exists [1007]":
            result["Vivaldi"] = f"{target}@vivaldi.net"

    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result

async def mailDe(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}
    mailChkLst, error = await code250("mail.de", target, kwargs.get('timeout', 10))
    if mailChkLst:
        result["mail.de"] = mailChkLst[0]
    await asyncio.sleep(0)
    return result, error

# DEPRECATED — not in CHECKERS.
# Why: WP signup migrated to a Next.js SPA at 1login.wp.pl that loads
# Cloudflare Turnstile and reCAPTCHA before exposing the username field.
# Submission requires a `tokenMultiUse` from the captcha. Headless Chromium
# hits the Turnstile wall too.
# How to revive: integrate a captcha-solver service (Turnstile + reCAPTCHA)
# to mint `tokenMultiUse`, drive the SPA through headless and post.
async def wp(target, req_session_fun, *args, **kwargs) -> Dict:
    print('[DEPRECATED] wp is unmaintained — Cloudflare Turnstile + reCAPTCHA wall. See comment in mailcat.py.')
    result = {}

    wpURL = "https://poczta.wp.pl/api/v1/public/registration/accounts/availability"
    headers = {
        "User-Agent": random.choice(uaLst),
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://poczta.wp.pl",
        "Referer": "https://poczta.wp.pl/rejestracja/",
        "Accept": "application/json"
    }

    data = f'{{"login":"{target}"}}'

    sreq = req_session_fun()

    try:
        wpChk = await sreq.put(wpURL, headers=headers, data=data, timeout=kwargs.get('timeout', 5))

        body = await wpChk.json(content_type=None)

        if "Podany login jest niedostępny." in str(body):
            result["Wirtualna Polska"] = f"{target}@wp.pl"

    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result

# DEPRECATED — not in CHECKERS.
# Why: konto.gazeta.pl/konto/checkLogin returns 404 — the live signup form
# (rejestracja.do) no longer exposes a JSON availability endpoint and
# protects the final submit with hCaptcha + reCAPTCHA. Even via headless,
# no XHR fires until the captcha is solved.
# How to revive: integrate a captcha-solver to clear hCaptcha + reCAPTCHA,
# then full-submit the form and inspect the response page for the
# "login already taken" inline error.
async def gazeta(target, req_session_fun, *args, **kwargs) -> Dict:
    print('[DEPRECATED] gazeta is unmaintained — no public API + captcha wall. See comment in mailcat.py.')
    result = {}

    gazetaURL = f"https://konto.gazeta.pl/konto/checkLogin?login={target}&nosuggestions=true"
    headers = {
        "User-Agent": random.choice(uaLst),
        "Referer": "https://konto.gazeta.pl/konto/rejestracja.do",
        "Accept": "*/*"
    }

    sreq = req_session_fun()

    try:
        gazetaChk = await sreq.get(gazetaURL, headers=headers, timeout=kwargs.get('timeout', 5))

        body = await gazetaChk.json(content_type=None)

        if body["available"] == "0":
            result["Gazeta.pl"] = f"{target}@gazeta.pl"

    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result

async def intpl(target, req_session_fun, *args, **kwargs) -> Dict:
    """Drive the int.pl registration form (#/register) in headless Chromium —
    the /v1/user/checkEmail endpoint blocks unauthenticated direct calls with
    HTTP 429, but inside a real browser session it accepts the blur-triggered
    XHR. Response shape: {"result":{"data":{"login":0}}} when the login is
    taken, login==1 when free."""
    result: Dict[str, Any] = {}

    print('[INFO] int.pl check uses Chromium (pyppeteer). '
          'On first run this downloads Chromium (~150 MB) which may take a while...')

    browser = None
    try:
        browser = await _launch_headless()
        page = await browser.newPage()
        await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36')
        captured: Dict[str, Any] = {}

        async def on_response(r):
            if 'checkEmail' in r.url:
                try:
                    captured['body'] = await r.json()
                except Exception:
                    pass

        page.on('response', lambda r: asyncio.ensure_future(on_response(r)))

        await page.goto('https://int.pl/#/register', {'waitUntil': 'networkidle2', 'timeout': 30000})
        await page.waitForSelector('input[name=login]', {'timeout': 8000})
        await page.evaluate('document.querySelector("input[name=login]").value = ""')
        await page.evaluate('document.querySelector("input[name=login]").focus()')
        await page.type('input[name=login]', target, {'delay': 60})
        await page.evaluate('document.querySelector("input[name=login]").blur()')
        for _ in range(16):
            await asyncio.sleep(0.5)
            if 'body' in captured:
                break

        body = captured.get('body')
        if isinstance(body, dict):
            login_status = body.get('result', {}).get('data', {}).get('login')
            if login_status == 0:
                result["int.pl"] = f"{target}@int.pl"
    except Exception as e:
        err_str = str(e)
        if _is_chromium_error(err_str):
            print(f'[WARNING] int.pl check failed: Chromium/browser issue detected ({err_str[:200]}).')
        else:
            print(f'[WARNING] int.pl check failed: {err_str[:200]}')
        logger.error(e, exc_info=True)
    finally:
        if browser is not None:
            await browser.close()

    return result

# DEPRECATED — not in CHECKERS.
# Why: o2.pl signup is hosted on the same WP-managed 1login.wp.pl SPA and
# therefore inherits the same Cloudflare Turnstile + reCAPTCHA wall. See
# `wp()` above.
# How to revive: same path as wp().
async def o2(target, req_session_fun, *args, **kwargs) -> Dict:
    print('[DEPRECATED] o2 is unmaintained — Cloudflare Turnstile + reCAPTCHA wall. See comment in mailcat.py.')
    result = {}

    o2URL = "https://poczta.o2.pl/api/v1/public/registration/accounts/availability"
    headers = {
        "User-Agent": random.choice(uaLst),
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://poczta.o2.pl",
        "Referer": "https://poczta.o2.pl/rejestracja/",
        "Accept": "application/json"
    }

    data = f'{{"login":"{target}","sex":""}}'

    sreq = req_session_fun()

    try:
        wpChk = await sreq.put(o2URL, headers=headers, data=data, timeout=kwargs.get('timeout', 5))

        body = await wpChk.json(content_type=None)

        if "Podany login jest niedostępny." in str(body):
            result["O2"] = f"{target}@o2.pl"

    except Exception as e:
        logger.error(e, exc_info=True)

    await sreq.close()

    return result

async def interia(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}
    interiaSucc = []

    interiaLst = ["interia.pl",
               "interia.eu",
               "intmail.pl",
               "adresik.net",
               "vip.interia.pl",
               "ogarnij.se",
               "poczta.fm",
               "interia.com",
               "interiowy.pl",
               "pisz.to",
               "pacz.to"]


    headers = {
        'User-Agent': random.choice(uaLst),
        'Content-Type': 'application/json',
        'Accept': 'application/json; q=1.0, text/*; q=0.8, */*; q=0.1',
        'Origin': 'https://konto-pocztowe.interia.pl',
        'Referer': 'https://konto-pocztowe.interia.pl/'
    }

    sreq = req_session_fun()
    timeout = kwargs.get('timeout', 5)
    interiaUrl = "https://konto-pocztowe.interia.pl/odzyskiwanie-dostepu/sms"

    async def check_one(maildomain):
        targetMail = f"{target}@{maildomain}"
        data = f'{{"email":"{targetMail}"}}'
        try:
            chkInteria = await sreq.post(interiaUrl, headers=headers, data=data, timeout=timeout)
            async with chkInteria:
                # 200 = SMS-recovery flow accepted → user exists.
                # 404 with "Użytkownik nie istnieje w systemie" = user doesn't exist.
                # 422 = invalid email (rate-limited / domain not recognised).
                if chkInteria.status == 200:
                    resp = await chkInteria.json(content_type=None)
                    if resp.get("status") == "success":
                        return targetMail
        except Exception as e:
            logger.error(e, exc_info=True)
        return None

    checked = await asyncio.gather(*(check_one(d) for d in interiaLst))
    interiaSucc = [m for m in checked if m]

    if interiaSucc:
        result["Interia"] = interiaSucc

    await sreq.close()

    return result

async def tpl(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}
    tplSucc = []

    tplLst = ["t.pl",
               "malio.pl",
               "wg.pl",
               "2.pl",
               "jo.pl",
               "pocz.pl",
               "t7.pl",
               "0.pl",
               "uk.pl"]


    headers = {'User-Agent': random.choice(uaLst)}
    sreq = req_session_fun()
    try:
        tplUrl = f"https://t.pl/reg.php?nazwa={target}"

        chkTpl = await sreq.get(tplUrl, headers=headers, timeout=kwargs.get('timeout', 5))

        async with chkTpl:
            if chkTpl.status == 200:
                resp = await chkTpl.text()
                for maildomain in tplLst:
                    targetMail = f"{target}@{maildomain}"
                    if f"<td>{targetMail}</td><td class=zajety>" in resp:
                        tplSucc.append(targetMail)
    except Exception as e:
        logger.error(e, exc_info=True)

    if tplSucc:
        result["T.pl"] = tplSucc

    await sreq.close()

    return result

async def onet(target, req_session_fun, *args, **kwargs) -> Dict:
    """Drive konto.onet.pl/register in headless Chromium, type the alias into
    the signup form, click "DALEJ" and capture the response from
    /newapi/oauth/check-register-email-identity. The endpoint requires a
    captcha_response which the page generates from a JS challenge —
    /api/v1/oauth/captcha is invisible to direct curl callers. The response
    payload `{"emails":[...]}` is empty for usernames already taken across
    all 16 onet domains, and contains the full list of free addresses
    otherwise."""
    result: Dict[str, Any] = {}
    onetLst = ["onet.pl", "op.pl", "adres.pl", "vp.pl", "onet.eu",
               "cyberia.pl", "pseudonim.pl", "autograf.pl", "opoczta.pl",
               "spoko.pl", "amorki.pl", "buziaczek.pl", "poczta.onet.pl",
               "poczta.onet.eu", "onet.com.pl", "vip.onet.pl"]

    print('[INFO] Onet check uses Chromium (pyppeteer). '
          'On first run this downloads Chromium (~150 MB) which may take a while...')

    browser = None
    try:
        browser = await _launch_headless()
        page = await browser.newPage()
        await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36')

        captured: Dict[str, Any] = {}

        async def on_response(r):
            if 'check-register-email-identity' in r.url:
                try:
                    captured['body'] = await r.json()
                except Exception:
                    pass

        page.on('response', lambda r: asyncio.ensure_future(on_response(r)))

        await page.goto('https://konto.onet.pl/register', {'waitUntil': 'networkidle2', 'timeout': 30000})
        await asyncio.sleep(2)
        # Pick "create new mail" radio
        try:
            await page.click('#with-inbox')
        except Exception:
            pass
        await asyncio.sleep(1)
        await page.waitForSelector('#alias', {'timeout': 5000})
        await page.evaluate('document.querySelector("#alias").value = ""')
        await page.click('#alias')
        await page.type('#alias', target, {'delay': 60})
        await asyncio.sleep(0.5)
        # Click "DALEJ" / Next
        await page.evaluate('''() => {
            const btns = Array.from(document.querySelectorAll("button"));
            const target = btns.find(b => /dalej|next|kontynu/i.test(b.innerText || ""));
            if (target) target.click();
        }''')
        for _ in range(20):
            await asyncio.sleep(0.5)
            if 'body' in captured:
                break

        body = captured.get('body')
        if isinstance(body, dict):
            emails = body.get('emails', [])
            # Empty list = the alias is taken across all onet domains.
            if not emails:
                result["Onet"] = [f"{target}@{d}" for d in onetLst]
    except Exception as e:
        err_str = str(e)
        if _is_chromium_error(err_str):
            print(f'[WARNING] Onet check failed: Chromium/browser issue ({err_str[:200]}).')
        else:
            print(f'[WARNING] Onet check failed: {err_str[:200]}')
        logger.error(e, exc_info=True)
    finally:
        if browser is not None:
            await browser.close()

    return result

async def mailum(target, req_session_fun, *args, **kwargs) -> Dict:
    result = {}
    mailumSucc = []

    mailumLst = ["cyberfear.com", "mailum.com"]

    mailumURL = "https://mailum.com/api/checkEmailExist4RegistrationV3"
    headers = {
        "User-Agent": random.choice(uaLst),
        "Referer": "https://mailum.com/mailbox/",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    sreq = req_session_fun()

    for maildomain in mailumLst:
        try:
            data = f"email={target}&domain=%40{maildomain}"

            chkMailum = await sreq.post(mailumURL, headers=headers, data=data, timeout=kwargs.get('timeout', 10))

            async with chkMailum:
                if chkMailum.status == 200:
                    resp = await chkMailum.text()
                    if resp.strip().lower() == "false":
                        mailumSucc.append(f"{target}@{maildomain}")

        except Exception as e:
            logger.error(e, exc_info=True)

    if mailumSucc:
        result["Mailum"] = mailumSucc

    await sreq.close()

    return result

####################################################################################
def show_banner():
    banner = r"""

                  ,-.                    ^
                 ( (        _,---._ __  / \
                  ) )    .-'       `./ /   \
                 ( (   ,'            `/    /:
                  \ `-"             \'\   / |
                   .              ,  \ \ /  |
                   / @          ,'-`----Y   |
                  (            ;        :   :
                  |  .-.   _,-'         |  /
                  |  | (  (             | /
                  )  (  \  `.___________:/
                  `..'   `--' :mailcat:
    """
    for color, part in zip(range(75, 89), banner.split('\n')[1:]):
        print(f"\033[1;38;5;{color}m{part}\033[0m")
        sleep(0.1337)


async def print_results(checker, target, req_session_fun, is_verbose_mode, timeout):
    checker_name = checker.__name__
    if is_verbose_mode:
        print(f'Running {checker_name} checker for {target}...')

    err = None
    res = await checker(target, req_session_fun, timeout)

    if isinstance(res, tuple):
        res, err = res

    if not res:
        if is_verbose_mode:
            print(f'No results for {checker_name}')
        res = {}

    if err:
        print(f'Error while checking {checker_name}: {err}')
        return {checker_name: err}

    for provider, emails in res.items():
        print(f'\033[1;38;5;75m{provider}: \033[0m')
        if isinstance(emails, str):
            emails = [emails]
        for email in emails:
            print(f'*  {email}')

    return {checker_name: res} if res else {checker_name: None}


# Deprecated checkers (kept in source, marked with `# DEPRECATED` and a
# `[DEPRECATED]` runtime warning above each function):
#   iCloud   — Apple endpoint 403
#   hushmail — fixed form_token rejected with 500
#   xmail    — endpoint now requires HTTP Basic auth (401)
#   tuta     — needs signupToken from hCaptcha
#   mailbox  — multi-step form blocks the username check
#   wp / o2  — Cloudflare Turnstile + reCAPTCHA wall
#   gazeta   — no public API + final-submit captcha
# Each function still runs if invoked explicitly via `-p <name>`, but it
# emits a deprecation notice and almost always returns {}.
CHECKERS = [gmail, yandex, proton, mailRu,
            rambler, yahoo, outlook,
            zoho, eclipso, posteo,
            firemail, fastmail, startmail,
            ukrnet,
            runbox, duckgo,
            aikq, emailn, vivaldi,
            mailDe, intpl,
            interia, tpl, onet,
            mailum]

async def start():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Mailcat",
    )
    parser.add_argument(
        '-p',
        '--provider',
        action="append",
        metavar='<mail providers name>',
        dest="providers",
        default=[],
        help="Specify one or more (-p for each) mail providers by name: " +
             ', '.join(map(lambda f: f.__name__, CHECKERS)),
    )
    parser.add_argument(
        "username",
        nargs='*',
        metavar="USERNAME",
        help="One or more usernames to search emails by",
    )
    parser.add_argument(
        '-f',
        '--file',
        type=str,
        default="",
        metavar='<path>',
        help="Path to a file containing usernames to check, one per line",
    )
    parser.add_argument(
        '-l',
        '--list',
        action="store_true",
        default=False,
        help="List all the supported providers",
    )
    parser.add_argument(
        '-s',
        '--silent',
        action="store_true",
        default=False,
        help="Hide wonderful mailcat intro animation",
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action="store_true",
        default=False,
        help="Verbose output about search progress.",
    )
    parser.add_argument(
        '-d',
        '--debug',
        action="store_true",
        default=False,
        help="Display checking errors.",
    )
    parser.add_argument(
        '--tor',
        action="store_true",
        default=False,
        help="Use Tor where you need it",
    )
    parser.add_argument(
        '--proxy',
        type=str,
        default="",
        help="Proxy string (e.g. https://user:pass@1.2.3.4:8080)",
    )
    parser.add_argument(
        '-t',
        '--timeout',
        type=int,
        default=10,
        help="Timeout for every check, 10 seconds by default",
    )
    parser.add_argument(
        '-m',
        '--max-connections',
        type=int,
        default=10,
        help="Max connections to check (number of simultaneously checked providers), 10 by default",
    )
    parser.add_argument(
        '--progressbar',
        action="store_true",
        default=False,
        help="Show progressbar",
    )
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.WARNING)

    if not args.silent:
        show_banner()

    if args.list:
        print('Supported email providers: ')
        print('  ' + ', '.join(map(lambda f: f.__name__, CHECKERS)))

    targets = list(args.username)

    if not targets and not args.file and args.list:
        return

    if args.file:
        try:
            with open(args.file) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        targets.append(line)
        except OSError as e:
            print(f'Cannot read file {args.file}: {e}')
            sys.exit(1)

    if not targets:
        print('Please, specify one or more usernames to search!')
        sys.exit(1)

    targets = [t.split('@')[0] if '@' in t else t for t in targets]

    if args.providers:
        pset = set(map(lambda s: s.lower(), args.providers))
        checkers = [c for c in CHECKERS if c.__name__.lower() in pset]
        if not checkers:
            print(f'Can not find providers {", ".join(args.providers)}')
    else:
        checkers = CHECKERS

    if args.proxy:
        req_session_fun = via_proxy(args.proxy)
        print(f'Using proxy {args.proxy} to make requests...')
    elif args.tor:
        req_session_fun = via_tor
        print('Using tor to make requests...')
    else:
        req_session_fun = simple_session

    bulk_mode = len(targets) > 1
    for target in targets:
        if bulk_mode:
            print(f'\n[*] Checking username: {target}')

        tasks = [(
            print_results,
            [checker, target, req_session_fun, args.verbose, args.timeout],
            {},
        ) for checker in checkers]

        executor = AsyncioProgressbarQueueExecutor(
            logger=logger,
            in_parallel=args.max_connections,
            timeout=args.timeout + 0.5,
            progress_func=tqdm.tqdm if args.progressbar else stub_progress,
        )

        await executor.run(tasks)

    for session in _open_sessions:
        try:
            if hasattr(session, 'closed') and session.closed:
                continue
            await session.close()
        except Exception:
            pass
    _open_sessions.clear()

if __name__ == '__main__':
    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        sys.exit(0)


