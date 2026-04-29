# mailcat

<p align="center">
	<img src="https://github.com/sharsil/mailcat/blob/main/logo.png?raw=true" height="200"/>
</p>

---

The only cat who can find existing email addresses by nickname.

## Usage

First install requirements:
	
	pip3 install -r requirements.txt

Then just run the script:

	./mailcat.py username

It's recommended to run script through Tor or a proxy — see [Routing through Tor](#routing-through-tor) below.

	./mailcat.py --tor username
	proxychains4 -q python3 mailcat.py username

	./mailcat.py username --proxy http://1.2.3.4:8080

## Batch mode

You can check multiple usernames in one run.

Pass several usernames as positional arguments:

	./mailcat.py alice bob charlie

Or supply a file with one username (or email address) per line:

	./mailcat.py --file usernames.txt

File format example:

	alice
	bob@proton.me
	charlie

You can also combine both — positional names are merged with those from the file:

	./mailcat.py alice --file more_users.txt

When more than one username is resolved, a header is printed before each result block so the output is easy to follow:

	[*] Checking username: alice
	...
	[*] Checking username: bob
	...

## Supported providers

**25 active providers covering > 155 domains** (plus ~50 Posteo alias domains).
Active checks run by default; deprecated checks remain in the source for revival
but are skipped on a default run. See the comment block above each function in
`mailcat.py` for the upstream change that broke it and notes on how to revive it.

| Name        | Domains                              | Method            | Status     |
| ----------- | ------------------------------------ | ----------------- | ---------- |
| Gmail       | gmail.com                            | SMTP              | Active     |
| Yandex      | yandex.ru + 5 aliases                | SMTP              | Active     |
| Protonmail  | protonmail.com + 3 aliases           | API               | Active     |
| MailRu      | mail.ru + 4 other domains            | Registration      | Active     |
| Rambler     | rambler.ru + 5 other domains         | Registration      | Active     |
| Yahoo       | yahoo.com                            | Registration      | Active     |
| Outlook     | outlook.com, hotmail.com             | Headless Chromium | Active     |
| Zoho        | zohomail.com                         | Registration      | Active     |
| Eclipso     | eclipso.eu + 9 other domains         | Registration      | Active     |
| Posteo      | posteo.net + ~50 aliases             | Registration      | Active     |
| Firemail    | firemail.de + 2 other domains        | Registration      | Active     |
| Fastmail    | fastmail.com                         | Headless Chromium | Active     |
| StartMail   | startmail.com                        | Registration      | Active     |
| Ukrnet      | ukr.net                              | Registration      | Active     |
| Runbox      | runbox.com + 29 other domains        | Registration      | Active     |
| DuckGo      | duck.com                             | Registration      | Active     |
| emailn      | emailn.de                            | Registration      | Active     |
| aikq        | aikq.de + 40 other domains           | Registration      | Active     |
| Vivaldi     | vivaldi.net                          | Registration      | Active     |
| mailDe      | mail.de                              | SMTP              | Active     |
| int.pl      | int.pl                               | Headless Chromium | Active     |
| Interia     | interia.pl + 10 other domains        | Password recovery | Active     |
| t.pl        | t.pl + 8 other domains               | Registration      | Active     |
| onet.pl     | onet.pl + 15 other domains           | Headless Chromium | Active     |
| Mailum      | cyberfear.com, mailum.com            | Registration      | Active     |
| iCloud      | icloud.com, me.com, mac.com          | Account recovery  | Deprecated |
| HushMail    | hushmail.com + 5 other domains       | Registration      | Deprecated |
| Xmail       | xmail.net                            | Registration      | Deprecated |
| Tutanota    | tutanota.com + 4 other domains       | Registration      | Deprecated |
| Mailbox.org | mailbox.org                          | Registration      | Deprecated |
| WP          | wp.pl                                | Registration      | Deprecated |
| O2          | o2.pl                                | Registration      | Deprecated |
| Gazeta.pl   | gazeta.pl                            | Registration      | Deprecated |

## Troubleshooting

Use `-m` or `--max-connections` if you get connection errors (Mailcat does 10 parallel connections max by default).

### Routing through Tor

The SMTP-based checks (`gmail`, `yandex`, `mailDe`) reach the destination
provider's MX servers on TCP port 25. Most residential ISPs and every major
cloud provider (AWS, GCP, Azure, Heroku, …) **block outbound port 25** as
an anti-spam measure, so these checks will time out with messages like:

	Error while checking gmail: Timed out connecting to gmail-smtp-in.l.google.com. on port 25

Tor exit nodes generally do not have port 25 blocked, which makes routing
through Tor the easiest fix. Mailcat has built-in Tor support via the
`--tor` flag — it expects a SOCKS5 proxy at `127.0.0.1:9050` (the default
when you run `tor` locally).

	# 1. Start Tor (macOS / Linux)
	brew install tor && tor &        # macOS
	sudo systemctl start tor          # Linux with systemd

	# 2. Run mailcat through Tor — SMTP checks now succeed
	./mailcat.py alex --tor

	# Or restrict to just the providers that need it
	./mailcat.py alex --tor -p gmail -p yandex -p mailDe

Tor adds ~5–15 s of latency per request, but it is the only reliable way
to make the SMTP-25 checks work from a typical home or cloud environment.
A clean VPS with unblocked egress 25 (Hetzner after verification, OVH,
Vultr) works equally well — point mailcat at it via `--proxy` or just run
mailcat on the VPS itself.

The HTTP-based checks (everything else) work fine from any network and
do not require Tor.

### SOWEL classification

This tool uses the following OSINT techniques:
- [SOTL-2.2. Search For Accounts On Other Platforms](https://sowel.soxoj.com/other-platform-accounts)
- [SOTL-6.1. Check Logins Reuse To Find Another Account](https://sowel.soxoj.com/logins-reuse)
- [SOTL-6.2. Check Nicknames Reuse To Find Another Account](https://sowel.soxoj.com/nicknames-reuse) 

## Mentions and articles

[OSINTEditor Sunday Briefing: Sensational Headlines and Kuomintang Chairmanship Elections]([https://www.osinteditor.com/general/osinteditor-sunday-briefing-sensational-headlines-and-kuomintang-chairmanship-elections/](https://web.archive.org/web/20220116223051/https://www.osinteditor.com/general/osinteditor-sunday-briefing-sensational-headlines-and-kuomintang-chairmanship-elections/))

[Michael Buzzel: 237 - The Huge OSINT Show by The Privacy, Security, & OSINT Show](https://soundcloud.com/user-98066669/237-the-huge-osint-show)

[bellingcat: First Steps to Getting Started in Open Source Research](https://www.bellingcat.com/resources/2021/11/09/first-steps-to-getting-started-in-open-source-research/)

[OS2INT verifying email addresses using Mailcat](https://os2int.com/toolbox/verifying-email-usernames-using-mailcat/)

[hwosint - Twitter post](https://twitter.com/harrywald80/status/1439115143485534212)
