<div align="center">

# Cloud Code

**Бесплатный AI-разработчик для твоих проектов.**
Пиши задачу словами — получай код и изменения прямо в файлах.

[![Python](https://img.shields.io/badge/Python-3.10+-000000?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![opencode](https://img.shields.io/badge/powered%20by-opencode-000000?style=for-the-badge)](https://opencode.ai)
[![License](https://img.shields.io/badge/license-MIT-000000?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Windows%20%7C%20macOS-000000?style=for-the-badge)](#установка)

<br>

<img src="docs/banner.png" alt="Cloud Code by m3lf1x" width="100%">

<br>

**by m3lf1x**

</div>

---

## Что это

Cloud Code — десктопное приложение с интерфейсом в стиле Claude Code, которое работает поверх [opencode](https://opencode.ai) и бесплатных моделей. Ни ключей API, ни подписки: ставишь, выбираешь папку проекта и ставишь задачу обычным языком.

Интерфейс написан на HTML и открывается в окне Python через `pywebview`. Всё в одном файле.

## Скриншоты

<p align="center">
  <img src="docs/screenshot.png" alt="Чат с агентом" width="100%">
  <br><sub><b>Чат.</b> Потоковые ответы, подсветка кода и кнопка «копировать».</sub>
</p>

<p align="center">
  <img src="docs/files.png" alt="Файлы проекта" width="100%">
  <br><sub><b>Файлы.</b> Дерево проекта и просмотр кода с подсветкой.</sub>
</p>

<p align="center">
  <img src="docs/diff.png" alt="Изменения" width="100%">
  <br><sub><b>Изменения.</b> Цветной diff из git по каждому файлу.</sub>
</p>

## Возможности

- **Бесплатно.** Автоматически выбирается бесплатная модель opencode. Свои провайдеры подключаются через `opencode auth login`.
- **Работает с твоим проектом.** Агент читает и правит файлы в выбранной папке.
- **Потоковые ответы.** Текст печатается по мере генерации, есть таймер и кнопка «Стоп».
- **Чаты с контекстом.** История сохраняется, поиск по чатам, диалог можно продолжить после перезапуска.
- **Файлы проекта.** Дерево файлов, просмотр с подсветкой синтаксиса, упоминание файла в чате через `@`.
- **Изменения.** Список изменённых файлов из git и цветной diff.
- **Markdown и код.** Заголовки, списки, блоки кода с подсветкой и кнопкой «копировать».
- **Быстрые команды.** Набери `/` в поле ввода: `/объясни`, `/ошибки`, `/ревью`, `/тесты`, `/рефактор`, `/readme`, `/коммит`, `/план`.
- **Режим «план».** Агент только анализирует проект и ничего не меняет в файлах. Переключается кнопкой над полем ввода.
- **Повторить ответ**, время генерации под каждым ответом, **экспорт чата в Markdown**.
- **Проверка обновлений.** Программа сама сообщит о новой версии.
- **Тёмная и светлая тема**, горячие клавиши, сворачиваемая панель.

## Установка

### Готовая сборка (Windows)

1. Установи [Node.js](https://nodejs.org) и opencode:
   ```bash
   npm i -g opencode-ai
   ```
2. Скачай `CloudCode.exe` на странице [Releases](https://github.com/m3lf1x/Cloud-code/releases/latest).
3. Запусти. Если окно не открывается, установи [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).

### Готовая сборка (macOS)

1. Установи opencode одной из команд:
   ```bash
   curl -fsSL https://opencode.ai/install | bash
   # или
   npm i -g opencode-ai
   ```
2. Скачай `CloudCode-macOS.zip` на странице [Releases](https://github.com/m3lf1x/Cloud-code/releases/latest), распакуй и перетащи `Cloud Code.app` в «Программы».
3. При первом запуске нажми на приложение правой кнопкой → **Открыть** (приложение не подписано Apple). Если macOS пишет, что файл повреждён, выполни:
   ```bash
   xattr -cr "/Applications/Cloud Code.app"
   ```

### Из исходников

```bash
git clone https://github.com/m3lf1x/Cloud-code.git
cd Cloud-code
pip install pywebview
npm i -g opencode-ai
python main.py      # на macOS: python3 main.py
```

## Использование

1. Нажми **«Выбрать папку»** и укажи свой проект.
2. Напиши задачу, например: *«Создай лендинг для кофейни: тёмная тема, меню и форма заказа»*.
3. Смотри, как агент работает, во вкладках **Файлы** и **Изменения**.

### Горячие клавиши

| Клавиша | Действие |
| --- | --- |
| `Enter` | Отправить сообщение |
| `Shift + Enter` | Новая строка |
| `Esc` | Остановить ответ |
| `/` | Быстрые команды |
| `Ctrl + K` (`Cmd + K` на Mac) | Новый чат |
| `Ctrl + B` (`Cmd + B` на Mac) | Свернуть боковую панель |
| `Ctrl + 1 / 2 / 3` | Чат / Файлы / Изменения |

## Как это работает

```
Интерфейс (HTML/CSS/JS)  ←→  pywebview  ←→  Python  ←→  opencode run  ←→  модель
```

Каждое сообщение уходит в `opencode run` в выбранной папке. Контекст диалога и текст запроса передаются через stdin, ответ читается потоком и показывается в интерфейсе. Чаты и настройки хранятся в `~/.cloud_code`.

## Частые вопросы

**opencode не найден.** Установи его (`npm i -g opencode-ai`) и перезапусти приложение. Программа ищет его в `PATH` и в стандартных папках (npm, Homebrew, `~/.opencode/bin`). На macOS дополнительно используется `PATH` твоего терминала.

**Failed to load Python DLL ... `_internal\python310.dll`.** exe собран как папка (без `--onefile`) и запущен без папки `_internal`, либо антивирус удалил DLL. Скачай готовый `CloudCode.exe` из [Releases](https://github.com/m3lf1x/Cloud-code/releases/latest) или собери заново через `build_win.bat`. Если запускаешь собранную папку целиком, не переноси `CloudCode.exe` отдельно от `_internal`. Если не помогло, установи [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) и проверь карантин антивируса.

**«Порядковый номер 380 не найден в библиотеке DLL ...CloudCode.exe».** Это вторичная ошибка: при старте exe произошла настоящая ошибка, а окно с её описанием само упало ([баг PyInstaller](https://github.com/pyinstaller/pyinstaller/issues/6223)). В версии 1.1.1 ошибки показываются обычным окном и пишутся в `~/.cloud_code/error.log`. Чтобы увидеть причину у старой сборки, запусти `python main.py` из папки с проектом или собери отладочную версию: `build_win.bat debug` (запускай `dist\CloudCodeDebug.exe` из `cmd`, там виден traceback). Чаще всего причина в том, что `pywebview` собран в Python без `pythonnet` (используй Python 3.11 или 3.12) или не установлен [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/).

**Пустой ответ.** Нажми кнопку обновления рядом с полем модели и выбери рабочую бесплатную модель. Проверь интернет.

**Где хранятся чаты.** В папке `.cloud_code` в твоей домашней директории (`chats.json`, `config.json`).

## История версий

**1.1.1**
- быстрые команды через `/`
- режим «план» (только чтение)
- повторить ответ, время генерации, экспорт чата в Markdown
- кнопка «Открыть папку проекта»
- проверка обновлений
- сборка Windows одним файлом через `build_win.bat`
- понятное окно ошибки при сбое запуска и лог `~/.cloud_code/error.log`
- `build_win.bat debug` для отладочной сборки с консолью

**1.0.0** — первый релиз.

## Дисклеймер

Cloud Code — независимый open source проект. Он не связан с Anthropic и не является их продуктом. Название отсылает к идее и не означает аффилированности.

## Лицензия

MIT. Делай что хочешь, оставь авторство.

---

<div align="center">

**Cloud Code by m3lf1x**

Если проект полезен, поставь звезду.

</div>
