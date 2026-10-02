# ipynb-skill

`ipynb-skill` помогает coding assistants читать, анализировать, создавать и
безопасно редактировать Jupyter notebook-файлы `.ipynb` без ручной работы с
большим JSON. CLI-инструмент `ipynb-tool` умеет:

- выводить код, markdown, outputs, ошибки, оглавление и краткую сводку;
- извлекать изображения из cell outputs;
- атомарно заменять, добавлять, удалять и перемещать ячейки;
- экспортировать notebook в Jupytext-совместимый `py:percent` и импортировать
  его обратно с проверкой исходной версии notebook;
- создавать новый Python 3 notebook из percent-файла.

## Установка

Если coding assistant поддерживает установку skills из GitHub URL:

```text
https://github.com/shwars/shwarsico-skills/tree/main/ipynb-skill
```

Если assistant принимает отдельно репозиторий и путь:

```text
repo: shwars/shwarsico-skills
path: ipynb-skill
```

При ручной установке скопируйте папку `ipynb-skill` в директорию skills вашего
assistant. Для запуска CLI нужен `uv`; он установит локальный пакет и его
зависимости `jupytext` и `nbformat`:

```bash
cd ipynb-skill
uv run ipynb-tool --summary --toc path/to/notebook.ipynb
```

## Исследование notebook

Получить краткую карту и стабильные ID ячеек:

```bash
uv run ipynb-tool --summary --toc --cell-ids notebook.ipynb
```

Вывести только Python-код:

```bash
uv run ipynb-tool --code notebook.ipynb
```

Вывести код и markdown как читаемый Python-файл:

```bash
uv run ipynb-tool --code --markdown --comments --noxml notebook.ipynb
```

Найти ячейки и захватить соседний контекст:

```bash
uv run ipynb-tool --search "train|model|error" --around 1 notebook.ipynb
```

Показать ячейки с ошибками или извлечь изображения:

```bash
uv run ipynb-tool --errors notebook.ipynb
uv run ipynb-tool --images files --image-dir extracted notebook.ipynb
```

Существующие inspection-аргументы остаются совместимыми с предыдущей версией.

## Небольшие изменения

Editing-команды по умолчанию только показывают semantic diff и не меняют файл.
После проверки preview повторите команду с `--write`.

Заменить source ячейки по 1-based индексу или ID:

```bash
uv run ipynb-tool replace-cell notebook.ipynb id:setup --source-file setup.py
uv run ipynb-tool replace-cell notebook.ipynb id:setup --source-file setup.py --write
```

Вместо `--source-file PATH` можно передать source через `--stdin`.

Добавить ячейку:

```bash
uv run ipynb-tool insert-cell notebook.ipynb \
  --type markdown --after 3 --source-file note.md
```

Позиция задается ровно одним аргументом: `--before CELL`, `--after CELL`,
`--at-start` или `--at-end`. Поддерживаются типы `code`, `markdown` и `raw`.

Удалить или переместить несколько ячеек:

```bash
uv run ipynb-tool delete-cells notebook.ipynb --cells 5,8-10
uv run ipynb-tool move-cells notebook.ipynb --cells 4-6 --before id:results
```

`--cells` принимает индексы, диапазоны и `id:<cell-id>`. Повторные selectors
считаются ошибкой. При перемещении относительный порядок выбранных ячеек
сохраняется.

## Масштабное редактирование

Экспортируйте transient percent-файл, отредактируйте его как обычный `.py`,
затем импортируйте:

```bash
uv run ipynb-tool export-percent notebook.ipynb --output notebook.edit.py

# edit notebook.edit.py

uv run ipynb-tool import-percent notebook.edit.py notebook.ipynb
uv run ipynb-tool import-percent notebook.edit.py notebook.ipynb --write
```

Percent-файл содержит служебный hash исходного notebook и cell handles. При
импорте инструмент:

- откажется применять edit buffer, если исходный `.ipynb` изменился;
- сохранит metadata, attachments, outputs и execution count неизмененных или
  перемещенных ячеек;
- очистит outputs и execution count любой измененной code cell;
- потребует `--allow-delete`, если из edit buffer исчезли существующие ячейки;
- удалит служебные поля из итогового notebook.

Экспорт не перезаписывает существующий `.py` без `--force`. Это transient edit
buffer: команда не включает Jupytext pairing и автоматическую синхронизацию.

## Создание notebook

Обычный `py:percent` без служебного export header можно импортировать в новый
файл:

```python
# %% [markdown]
# # New notebook

# %%
answer = 42
```

```bash
uv run ipynb-tool import-percent lesson.py lesson.ipynb
uv run ipynb-tool import-percent lesson.py lesson.ipynb --write
```

Новый notebook получает nbformat 4, minor version 5, уникальные cell IDs и стандартные
`Python 3`/`python3` kernel metadata. Все code cells создаются без outputs и с
`execution_count = null`.

## Модель безопасности

- Любое изменение `.ipynb` сначала строится в памяти и валидируется через
  `nbformat`.
- `--write` сохраняет notebook через временный файл в той же директории и
  атомарный replace.
- Перед replace повторно проверяется hash исходного файла; concurrent change
  отменяет запись.
- No-op edit не переписывает файл и не меняет его байты или mtime.
- Команды не выполняют notebook и не позволяют напрямую редактировать output
  MIME bundles или metadata.

## Inspection-аргументы

| Аргумент | Назначение |
| --- | --- |
| `--code`, `--markdown`, `--output`, `--all` | Выбор содержимого для вывода. |
| `--xml`, `--noxml`, `--comments` | Формат представления. |
| `--summary`, `--toc`, `--cell-ids` | Карта notebook, заголовки и cell IDs. |
| `--cells 1,3,8-12` | Фильтр по 1-based индексам. |
| `--search PATTERN`, `--around N` | Regex-поиск и соседние ячейки. |
| `--errors`, `--execution`, `--metadata` | Ошибки, порядок выполнения и metadata. |
| `--max-chars N`, `--no-truncate` | Ограничение длинных блоков. |
| `--images skip|base64|files`, `--image-dir DIR` | Обработка изображений. |

Если content selector не указан, инструмент печатает только запрошенные
exploration-разделы. `--images files` может извлекать изображения без stdout.

## Тестирование

```bash
uv run python -m unittest discover -s tests -v
```

Разовая проверка без project lockfile:

```bash
uv run --no-project --with-editable . python -m unittest discover -s tests -v
```

Тесты покрывают старый inspection CLI, cell IDs, preview/write, index/ID
selectors, очистку stale outputs, структурные операции, percent round trip,
stale-base detection, guarded deletion и создание notebook.
