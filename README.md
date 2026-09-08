# SHWARSICO Skills

Встречайте набор полезных скиллов, разработанных в SHWARSICO Vibe Coding Dept!

Skills в этом репозитории - это переиспользуемые инструкции и вспомогательные инструменты для ваших кодинг-ассистентов: Codex, Claude Code, OpenCode и др.

В основном скиллы "под капотом" используют Python, с помощью пакетного менеджера `uv`. Он должен быть установлен у вас для корректной работы.

Для рендеринга mindmap с помощью `mindmap-js-skill` нужны Node.js 20+ и npm. Зависимости устанавливаются командой `npm ci --ignore-scripts --no-audit --no-fund` из папки скилла.

> Скиллы разработаны [Дмитрием Сошниковым](https://soshnikov.com), автором канала
[Облачный адвокат](http://t.me/shwarsico).


## Скиллы

| Skill | Краткое описание |
| --- | --- |
| [`ipynb-skill`](ipynb-skill/) | Облегчает кодинг-ассистенту анализ файлов Jupyter Notebooks `.ipynb`: обзор структуры notebook, извлечение code/markdown/output/images, поиск по ячейкам и навигация. Использует разработанный дла этого CLI-инструмент `ipynb-tool`. |
| [`ai-studio-skill`](ai-studio-skill/) | Builds clean Python applications for Yandex AI Studio: Responses API, tools, RAG, MCP, Code Interpreter, images, OCR, and SpeechKit. |
| [`soshnikov-style`](soshnikov-style/) | Пишет текст в стиле Дмитрия Сошникова. Основано на его постах в блоге и контенте из телеграм-канала.|
| [`mindmap-js-skill`](mindmap-js-skill/) | Превращает текст в редактируемые mindmap на Markmap.js и создаёт интерактивный HTML-просмотр. Поддерживает offline/CDN-режимы; экспорт PNG/SVG выполняет кодинг-ассистент доступными браузерными инструментами. |

## Установка (на примере `ipynb-skill`)

Если ваш coding assistant поддерживает установку skills из GitHub URL, укажите:

```text
https://github.com/shwars/shwarsico-skills/tree/main/ipynb-skill
```

Если assistant принимает отдельно репозиторий и путь внутри него:

```text
repo: shwars/shwarsico-skills
path: ipynb-skill
```

Если автоматической установки нет, скопируйте папку нужного skill в директорию
пользовательских skills/инструкций вашего assistant и убедитесь, что он видит
файл `SKILL.md`.
