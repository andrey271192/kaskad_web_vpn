# kaskad_web_vpn

Мини-сайт на Flask с **HTTP Basic Auth**: памятка про каскад **AmneziaWG**, без сторонней рекламы. В шапке — ссылки автора на поддержку (GitHub, Boosty, Ozon СБП, Telegram).

Репозиторий: [github.com/andrey271192/kaskad_web_vpn](https://github.com/andrey271192/kaskad_web_vpn)

## Требования

- Docker с доступом для текущего пользователя (или запуск скриптов от root).

## Установка одной командой

На сервере (порт хоста по умолчанию **8088**, логин **user1**, пароль генерируется и пишется в `/root/kaskad_web.initial-password`):

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/install.sh | sudo bash
```

Свой пароль и порт:

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/install.sh | sudo \
  env ADMIN_PASSWORD='ваш_секрет' HOST_PORT=8443 bash
```

Опционально ссылка на вашу веб-панель Amnezia (подставится на страницу):

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/install.sh | sudo \
  env PANEL_URL='https://panel.example.com' bash
```

Переменные окружения установки:

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `HOST_PORT` | `8088` | Порт на хосте (`HOST_PORT:8088` в контейнере) |
| `BASIC_AUTH_USER` | `user1` | Логин Basic Auth |
| `ADMIN_PASSWORD` | — | Пароль; если не задан — берётся из файла или генерируется |
| `PASSWORD_FILE` | `/root/kaskad_web.initial-password` | Файл с паролем при автогенерации |
| `PANEL_URL` | пусто | URL панели для блока на главной |
| `KASKAD_REPO` | `andrey271192/kaskad_web_vpn` | Репозиторий GitHub |
| `KASKAD_REF` | `main` | Ветка |
| `KASKAD_INSTALL_ROOT` | `/opt` | Куда распаковать исходники для сборки |

## Удаление

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/uninstall.sh | sudo bash
```

Удалить ещё и Docker-образ:

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/uninstall.sh | sudo env REMOVE_IMAGE=1 bash
```

## Локально без Docker

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export BASIC_AUTH_PASSWORD='secret'
flask --app app run --host 0.0.0.0 --port 8088
```

Проверка без авторизации: `GET /health`.

## Лицензия

MIT
