"""Translation catalogs — source of truth; exported to en.json / ru.json."""

from __future__ import annotations

# Nested catalogs; flattened at runtime by i18n.__init__


def _merge(*parts: dict) -> dict:
    out: dict = {}
    for part in parts:
        out.update(part)
    return out


EN_CATALOG = {
    "app": {
        "title": {"hub": "Pyla-RL Hub", "settings": "Pyla-RL Settings"},
    },
    "nav": {
        "overview": "Overview",
        "instances": "Instances",
        "farmPlan": "Farm Plan",
        "settings": "Settings",
        "discord": "Discord",
        "telegram": "Telegram",
        "api": "API",
        "timers": "Timers",
        "matchHistory": "Match History",
        "help": "Help",
        "farmPlanCount": "Farm Plan ({count})",
    },
    "brand": {
        "productName": "Pyla-RL",
        "freeNotice": "Pyla-RL is free, open source, and must not be sold.",
        "footerNotice": "Pyla is free, public, and open-source.",
        "licenseName": "CC BY-NC 4.0",
        "downloadNotice": "Download only from GitHub or Pyla Discord.",
        "licenseLine": "{product} is free and open source under {license}. You may use and modify it, but you must not sell or resell it.",
        "licenseShort": "{product} is free. Licensed under {license}.",
    },
    "wizard": {
        "language": {
            "title": "Choose language / Выберите язык",
            "subtitle": "Hub, pause menu, and bot messages will use this language. / Хаб, меню паузы и сообщения бота будут на этом языке.",
            "english": "English",
            "russian": "Русский",
        },
        "step1": {"title": "Step 1: Free Use License"},
        "step2": {"title": "Step 2: Environment", "body": "Start your emulator, open Brawl Stars, then run pre-flight checks on Overview. Full guides for every feature are in the Help tab."},
        "step3": {"title": "Step 3: Optional Setup", "body": "Optional: configure Discord, Telegram, or API tabs for notifications and remote control. See the Help tab for setup tutorials."},
        "step4": {"title": "Step 4: Farm Plan", "body": "Build a farm plan on the Farm Plan tab, or use the legacy brawler picker after START if the queue is empty. Open Help anytime for full guides."},
        "licenseText": "I understand Pyla-RL is free and I will not sell it.",
        "licenseHint": "Select the agreement above to enable Next.",
        "back": "Back",
        "runChecks": "Run Checks",
        "openHelp": "Open Help",
        "next": "Next",
        "finish": "Finish",
    },
    "settings": {
        "language": {
            "title": "LANGUAGE",
            "hint": "Pause menu and remote replies use this language after restart or reopening the pause menu.",
            "english": "English",
            "russian": "Русский",
        },
    },
    "chrome": {
        "brand": "Pyla",
        "subtitle": {"hub": "Pyla-RL Hub", "settingsRunning": "Pyla-RL Settings (bot running)"},
        "startBar": {
            "ready": "Ready to start",
            "runChecks": "Run pre-flight checks on Overview",
            "start": "START",
            "close": "CLOSE",
            "checks": "Checks",
        },
    },
    "footer": {
        "joinDiscord": "Join Discord",
        "supportPatreon": "Support on Patreon",
    },
    "status": {
        "saved": "Saved",
        "working": "Working...",
        "waitForAction": "Please wait for the current hub action to finish.",
        "checkingPreflight": "Checking pre-flight...",
        "invalidTrophyTarget": "Enter a valid trophy target.",
        "farmPlanEmpty": "Farm plan is empty.",
        "restartForDebugScreen": "Restart bot to apply Debug Screen changes.",
    },
    "overview": {
        "preflight": {
            "title": "PRE-FLIGHT CHECKS",
            "description": "Verify emulator and ADB before START. Use 1920x1080 and 100% Windows scaling.",
            "runChecks": "Run Checks",
            "testConnection": "Test Connection",
            "recoveryLog": "Recovery Log",
            "fix": "Fix",
        },
        "performance": {"title": "PERFORMANCE PROFILE", "balanced": "balanced", "lowEnd": "low-end", "quality": "quality", "highIps": "high-ips"},
        "gameMode": {"title": "GAME MODE", "brawlBall": "Brawl Ball", "showdownTrio": "Showdown Trio"},
        "emulator": {"title": "EMULATOR", "ldplayer": "LDPlayer", "mumu": "MuMu"},
        "unofficialCopy": {"title": "UNOFFICIAL COPY", "officialGithub": "Official GitHub", "pylaDiscord": "Pyla Discord"},
    },
    "instances": {
        "readiness": {
            "unknown": "Unknown", "ready": "Ready", "needsFarmPlan": "Needs farm plan",
            "portConflict": "Port conflict", "noEmulator": "No emulator",
        },
    },
    "farmPlan": {
        "sort": {
            "cupsHighToLow": "Cups high → low", "cupsLowToHigh": "Cups low → high",
            "closestToTarget": "Closest to target", "furthestFromTarget": "Furthest from target",
            "targetHighToLow": "Target high → low", "targetLowToHigh": "Target low → high",
            "nameAToZ": "Name A → Z", "nameZToA": "Name Z → A", "bestTrophiesPerHour": "Best trophies/hour",
        },
    },
    "hub": {
        "action": {
            "anotherRunning": "Another hub action is still running.",
            "actionFailed": "Hub action failed.",
            "actionTimeout": "Hub action timed out. You can try again. If checks never finish, restart the Hub and confirm the emulator is running.",
            "preflightRunning": "Running pre-flight checks...",
            "testEmulatorRunning": "Testing emulator connection...",
            "buildQueueRunning": "Building farm plan...",
            "startingPyla": "Checking pre-flight...",
            "licenseAccepted": "License accepted. Pyla-RL is free and must not be sold.",
            "preflightReady": "Ready to start.",
            "preflightFixRequired": "Fix required checks before START.",
            "preflightFailedStart": "Pre-flight checks failed. Run checks on Overview and fix required items.",
            "startingMessage": "Starting Pyla-RL...",
            "emulatorOk": "Emulator connection OK: {detail}",
            "emulatorFailed": "Emulator connection failed: {detail}",
            "farmPlanImported": "Imported {count} brawler(s) from {name}.",
            "farmPlanExported": "Exported {count} brawler(s) to {name}.",
            "queueCleared": "Farm plan cleared.",
            "queueBuilt": "Built Push All queue with {count} brawler(s) to {target} trophies.",
            "instanceSaved": "Saved instance '{id}'.",
            "settingsSaved": "Instance settings saved.",
            "farmPlanCopied": "Farm plan copied.",
            "wizardComplete": "Setup wizard completed.",
            "wizardReopened": "Setup wizard reopened.",
            "wizardReset": "Setup wizard will show again on next launch. Opening it now.",
            "apiTestRunning": "Testing Brawl Stars API...",
            "sortQueueRunning": "Sorting farm plan...",
            "importQueueRunning": "Importing farm plan...",
            "calibrateRunning": "Calibrating performance profile...",
            "checkUpdatesRunning": "Checking for updates...",
            "exportHistoryRunning": "Exporting match history...",
            "refreshHistoryRunning": "Refreshing match history...",
            "multiInstanceNotRunning": "Multi-instance service is not running.",
            "webhookTestSent": "Webhook test sent.",
            "settingsDisabledWhileRunning": "START is disabled while the bot is running. Close this window when finished editing settings.",
            "multiInstanceUseInstances": "Multi-instance mode is enabled. Start bots from the Instances tab.",
            "licenseRequiredBeforeStart": "Accept the free-use license in the hub wizard or Settings → About before START.",
            "openedFile": "Opened {name}",
        },
    },
    "pause": {
        "title": "Pyla  ·  Control",
        "status": "STATUS",
        "running": "Running",
        "paused": "Paused",
        "pauseBot": "Pause Bot",
        "resumeBot": "Resume Bot",
        "pause": "Pause",
        "resume": "Resume",
        "settings": "Settings",
        "quit": "Quit",
        "ipsFeed": "IPS {ips} · Feed {feed}",
        "ipsEmpty": "IPS -- · Feed --",
        "sessionWins": "W{wins} L{losses} · IPS {ips} · {feed}",
        "stopBot": "Stop Bot",
        "openHub": "Open Hub",
        "copied": "Copied!",
        "hub": "Hub",
    },
    "login": {
        "title": "API Key Login",
        "prompt": "Enter API Key:",
        "placeholder": "API Key",
        "button": "Login",
        "success": "Login Successful!",
        "invalid": "Invalid API Key",
    },
    "select": {
        "title": "Pyla-RL",
        "search": "Search brawler",
        "pushAll": "Push All",
        "startPyla": "Start Pyla",
        "pushOrder": "Push Order",
        "selectBrawler": "Select Brawler Config File",
        "priority": "Priority",
        "selectedCount": "{count} selected",
        "brawlers": "Brawlers",
        "noPriority": "No priority order selected",
    },
    "remote": {
        "result": {
            "1st": "1st Place", "2nd": "2nd Place", "3rd": "3rd Place (Tie)",
            "4th": "4th Place", "victory": "Victory", "defeat": "Defeat", "draw": "Draw",
        },
        "status": {
            "runtime": "Runtime", "state": "State", "ips": "IPS", "feed_fps": "Feed FPS",
            "emulator": "Emulator", "adb_device": "ADB Device", "brawler": "Brawler",
            "target": "Target", "last_match": "Last Match", "queue_preview": "Queue",
            "last_recovery": "Last Recovery",
        },
        "state": {"running": "Running", "paused": "Paused", "stopping": "Stopping"},
        "queueEmpty": "Farm plan is empty.",
        "queueMore": "  … and {count} more",
        "targetReached": "**{brawler}** reached the target at **{target}**.",
        "targetReachedGeneric": "Configured target reached.",
        "recoveryDefault": "Pyla-RL triggered a recovery action.",
        "help": {
            "statusTitle": "Pyla-RL status",
            "discordTitle": "Pyla-RL Remote Commands",
            "discordDescription": "Use these slash commands to control your local bot instance.",
            "sectionControl": "Control",
            "sectionFarmPlan": "Farm Plan",
            "sectionRecovery": "Recovery",
            "sectionOther": "Other",
            "discordControlCommands": "/start, /pause, /stop_all, /status, /stats",
            "discordFarmCommands": "/push, /skip, /remove, /target, /queue",
            "discordRecoveryCommands": "/restart_game, /restart_scrcpy, /restart_emulator",
            "discordOtherCommands": "/screenshot, /press, /back, /pause_menu",
            "telegram": "<b>Pyla-RL Telegram commands</b>\n<b>Control</b>\n/status, /stats, /pause, /resume, /quit, /pause_menu\n<b>Farm Plan</b>\n/push, /skip, /remove, /target, /queue\n<b>Recovery</b>\n/restart_game, /restart_scrcpy, /restart_emulator\n<b>Other</b>\n/screenshot, /back, /press\n\nUse /setup to show this list. Save this chat ID in the Telegram tab before control commands work.",
            "unknownCommand": "Unknown command. Send /help.",
            "unknownBrawler": "Unknown brawler '{name}'.",
        },
    },
    "profile": {
        "balanced": "Good default for most PCs: uncapped bot loop with a 60 FPS emulator feed.",
        "low_end": "Lower heat/CPU profile for older laptops or thermal throttling.",
        "quality": "Sharper capture for strong PCs; uncapped bot loop with a 60 FPS emulator feed.",
        "quality_fullres": "Full-resolution emulator capture for strong PCs (1920 native width).",
        "high_ips": "Maximum throughput: debug overlays off, fewer vision passes, tuned duplicate-frame replay.",
    },
    "preflight": {
        "adbLabel": "ADB device {serial}",
        "emulatorProcess": "{emulator} process",
        "resolution": "Resolution",
        "brawlStars": "Brawl Stars installed",
        "zoom": "Windows display scaling",
        "checksTitle": "Pre-flight checks",
        "adbFailed": "ADB check failed",
        "gameForeground": "Brawl Stars foreground",
        "gameInForeground": "In foreground",
        "gameOpenBeforeStart": "Open Brawl Stars on the emulator before START",
        "resolutionHint": "Use 1920x1080 emulator resolution for best accuracy",
        "resolutionLabel": "1080p recommended",
        "zoomOk": "Display scaling is 100%",
        "zoomFix": "Set Windows display scaling to 100% to avoid misclicks",
        "fix": {
            "reconnectAdb": "Reconnect ADB",
            "startEmulator": "Start Emulator",
            "launchGame": "Launch Game",
            "resolutionHelp": "Resolution Help",
        },
    },
}

RU_CATALOG = {
    "app": {
        "title": {"hub": "Pyla-RL Хаб", "settings": "Pyla-RL Настройки"},
    },
    "nav": {
        "overview": "Обзор",
        "instances": "Экземпляры",
        "farmPlan": "План фарма",
        "settings": "Настройки",
        "discord": "Discord",
        "telegram": "Telegram",
        "api": "API",
        "timers": "Таймеры",
        "matchHistory": "История матчей",
        "help": "Справка",
        "farmPlanCount": "План фарма ({count})",
    },
    "brand": {
        "productName": "Pyla-RL",
        "freeNotice": "Pyla-RL бесплатен, с открытым исходным кодом; его нельзя продавать.",
        "footerNotice": "Pyla бесплатен, публичен и с открытым исходным кодом.",
        "licenseName": "CC BY-NC 4.0",
        "downloadNotice": "Скачивайте только с GitHub или Discord Pyla.",
        "licenseLine": "{product} бесплатен и с открытым исходным кодом под {license}. Можно использовать и изменять, но нельзя продавать или перепродавать.",
        "licenseShort": "{product} бесплатен. Лицензия: {license}.",
    },
    "wizard": {
        "language": {
            "title": "Choose language / Выберите язык",
            "subtitle": "Hub, pause menu, and bot messages will use this language. / Хаб, меню паузы и сообщения бота будут на этом языке.",
            "english": "English",
            "russian": "Русский",
        },
        "step1": {"title": "Шаг 1: Лицензия бесплатного использования"},
        "step2": {"title": "Шаг 2: Окружение", "body": "Запустите эмулятор, откройте Brawl Stars, затем выполните проверки на вкладке Обзор. Полные руководства — во вкладке Справка."},
        "step3": {"title": "Шаг 3: Дополнительно", "body": "По желанию настройте Discord, Telegram или API для уведомлений и удалённого управления. Инструкции — во вкладке Справка."},
        "step4": {"title": "Шаг 4: План фарма", "body": "Соберите план фарма на вкладке План фарма или используйте классический выбор бойца после START, если очередь пуста."},
        "licenseText": "Я понимаю, что Pyla-RL бесплатен, и не буду его продавать.",
        "licenseHint": "Отметьте соглашение выше, чтобы включить Далее.",
        "back": "Назад",
        "runChecks": "Запустить проверки",
        "openHelp": "Открыть справку",
        "next": "Далее",
        "finish": "Готово",
    },
    "settings": {
        "language": {
            "title": "ЯЗЫК",
            "hint": "Меню паузы и удалённые ответы используют этот язык после перезапуска или повторного открытия меню паузы.",
            "english": "English",
            "russian": "Русский",
        },
    },
    "chrome": {
        "brand": "Pyla",
        "subtitle": {"hub": "Pyla-RL Хаб", "settingsRunning": "Pyla-RL Настройки (бот запущен)"},
        "startBar": {
            "ready": "Готов к запуску",
            "runChecks": "Выполните проверки на вкладке Обзор",
            "start": "СТАРТ",
            "close": "ЗАКРЫТЬ",
            "checks": "Проверки",
        },
    },
    "footer": {
        "joinDiscord": "Discord",
        "supportPatreon": "Patreon",
    },
    "status": {
        "saved": "Сохранено",
        "working": "Работа...",
        "waitForAction": "Дождитесь завершения текущего действия.",
        "checkingPreflight": "Проверка перед запуском...",
        "invalidTrophyTarget": "Введите корректную цель по кубкам.",
        "farmPlanEmpty": "План фарма пуст.",
        "restartForDebugScreen": "Перезапустите бота, чтобы применить экран отладки.",
    },
    "overview": {
        "preflight": {
            "title": "ПРОВЕРКИ ПЕРЕД ЗАПУСКОМ",
            "description": "Проверьте эмулятор и ADB перед СТАРТ. Используйте 1920x1080 и масштаб Windows 100%.",
            "runChecks": "Запустить проверки",
            "testConnection": "Тест соединения",
            "recoveryLog": "Журнал восстановления",
            "fix": "Исправить",
        },
        "performance": {"title": "ПРОФИЛЬ ПРОИЗВОДИТЕЛЬНОСТИ", "balanced": "сбалансированный", "lowEnd": "слабый ПК", "quality": "качество", "highIps": "макс. IPS"},
        "gameMode": {"title": "РЕЖИМ ИГРЫ", "brawlBall": "Brawl Ball", "showdownTrio": "Showdown Trio"},
        "emulator": {"title": "ЭМУЛЯТОР", "ldplayer": "LDPlayer", "mumu": "MuMu"},
        "unofficialCopy": {"title": "НЕОФИЦИАЛЬНАЯ КОПИЯ", "officialGithub": "Официальный GitHub", "pylaDiscord": "Discord Pyla"},
    },
    "instances": {
        "readiness": {
            "unknown": "Неизвестно", "ready": "Готов", "needsFarmPlan": "Нужен план фарма",
            "portConflict": "Конфликт порта", "noEmulator": "Нет эмулятора",
        },
    },
    "farmPlan": {
        "sort": {
            "cupsHighToLow": "Кубки: высокие → низкие", "cupsLowToHigh": "Кубки: низкие → высокие",
            "closestToTarget": "Ближе к цели", "furthestFromTarget": "Дальше от цели",
            "targetHighToLow": "Цель: высокая → низкая", "targetLowToHigh": "Цель: низкая → высокая",
            "nameAToZ": "Имя А → Я", "nameZToA": "Имя Я → А", "bestTrophiesPerHour": "Лучший кубков/час",
        },
    },
    "hub": {
        "action": {
            "anotherRunning": "Другое действие хаба ещё выполняется.",
            "actionFailed": "Действие не удалось.",
            "actionTimeout": "Время действия истекло. Попробуйте снова. Если проверки не завершаются, перезапустите хаб и убедитесь, что эмулятор запущен.",
            "preflightRunning": "Выполняются проверки перед запуском...",
            "testEmulatorRunning": "Проверка соединения с эмулятором...",
            "buildQueueRunning": "Создание плана фарма...",
            "startingPyla": "Проверка перед запуском...",
            "licenseAccepted": "Лицензия принята. Pyla-RL бесплатен; его нельзя продавать.",
            "preflightReady": "Готов к запуску.",
            "preflightFixRequired": "Исправьте обязательные проверки перед СТАРТ.",
            "preflightFailedStart": "Проверки не пройдены. Исправьте ошибки на вкладке Обзор.",
            "startingMessage": "Запуск Pyla-RL...",
            "emulatorOk": "Соединение с эмулятором OK: {detail}",
            "emulatorFailed": "Соединение с эмулятором не удалось: {detail}",
            "farmPlanImported": "Импортировано бойцов: {count} из {name}.",
            "farmPlanExported": "Экспортировано бойцов: {count} в {name}.",
            "queueCleared": "План фарма очищен.",
            "queueBuilt": "Создан план Push All: {count} бойцов до {target} кубков.",
            "instanceSaved": "Экземпляр «{id}» сохранён.",
            "settingsSaved": "Настройки экземпляра сохранены.",
            "farmPlanCopied": "План фарма скопирован.",
            "wizardComplete": "Мастер настройки завершён.",
            "wizardReopened": "Мастер настройки открыт снова.",
            "wizardReset": "Мастер настройки появится при следующем запуске. Открываем сейчас.",
            "apiTestRunning": "Проверка API Brawl Stars...",
            "sortQueueRunning": "Сортировка плана фарма...",
            "importQueueRunning": "Импорт плана фарма...",
            "calibrateRunning": "Калибровка профиля производительности...",
            "checkUpdatesRunning": "Проверка обновлений...",
            "exportHistoryRunning": "Экспорт истории матчей...",
            "refreshHistoryRunning": "Обновление истории матчей...",
            "multiInstanceNotRunning": "Служба мульти-экземпляра не запущена.",
            "webhookTestSent": "Тест webhook отправлен.",
            "settingsDisabledWhileRunning": "СТАРТ отключён, пока бот запущен. Закройте окно после редактирования настроек.",
            "multiInstanceUseInstances": "Включён мульти-экземпляр. Запускайте ботов с вкладки Экземпляры.",
            "licenseRequiredBeforeStart": "Примите лицензию в мастере или Настройки → О программе перед СТАРТ.",
            "openedFile": "Открыто: {name}",
        },
    },
    "pause": {
        "title": "Pyla  ·  Управление",
        "status": "СТАТУС",
        "running": "Работает",
        "paused": "Пауза",
        "pauseBot": "Пауза бота",
        "resumeBot": "Продолжить",
        "pause": "Пауза",
        "resume": "Продолжить",
        "settings": "Настройки",
        "quit": "Выход",
        "ipsFeed": "IPS {ips} · Поток {feed}",
        "ipsEmpty": "IPS -- · Поток --",
        "sessionWins": "П{wins} ПР{losses} · IPS {ips} · {feed}",
        "stopBot": "Остановить бота",
        "openHub": "Открыть хаб",
        "copied": "Скопировано!",
        "hub": "Хаб",
    },
    "login": {
        "title": "Вход по API-ключу",
        "prompt": "Введите API-ключ:",
        "placeholder": "API-ключ",
        "button": "Войти",
        "success": "Вход выполнен!",
        "invalid": "Неверный API-ключ",
    },
    "select": {
        "title": "Pyla-RL",
        "search": "Поиск бойца",
        "pushAll": "Push All",
        "startPyla": "Запустить Pyla",
        "pushOrder": "Порядок push",
        "selectBrawler": "Выберите файл конфигурации бойца",
        "priority": "Приоритет",
        "selectedCount": "Выбрано: {count}",
        "brawlers": "Бойцы",
        "noPriority": "Порядок приоритета не выбран",
    },
    "remote": {
        "result": {
            "1st": "1 место", "2nd": "2 место", "3rd": "3 место (ничья)",
            "4th": "4 место", "victory": "Победа", "defeat": "Поражение", "draw": "Ничья",
        },
        "status": {
            "runtime": "Время работы", "state": "Состояние", "ips": "IPS", "feed_fps": "FPS потока",
            "emulator": "Эмулятор", "adb_device": "ADB устройство", "brawler": "Боец",
            "target": "Цель", "last_match": "Последний матч", "queue_preview": "Очередь",
            "last_recovery": "Последнее восстановление",
        },
        "state": {"running": "Работает", "paused": "Пауза", "stopping": "Остановка"},
        "queueEmpty": "План фарма пуст.",
        "queueMore": "  … и ещё {count}",
        "targetReached": "**{brawler}** достиг цели **{target}**.",
        "targetReachedGeneric": "Настроенная цель достигнута.",
        "recoveryDefault": "Pyla-RL выполнил действие восстановления.",
        "help": {
            "statusTitle": "Статус Pyla-RL",
            "discordTitle": "Удалённые команды Pyla-RL",
            "discordDescription": "Используйте эти slash-команды для управления локальным ботом.",
            "sectionControl": "Управление",
            "sectionFarmPlan": "План фарма",
            "sectionRecovery": "Восстановление",
            "sectionOther": "Прочее",
            "discordControlCommands": "/start, /pause, /stop_all, /status, /stats",
            "discordFarmCommands": "/push, /skip, /remove, /target, /queue",
            "discordRecoveryCommands": "/restart_game, /restart_scrcpy, /restart_emulator",
            "discordOtherCommands": "/screenshot, /press, /back, /pause_menu",
            "telegram": "<b>Команды Telegram Pyla-RL</b>\n<b>Управление</b>\n/status, /stats, /pause, /resume, /quit, /pause_menu\n<b>План фарма</b>\n/push, /skip, /remove, /target, /queue\n<b>Восстановление</b>\n/restart_game, /restart_scrcpy, /restart_emulator\n<b>Прочее</b>\n/screenshot, /back, /press\n\nОтправьте /setup для списка. Сохраните chat ID на вкладке Telegram.",
            "unknownCommand": "Неизвестная команда. Отправьте /help.",
            "unknownBrawler": "Неизвестный боец «{name}».",
        },
    },
    "profile": {
        "balanced": "Хороший вариант по умолчанию: без лимита IPS и 60 FPS эмулятора.",
        "low_end": "Меньше нагрузка для слабых ноутбуков.",
        "quality": "Чётче захват для мощных ПК; 60 FPS эмулятора.",
        "quality_fullres": "Полное разрешение эмулятора (1920) для мощных ПК.",
        "high_ips": "Максимальная скорость: без оверлеев отладки, меньше проходов зрения.",
    },
    "preflight": {
        "adbLabel": "ADB устройство {serial}",
        "emulatorProcess": "Процесс {emulator}",
        "resolution": "Разрешение",
        "brawlStars": "Brawl Stars установлен",
        "zoom": "Масштаб Windows",
        "checksTitle": "Проверки перед запуском",
        "adbFailed": "Проверка ADB не удалась",
        "gameForeground": "Brawl Stars на переднем плане",
        "gameInForeground": "На переднем плане",
        "gameOpenBeforeStart": "Откройте Brawl Stars в эмуляторе перед СТАРТ",
        "resolutionHint": "Для лучшей точности используйте разрешение 1920x1080",
        "resolutionLabel": "Рекомендуется 1080p",
        "zoomOk": "Масштаб дисплея 100%",
        "zoomFix": "Установите масштаб Windows 100%, чтобы избежать промахов",
        "fix": {
            "reconnectAdb": "Переподключить ADB",
            "startEmulator": "Запустить эмулятор",
            "launchGame": "Запустить игру",
            "resolutionHelp": "Справка по разрешению",
        },
    },
}

# Extend EN/RU with full hub UI strings from extraction (shared keys)
_HUB_UI_EN = {
    "tutorial.fallbackTitle": "Guide",
    "tutorial.openFullGuide": "Open full guide",
    "tutorial.close": "Close",
    "instances.multiInstance.title": "MULTI-INSTANCE MODE",
    "instances.multiInstance.enable": "Enable Multi-Instance",
    "instances.multiInstance.scanEmulators": "Scan Emulators",
    "instances.multiInstance.startAllReady": "Start All Ready",
    "instances.multiInstance.stopAll": "Stop All",
    "instances.add.saveInstance": "Save Instance",
    "instances.configured.start": "Start",
    "instances.configured.stop": "Stop",
    "instances.configured.delete": "Delete",
    "farmPlan.pushAll.buildQueue": "Build Queue",
    "farmPlan.queue.add": "Add",
    "farmPlan.queue.emptyTitle": "No brawlers in the farm plan yet",
    "settings.about.title": "ABOUT",
    "settings.about.accept": "Accept",
    "settings.behavior.afterRound": "After Round",
    "settings.behavior.returnToLobby": "Return to lobby",
    "settings.behavior.playAgain": "Play again",
    "discord.sendTest": "Send Discord Test",
    "telegram.sendTest": "Send Telegram Test",
    "api.testConfig": "Test API Config",
    "matchHistory.title": "MATCH HISTORY",
    "matchHistory.exportCsv": "Export CSV",
    "help.featureGuides.title": "FEATURE GUIDES",
    "help.openGuide": "Open guide",
}

_HUB_UI_RU = {
    "tutorial.fallbackTitle": "Руководство",
    "tutorial.openFullGuide": "Открыть полное руководство",
    "tutorial.close": "Закрыть",
    "instances.multiInstance.title": "РЕЖИМ НЕСКОЛЬКИХ ЭКЗЕМПЛЯРОВ",
    "instances.multiInstance.enable": "Включить мульти-экземпляр",
    "instances.multiInstance.scanEmulators": "Сканировать эмуляторы",
    "instances.multiInstance.startAllReady": "Запустить готовые",
    "instances.multiInstance.stopAll": "Остановить все",
    "instances.add.saveInstance": "Сохранить экземпляр",
    "instances.configured.start": "Старт",
    "instances.configured.stop": "Стоп",
    "instances.configured.delete": "Удалить",
    "farmPlan.pushAll.buildQueue": "Создать очередь",
    "farmPlan.queue.add": "Добавить",
    "farmPlan.queue.emptyTitle": "В плане фарма пока нет бойцов",
    "settings.about.title": "О ПРОГРАММЕ",
    "settings.about.accept": "Принять",
    "settings.behavior.afterRound": "После раунда",
    "settings.behavior.returnToLobby": "В лобби",
    "settings.behavior.playAgain": "Играть снова",
    "discord.sendTest": "Тест Discord",
    "telegram.sendTest": "Тест Telegram",
    "api.testConfig": "Тест API",
    "matchHistory.title": "ИСТОРИЯ МАТЧЕЙ",
    "matchHistory.exportCsv": "Экспорт CSV",
    "help.featureGuides.title": "РУКОВОДСТВА",
    "help.openGuide": "Открыть руководство",
}


def _nest_flat(flat: dict[str, str]) -> dict:
    nested: dict = {}
    for key, value in flat.items():
        parts = key.split(".")
        node = nested
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return nested


def _deep_merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


_deep_merge(EN_CATALOG, _nest_flat(_HUB_UI_EN))
_deep_merge(RU_CATALOG, _nest_flat(_HUB_UI_RU))

_TUTORIAL_TOPICS = {
    "gettingStarted": {
        "title": ("Getting Started", "Начало работы"),
        "tab": ("Help", "Справка"),
        "summary": (
            "1. Run setup.exe in the project folder.\n"
            "2. Launch pyla-rl.bat (or python app/main.py).\n"
            "3. Set emulator resolution to 1920x1080.\n"
            "4. Open Brawl Stars in the emulator before START.",
            "1. Запустите setup.exe в папке проекта.\n"
            "2. Запустите pyla-rl.bat (или python app/main.py).\n"
            "3. Установите разрешение эмулятора 1920x1080.\n"
            "4. Откройте Brawl Stars в эмуляторе перед СТАРТ.",
        ),
    },
    "overview": {
        "title": ("Overview and START", "Обзор и СТАРТ"),
        "tab": ("Overview", "Обзор"),
        "summary": (
            "1. Pick LDPlayer or MuMu, then Run Checks.\n"
            "2. Fix required ADB failures before START.\n"
            "3. Choose Showdown Trio mode and a performance profile.\n"
            "4. Press START (single-instance) or use Instances tab (multi-instance).",
            "1. Выберите LDPlayer или MuMu, затем Запустить проверки.\n"
            "2. Исправьте обязательные ошибки ADB перед СТАРТ.\n"
            "3. Выберите режим Showdown Trio и профиль производительности.\n"
            "4. Нажмите СТАРТ (один экземпляр) или вкладку Экземпляры (мульти).",
        ),
    },
    "farmPlan": {
        "title": ("Farm Plan", "План фарма"),
        "tab": ("Farm Plan", "План фарма"),
        "summary": (
            "1. Add brawlers or use Build Queue (Push All).\n"
            "2. Drag rows to reorder; first brawler is active.\n"
            "3. Import/Export JSON for backup.\n"
            "4. Leave empty to use the legacy picker after START.",
            "1. Добавьте бойцов или Build Queue (Push All).\n"
            "2. Перетаскивайте строки; первый боец активен.\n"
            "3. Импорт/экспорт JSON для резервной копии.\n"
            "4. Оставьте пустым для классического выбора после СТАРТ.",
        ),
    },
    "multiInstance": {
        "title": ("Multi-Instance", "Несколько экземпляров"),
        "tab": ("Instances", "Экземпляры"),
        "summary": (
            "1. Enable Multi-Instance on the Instances tab and follow the quick setup panel.\n"
            "2. Scan emulators and Quick add unassigned instances (or use Manual Add).\n"
            "3. Set each instance farm plan from the Farm Plan tab instance selector.\n"
            "4. Start all ready, then Align windows. Use Overview START only in single-instance mode.",
            "1. Включите мульти-экземпляр на вкладке Экземпляры.\n"
            "2. Сканируйте эмуляторы и быстро добавьте экземпляры.\n"
            "3. Настройте план фарма для каждого экземпляра.\n"
            "4. Запустите готовые, затем Выровнять окна. СТАРТ на Обзоре только в одиночном режиме.",
        ),
    },
    "settings": {
        "title": ("Settings and Performance", "Настройки и производительность"),
        "tab": ("Settings", "Настройки"),
        "summary": (
            "1. Accept the free-use license in About.\n"
            "2. Tune performance profile and debug options.\n"
            "3. Spacing Aggression purple circle = target hug distance in Debug Screen.\n"
            "4. After Round controls lobby return vs Play Again on wins.",
            "1. Примите лицензию в разделе О программе.\n"
            "2. Настройте профиль и отладку.\n"
            "3. Фиолетовый круг Spacing Aggression — целевая дистанция в Debug Screen.\n"
            "4. После раунда: лобби или Играть снова при победах.",
        ),
    },
    "discord": {
        "title": ("Discord Notifications", "Уведомления Discord"),
        "tab": ("Discord", "Discord"),
        "summary": (
            "1. Webhook URL + Send Match Summary posts a report after each game.\n"
            "2. Ping Every X Matches mentions you on match summaries (optional).\n"
            "3. Heartbeat Every X Minutes is optional; leave at 0 to avoid status spam.\n"
            "4. Remote slash commands need a bot token (separate from webhooks).",
            "1. Webhook URL + Send Match Summary — отчёт после каждой игры.\n"
            "2. Ping Every X Matches — упоминание в сводках (опционально).\n"
            "3. Heartbeat Every X Minutes — опционально; 0 отключает спам.\n"
            "4. Удалённые команды требуют токен бота (отдельно от webhook).",
        ),
    },
    "telegram": {
        "title": ("Telegram Control", "Управление Telegram"),
        "tab": ("Telegram", "Telegram"),
        "summary": (
            "1. Create a bot with @BotFather and paste the token.\n"
            "2. Send /setup to the bot once to register your chat.\n"
            "3. Use /status, /pause, /push, and other commands remotely.\n"
            "4. Keep notification chat IDs private.",
            "1. Создайте бота через @BotFather и вставьте токен.\n"
            "2. Отправьте /setup боту один раз.\n"
            "3. Используйте /status, /pause, /push и другие команды.\n"
            "4. Не публикуйте chat ID уведомлений.",
        ),
    },
    "api": {
        "title": ("Brawl Stars API", "API Brawl Stars"),
        "tab": ("API", "API"),
        "summary": (
            "1. Create a developer account at developer.brawlstars.com.\n"
            "2. Fill player tag and credentials in the API tab.\n"
            "3. Enables trophy autofill and Push All queue building.\n"
            "4. Never commit filled API tokens to GitHub.",
            "1. Создайте аккаунт на developer.brawlstars.com.\n"
            "2. Заполните тег и данные на вкладке API.\n"
            "3. Автозаполнение кубков и Push All.\n"
            "4. Не коммитьте токены API в GitHub.",
        ),
    },
    "timers": {
        "title": ("Timers and Recovery", "Таймеры и восстановление"),
        "tab": ("Timers", "Таймеры"),
        "summary": (
            "1. Low IPS recovery restarts scrcpy, game, or emulator.\n"
            "2. Adjust thresholds if recovery triggers too often.\n"
            "3. Emulator restart cooldown prevents rapid loops.\n"
            "4. Check Recovery Log on Overview for recent events.",
            "1. Низкий IPS перезапускает scrcpy, игру или эмулятор.\n"
            "2. Настройте пороги при частых срабатываниях.\n"
            "3. Кулдаун перезапуска эмулятора предотвращает циклы.\n"
            "4. Журнал восстановления на вкладке Обзор.",
        ),
    },
    "matchHistory": {
        "title": ("Match History", "История матчей"),
        "tab": ("Match History", "История матчей"),
        "summary": (
            "1. Review recent matches and session summary.\n"
            "2. Sort by games or other columns.\n"
            "3. Reset history from the tab if needed.\n"
            "4. Discord /stats mirrors live session stats.",
            "1. Просмотр последних матчей и сводки сессии.\n"
            "2. Сортировка по играм и другим столбцам.\n"
            "3. Сброс истории с вкладки при необходимости.\n"
            "4. Discord /stats отражает статистику сессии.",
        ),
    },
    "remoteControl": {
        "title": ("Remote Commands", "Удалённые команды"),
        "tab": ("Help", "Справка"),
        "summary": (
            "Discord: /pause, /start, /status, /queue, /push, /skip, /remove, /target, /screenshot.\n"
            "Telegram: /pause, /resume, /status, /queue, /push, /skip, /remove, /target, /screenshot.\n"
            "Multi-instance: add instance:ld-2 (Discord) or a third argument (Telegram).",
            "Discord: /pause, /start, /status, /queue, /push, /skip, /remove, /target, /screenshot.\n"
            "Telegram: /pause, /resume, /status, /queue, /push, /skip, /remove, /target, /screenshot.\n"
            "Мульти-экземпляр: instance:ld-2 (Discord) или третий аргумент (Telegram).",
        ),
    },
    "troubleshooting": {
        "title": ("Troubleshooting", "Устранение неполадок"),
        "tab": ("Help", "Справка"),
        "summary": (
            "1. Run Checks on Overview for ADB/emulator issues.\n"
            "2. Run python tools/performance_check.py for IPS/GPU.\n"
            "3. Dual ADB devices: reconnect emulator ADB debugging.\n"
            "4. Read logs/recovery_events.jsonl for auto-recovery details.",
            "1. Запустите проверки на Обзоре при проблемах ADB/эмулятора.\n"
            "2. python tools/performance_check.py для IPS/GPU.\n"
            "3. Два ADB: переподключите отладку эмулятора.\n"
            "4. См. logs/recovery_events.jsonl для авто-восстановления.",
        ),
    },
}

for topic_id, fields in _TUTORIAL_TOPICS.items():
    _HUB_UI_EN[f"tutorial.{topic_id}.title"] = fields["title"][0]
    _HUB_UI_EN[f"tutorial.{topic_id}.tab"] = fields["tab"][0]
    _HUB_UI_EN[f"tutorial.{topic_id}.summary"] = fields["summary"][0]
    _HUB_UI_RU[f"tutorial.{topic_id}.title"] = fields["title"][1]
    _HUB_UI_RU[f"tutorial.{topic_id}.tab"] = fields["tab"][1]
    _HUB_UI_RU[f"tutorial.{topic_id}.summary"] = fields["summary"][1]

_deep_merge(EN_CATALOG, _nest_flat(_HUB_UI_EN))
_deep_merge(RU_CATALOG, _nest_flat(_HUB_UI_RU))
