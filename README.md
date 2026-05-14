# kaskad_web_vpn — Kaskad Web UI v2

Веб-панель на **Flask** с **HTTP Basic Auth**: дашборд как у классического «каскада» — блок **Система**, таблица **Сервисы**, CRUD **клиентов (NAT / DNAT)** и просмотр цепочки **iptables**. В шапке — ваши ссылки на поддержку (GitHub, Boosty, Ozon СБП, Telegram), без чужой рекламы в подвале.

Репозиторий: [github.com/andrey271192/kaskad_web_vpn](https://github.com/andrey271192/kaskad_web_vpn)

## Важно про NAT

Правила записываются в **`nat`**, отдельная цепочка **`KASKAD_WEB`**, подключение к **`PREROUTING`** (DNAT `входящий_порт → target:порт`). Для рабочего каскада на VPS нужны **`net.ipv4.ip_forward=1`** и разрешения в **`filter/FORWARD`** (настраиваются на хосте отдельно).

По умолчанию установка поднимает контейнер с **`--network host`** и **`--privileged`**, чтобы **iptables менял таблицы самого хоста**. Режим только с `-p порт:8088` без host network применим для просмотра UI, но DNAT с контейнера на хост в таком виде обычно **не** используют.

Данные правил: **`KASKAD_DATA_DIR`** на хосте → `/var/lib/kaskad/rules.json` в контейнере.

## Требования

- Linux с Docker (для NAT — предпочтительно host network + privileged).
- Доступ к **`docker.sock`** на хосте (по умолчанию монтируется), чтобы в таблице «Сервисы» третья строка могла показывать статус **самого контейнера** как `kaskad-web.service`.

## Установка одной командой

Порт **8088**, логин **user1**, пароль в **`/root/kaskad_web.initial-password`** (или задайте **`ADMIN_PASSWORD`**):

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/install.sh | sudo bash
```

Свой пароль и порт:

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/install.sh | sudo \
  env ADMIN_PASSWORD='ваш_секрет' HOST_PORT=8443 bash
```

Панель Amnezia (опционально, ссылка на странице):

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/install.sh | sudo \
  env PANEL_URL='https://panel.example.com' bash
```

### Переменные установки (install.sh)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `HOST_PORT` | `8088` | Порт HTTP (при host network = `PORT` внутри процесса) |
| `KASKAD_HOST_NETWORK` | `1` | `1` — `--network host`; `0` — проброс `-p HOST_PORT:8088` (NAT на хост может быть недоступен) |
| `KASKAD_DATA_DIR` | `/var/lib/kaskad` | Том с `rules.json` |
| `MOUNT_DOCKER_SOCK` | `1` | Монтировать `/var/run/docker.sock` для статуса контейнера в «Сервисы» |
| `BASIC_AUTH_USER` | `user1` | Логин Basic Auth |
| `ADMIN_PASSWORD` | — | Пароль |
| `PASSWORD_FILE` | `/root/kaskad_web.initial-password` | Файл пароля при автогенерации |
| `PANEL_URL` | пусто | Доп. ссылка в шапке |
| `KASKAD_REPO` | `andrey271192/kaskad_web_vpn` | Репозиторий |
| `KASKAD_REF` | `main` | Ветка |

### Переменные внутри приложения (Docker `-e`)

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN`, `BOT_CHAT_ID` | Отображаются в блоке «Система» в замаскированном виде |
| `SERVICE_UNITS` | CSV юнитов systemd для первых двух строк (по умолчанию `kaskad_bot.service,kaskad-monitor.service,kaskad-web.service`) |
| `DOCKER_WEB_CONTAINER` | Имя контейнера для третьей строки (install выставляет автоматически) |
| `DOCKER_WEB_DISPLAY_UNIT` | Подпись в таблице для этой строки (по умолчанию `kaskad-web.service`) |
| `KASKAD_UI_VERSION` | Версия в блоке «yaskad» (по умолчанию `v2.2`) |
| `KASKAD_NAT_CHAIN` | Имя цепочки в `nat` (по умолчанию `KASKAD_WEB`) |

## Удаление контейнера

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/uninstall.sh | sudo bash
```

Образ:

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/uninstall.sh | sudo env REMOVE_IMAGE=1 bash
```

Цепочку iptables после экспериментов можно убрать вручную (осторожно, на проде проверяйте порядок правил):

```bash
iptables -t nat -D PREROUTING -j KASKAD_WEB  # повторять, пока не вернёт ошибку
iptables -t nat -F KASKAD_WEB
iptables -t nat -X KASKAD_WEB
```

## Локально без Docker

Нужны root-права для `iptables` и установленные `iptables` / `ip`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export BASIC_AUTH_PASSWORD='secret'
sudo -E env PATH="$PATH" flask --app app run --host 0.0.0.0 --port 8088
```

Проверка без авторизации: `GET /health`.

## API (после Basic Auth)

- `GET /api/system`, `/api/services`, `/api/clients`
- `POST /api/clients`, `PUT /api/clients/<id>`, `DELETE /api/clients/<id>`
- `GET /api/iptables/raw`, `POST /api/iptables/sync`

## Лицензия

MIT
