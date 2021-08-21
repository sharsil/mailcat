# mailcat

<p align="center">
	<img src=./mailcat.png" height="200"/>
</p>

The cat who can find existing email addresses by nickname.

## Usage

	./mailcat.py username

It's recommended to run script through Tor and proxies, for example, with proxychains:

	proxychains4 -q python3 mailcat.py username

## Supported providers

Total 22 providers, > 60 domains and > 100 aliases.

| Name                | Domains                                | Method            |
| ------------------- | -------------------------------------- | ----------------- |
| Gmail               | gmail.com                              | SMTP              |
| Yandex              | yandex.ru + 5 aliases                  | SMTP              |
| Protonmail          | protonmail.com + 2 aliases             | HTTP API          |
| MailRu              | mail.ru + 4 other domains              | HTTP API          |
| Rambler             | rambler.ru + 5 other domains           | HTTP API          |
| Tutanota            | tutanota.com + 4 other domains         | HTTP API          |
| Yahoo               | yahoo.com                              | HTTP API          |
| Outlook             | outlook.com, hotmail.com               | HTTP API          |
| Zoho                | zohomail.com                           | HTTP API          |
| Lycos               | lycos.com                              | HTTP API          |
| Eclipso             | eclipso.eu + 9 other domains           | HTTP API          |
| Posteo              | posteo.net + 50 aliases                | HTTP API          |
| Mailbox.org         | mailbox.org                            | HTTP API          |
| Firemail            | firemail.de + 2 other domains          | HTTP API          |
| Fastmail            | fastmail.com                           | HTTP API          |
| StartMail           | startmail.com                          | HTTP API          |
| KOLABNOW            | kolabnow.com + 23 aliases              | HTTP API          |
| bigmir)net          | i.ua, ua.fm, email.ua                  | HTTP API          |
| tut.by              | tut.by                                 | HTTP API          |
| Xmail               | xmail.net                              | HTTP API          |
| Ukrnet              | ukr.net                                | HTTP API          |
| Runbox              | runbox.com + 30 other domains          | HTTP API          |
