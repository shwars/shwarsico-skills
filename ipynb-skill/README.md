# ipynb-skill

`ipynb-skill` помогает coding assistants читать и анализировать Jupyter notebook-файлы `.ipynb` без ручного разбора большого JSON. Внутри skill есть
CLI-инструмент `ipynb-tool`, который выводит код, markdown, outputs, ошибки,
оглавление, краткую сводку notebook и при необходимости извлекает изображения
из cell outputs.

Skill особенно полезен, когда ассистенту нужно быстро понять структуру
notebook, найти релевантные ячейки, посмотреть traceback, извлечь только Python
код или сохранить изображения из результатов выполнения.

## Установка

Если ваш coding assistant поддерживает установку skills из GitHub URL,
используйте:

```text
https://github.com/shwars/shwarsico-skills/tree/main/ipynb-skill
```

Если assistant принимает отдельно репозиторий и путь внутри него:

```text
repo: shwars/shwarsico-skills
path: ipynb-skill
```

Если автоматической установки нет, скопируйте папку `ipynb-skill` в директорию
пользовательских skills/инструкций вашего assistant и убедитесь, что он видит
файл `SKILL.md`.

## Работа через uv

Для запуска CLI нужен `uv`. Команды выполняются из папки `ipynb-skill`:

```bash
cd ipynb-skill
uv run ipynb-tool --summary --toc path/to/notebook.ipynb
```

Пакет объявляет console script `ipynb-tool` в `pyproject.toml`, поэтому `uv run`
установит локальный пакет в окружение запуска и выполнит инструмент.

## Базовые сценарии

Получить краткую карту notebook:

```bash
uv run ipynb-tool --summary --toc notebook.ipynb
```

Вывести только Python-код:

```bash
uv run ipynb-tool --code notebook.ipynb
```

Вывести код и markdown так, чтобы результат было удобно читать как Python-файл:

```bash
uv run ipynb-tool --code --markdown --comments --noxml notebook.ipynb
```

Посмотреть структурированный XML-подобный вывод:

```bash
uv run ipynb-tool --xml --all notebook.ipynb
```

Найти ячейки по тексту и захватить соседний контекст:

```bash
uv run ipynb-tool --search "train|model|error" --around 1 notebook.ipynb
```

Показать только ячейки с ошибками:

```bash
uv run ipynb-tool --errors notebook.ipynb
```

Извлечь изображения из outputs без вывода текста:

```bash
uv run ipynb-tool --images files --image-dir extracted notebook.ipynb
```

## Аргументы командной строки

Общий формат:

```bash
uv run ipynb-tool [options] notebook.ipynb
```

### Формат вывода

| Аргумент | Назначение |
| --- | --- |
| `--xml` | Выводит содержимое в XML-подобной структуре: `<notebook>`, `<cell>`, `<markdown>`, `<code>`, `<output>`, `<img>`. |
| `--noxml` | Выводит plain text без XML-обертки. Это поведение по умолчанию. |
| `--comments` | В plain text режиме превращает markdown и outputs в Python-комментарии. Код остается без комментариев. |

### Выбор содержимого

| Аргумент | Назначение |
| --- | --- |
| `--code` | Включить исходный код code cells. |
| `--markdown` | Включить markdown cells. |
| `--output` | Включить outputs code cells. |
| `--all` | Включить code, markdown и outputs. |

Если не указаны `--code`, `--markdown`, `--output` или `--all`, инструмент не
печатает содержимое ячеек, но exploration-аргументы вроде `--summary`, `--toc`,
`--search` и `--errors` могут вывести свою информацию.

### Навигация и исследование notebook

| Аргумент | Назначение |
| --- | --- |
| `--summary` | Краткая сводка: формат notebook, число выбранных/всех ячеек, типы ячеек, outputs, images, error cells и execution count range. |
| `--toc` | Оглавление по markdown-заголовкам с номерами ячеек. |
| `--cells 1,3,8-12` | Ограничить вывод 1-based индексами ячеек и диапазонами. |
| `--search PATTERN` | Выбрать ячейки, где source или outputs совпадают с regex pattern. Поиск регистронезависимый. |
| `--around N` | Вместе с `--search` добавить по `N` соседних ячеек вокруг найденных. |
| `--errors` | Ограничить вывод code cells с error outputs и tracebacks. |
| `--metadata` | Включить metadata notebook и ячеек. |
| `--execution` | Показать execution counts и отметить code cells, которые выглядят выполненными не по порядку. |

### Ограничение длинного вывода

| Аргумент | Назначение |
| --- | --- |
| `--max-chars N` | Максимальная длина одного source/output блока. По умолчанию `20000`. |
| `--no-truncate` | Отключить обрезку длинных source/output блоков. |

### Изображения

| Аргумент | Назначение |
| --- | --- |
| `--images skip` | Пропускать изображения в outputs. Это режим по умолчанию. |
| `--images base64` | Оставлять изображения как `data:<mime>;base64,...` ссылки. |
| `--images files` | Сохранять изображения на диск как `image-1.png`, `image-2.jpg` и т.п. |
| `--image-dir DIR` | Директория для файлов, созданных режимом `--images files`. |

Если указан только `--images files` без выбора содержимого, инструмент извлекает
изображения и ничего не печатает в stdout.

## Тестирование

Автоматические тесты запускаются из папки `ipynb-skill`:

```bash
uv run python -m unittest discover -s tests
```

Чтобы избежать создания project lockfile при разовой проверке, можно запускать
тесты так:

```bash
uv run --no-project --with-editable . python -m unittest discover -s tests
```

Тесты покрывают plain code output, комментарии для markdown, XML-вывод,
summary/toc, фильтрацию по cells/search/errors, truncation и обработку
изображений в режимах `files` и `base64`.
