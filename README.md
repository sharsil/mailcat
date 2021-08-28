# mailcat

<p align="center">
	<img src="https://github.com/sharsil/mailcat/blob/main/mailcat.png?raw=true" height="200"/>
</p>

---

The only cat who can find existing email addresses by nickname.

## Usage

	./mailcat.py username

It's recommended to run script through Tor and proxies. You can use internal Tor routing (`--tor`) or proxychains:

	./mailcat.py --tor username
	proxychains4 -q python3 mailcat.py username

## Supported providers

Total 22 providers, > 60 domains and > 100 aliases.

| Name                | Domains                                | Method            |
| ------------------- | -------------------------------------- | ----------------- |
| Gmail               | gmail.com                              | SMTP              |
| Yandex              | yandex.ru + 5 aliases                  | SMTP              |
| Protonmail          | protonmail.com + 2 aliases             | API               |
| iCloud              | icloud.com, me.com, mac.com            | Access recovery   |
| tut.by              | tut.by                                 | SMTP/Registration |
| MailRu              | mail.ru + 4 other domains              | Registration      |
| Rambler             | rambler.ru + 5 other domains           | Registration      |
| Tutanota            | tutanota.com + 4 other domains         | Registration      |
| Yahoo               | yahoo.com                              | Registration      |
| Outlook             | outlook.com, hotmail.com               | Registration      |
| Zoho                | zohomail.com                           | Registration      |
| Lycos               | lycos.com                              | Registration      |
| Eclipso             | eclipso.eu + 9 other domains           | Registration      |
| Posteo              | posteo.net + 50 aliases                | Registration      |
| Mailbox.org         | mailbox.org                            | Registration      |
| Firemail            | firemail.de + 2 other domains          | Registration      |
| Fastmail            | fastmail.com                           | Registration      |
| StartMail           | startmail.com                          | Registration      |
| KOLABNOW            | kolabnow.com + 23 aliases              | Registration      |
| bigmir)net          | i.ua, ua.fm, email.ua                  | Registration      |
| Xmail               | xmail.net                              | Registration      |
| Ukrnet              | ukr.net                                | Registration      |
| Runbox              | runbox.com + 30 other domains          | Registration      |
