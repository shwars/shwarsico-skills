---
entity_id: Софья получает письмо
title: Софья получает письмо
type: event
first_source: demo
book_ids: [demo]
aliases: []
source_kinds: [book]
tags: [wikibook, event]
event_status: occurred
date_text: Календарная дата не установлена
date_precision: unknown
date_min: null
date_max: null
sort_key: 9999-p01-ch01-0002
---

# Софья получает письмо

## Что произошло

Учебный пример. Софья получает запечатанное письмо; содержание пока неизвестно.
[[source/demo/bychapter/p01-ch01#^b0002]]

## Датировка

Год не установлен. Имя файла — `undated--Софья получает письмо.demo.md`.

<!-- wiki:generated:start -->
<!-- wiki:generated:end -->

## Структурированные факты

~~~yaml
facts:
  - fact_id: Софья получает письмо/факт-001
    subject: Софья получает письмо
    predicate: description
    value: Софья получает запечатанное письмо
    scope: canon
    evidence_type: action
    truth_status: confirmed
    sources:
      - "[[source/demo/bychapter/p01-ch01#^b0002]]"
  - fact_id: Софья получает письмо/факт-002
    subject: Софья получает письмо
    predicate: participates
    object: Софья
    role: Получатель
    scope: canon
    evidence_type: action
    truth_status: confirmed
    sources:
      - "[[source/demo/bychapter/p01-ch01#^b0002]]"
occurrences:
  - book_id: demo
    unit_id: p01-ch01
    block_id: b0002
    kind: действие
~~~
