# kaskad_web_vpn — Kaskad Web UI v2

Веб-панель на **Flask** с **HTTP Basic Auth**: дашборд в духе «каскада» — **Система**, **Сервисы**, CRUD **NAT / DNAT**, сырые **iptables**. Это **отдельная открытая реализация** под ваш GitHub: без пунктов меню PROMO/«anten-ka», без телеграм-бота и терминального `gokaskad` из коммерческого Kaskad PRO; зато установка **curl | bash** с этого репозитория и понятный NAT для AmneziaWG / TCP по схеме «RU VPS → DNAT → зарубежный сервер».

Репозиторий: [github.com/andrey271192/kaskad_web_vpn](https://github.com/andrey271192/kaskad_web_vpn)

## Первый вход и пароль

- **По умолчанию** скрипт установки **не** задаёт пароль в Docker: откройте в браузере **`http://<ваш_IP>:<порт>/setup`**, придумайте пароль (≥ 8 символов) и логин (часто оставляют `user1`). Хэш сохраняется в томе: **`/var/lib/kaskad/web_auth.json`**.
- Чтобы задать пароль сразу при установке: **`ADMIN_PASSWORD`** или файл **`PASSWORD_FILE`** — тогда шаг `/setup` не нужен.
- Как раньше (случайный пароль в файл): **`FORCE_RANDOM_PASSWORD=1`**.
- Если заданы **`BASIC_AUTH_PASSWORD`** / **`ADMIN_PASSWORD`**, используется они (перекрывают файл).

## NAT и совместимость с логикой Kaskad PRO

Переменная **`KASKAD_IPTABLES_MODE`** (в контейнере, install передаёт **`compat`** по умолчанию):

| Значение | Поведение |
|----------|-----------|
| **`compat`** (по умолчанию) | Как в Kaskad PRO: **DNAT** в **`nat/PREROUTING`**, **INPUT** и парой правил **FORWARD** с комментарием **`kaskad:PORT:proto`**, один раз **MASQUERADE** на исходящем интерфейсе (авто через `ip route` или **`KASKAD_OUT_IFACE`**). |
| **`chain`** | Старая схема: отдельная цепочка **`nat/KASKAD_WEB`** и jump из PREROUTING. |

Нужны **`net.ipv4.ip_forward=1`** и достаточное место на диске под Docker.

Установка по умолчанию: **`--network host`** и **`--privileged`**, чтобы правила применялись к **таблицам хоста**. Данные правил: **`KASKAD_DATA_DIR`** → `/var/lib/kaskad/rules.json`.

Попытка сохранить правила в **`netfilter-persistent`**, если установлен на хосте.

## Требования

- Linux с Docker (для NAT — host network + privileged).
- По желанию **`/var/run/docker.sock`** (чтобы в «Сервисах» отображался статус контейнера как `kaskad-web.service`).

## Сборка образа: «invalid signature» / apt

См. блок в Wiki ниже — типично кэш builder, прокси, диск, время.

```bash
docker builder prune -af
docker build --pull --no-cache -t kaskad-web-vpn:test .
```

В Dockerfile зеркала APT переведены на HTTPS.

## Установка одной командой

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/install.sh | sudo bash
```

Затем откройте **`/setup`** или задайте пароль при установке:

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/install.sh | sudo \
  env ADMIN_PASSWORD='ваш_секрет' HOST_PORT=8443 bash
```

Старый режим «случайный пароль в файл»:

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/install.sh | sudo \
  env FORCE_RANDOM_PASSWORD=1 bash
```

### Переменные install.sh

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `HOST_PORT` | `8088` | HTTP-порт |
| `KASKAD_HOST_NETWORK` | `1` | host network / или `-p` |
| `KASKAD_DATA_DIR` | `/var/lib/kaskad` | том данных |
| `KASKAD_IPTABLES_MODE` | `compat` | `compat` или `chain` |
| `ADMIN_PASSWORD` | — | пароль без `/setup` |
| `FORCE_RANDOM_PASSWORD` | `0` | `1` — автопароль в `PASSWORD_FILE` |
| `PASSWORD_FILE` | `/root/kaskad_web.initial-password` | при FORCE_RANDOM или чтении пароля |
| `BASIC_AUTH_USER` | `user1` | логин при использовании env-пароля |
| `PANEL_URL` | — | ссылка в шапке |

### Переменные приложения

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN`, `BOT_CHAT_ID` | только отображение в «Системе» (маска), без бота |
| `SERVICE_UNITS`, `DOCKER_WEB_*` | таблица сервисов |
| `KASKAD_OUT_IFACE` | исходящий интерфейс для MASQUERADE |
| `WEB_AUTH_JSON` | путь к `web_auth.json` |

## Удаление контейнера

```bash
curl -fsSL https://raw.githubusercontent.com/andrey271192/kaskad_web_vpn/main/uninstall.sh | sudo bash
```

Режим **`chain`**: удаление jump в **`KASKAD_WEB`** см. исторический README в git.

Режим **`compat`**: проще снять правила через панель (удалить клиентов) или выборочно удалять строки с **`kaskad:`** в `iptables -S INPUT/FORWARD` и соответствующие DNAT в `iptables -t nat -S PREROUTING`.

## Локально без Docker

```bash
pip install -r requirements.txt
# либо задайте BASIC_AUTH_PASSWORD, либо откройте /setup
sudo -E env PATH="$PATH" flask --app app run --host 0.0.0.0 --port 8088
```

`GET /health` без авторизации. `GET /api/meta` — флаг `needs_setup`, режим iptables.

## API

После Basic Auth: `/api/system`, `/api/services`, `/api/clients`, CRUD клиентов, `/api/iptables/raw`.

## Лицензия

MIT
