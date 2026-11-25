---
name: image-prompt-library
description: Apply reusable visual prompts to stylize photos or prepare the prompt for a requested style. Use when the user invokes $image-prompt-library or asks for the library's Abstract Poster, Fashion Portrait, or Big-Eyed Creature style.
---

# Image Prompt Library

## Каталог стилей

| Стиль | Что делает |
| --- | --- |
| [Abstract Poster](references/abstract-poster.json) | Превращает фотографию в горизонтальный абстрактный постер с геометрическими формами и фактурой печати. |
| [Fashion Portrait](references/fashion-portrait.txt) | Превращает фотографию человека в свободный маркерный fashion-скетч с узнаваемым лицом. |
| [Big-Eyed Creature](references/big-eyed-creature.md) | Превращает человека в большеглазого персонажа, нарисованного восковыми мелками, с заданным взглядом и выражением лица. |

## Применение

1. Определи стиль по названию или описанию и открой его файл. По запросу каталога покажи список стилей. Если пользователь хочет применить скилл и стиль неясен, предложи выбрать из каталога.
2. Для Big-Eyed Creature уточни направление взгляда и выражение лица по правилам в файле промпта. Собери промпт после того, как известны оба параметра.
3. Если пользователь просит промпт, верни готовый промпт в его формате без запуска генерации. Для создания изображения передай промпт и исходную фотографию в доступный инструмент генерации. Если фотографии нет, попроси приложить её в том же сообщении, что и нужные уточнения о стиле.
