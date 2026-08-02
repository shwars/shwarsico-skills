# SHWARSICO Skills

Встречайте набор полезных скиллов, разработанных в SHWARSICO Vibe Coding Dept!

Skills в этом репозитории - это переиспользуемые инструкции и вспомогательные инструменты для ваших кодинг-ассистентов: Codex, Claude Code, OpenCode и др.

В основном скиллы "под капотом" используют Python, с помощью пакетного менеджера `uv`. Он должен быть установлен у вас для корректной работы.

> Скиллы разработаны [Дмитрием Сошниковым](https://soshnikov.com), автором канала
[Облачный адвокат](http://t.me/shwarsico).


## Скиллы

| Skill | Краткое описание |
| --- | --- |
| [`ai-studio-skill`](ai-studio-skill/) | Builds clean Python applications for Yandex AI Studio: Responses API, tools, RAG, MCP, Code Interpreter, images, OCR, and SpeechKit. |
| [`ipynb-skill`](ipynb-skill/) | Облегчает кодинг-ассистенту анализ файлов Jupyter Notebooks `.ipynb`: обзор структуры notebook, извлечение code/markdown/output/images, поиск по ячейкам и навигация. Использует разработанный дла этого CLI-инструмент `ipynb-tool`. |

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
