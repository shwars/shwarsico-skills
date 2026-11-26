"""Locate editorial signals in Russian textbook prose. Read-only, standard library."""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path


BASELINES = Path(__file__).resolve().parents[1] / "references" / "rhythm.json"
WORD = re.compile(r"[^\W_]+(?:[-‑][^\W_]+)*", re.UNICODE)
SENTENCE_END = re.compile(r"""(?<=[.!?…])(?:[»”"')\]]*)(?:\s+|$)""")
ABBREVIATION = re.compile(
    r"(?i)\b(?:т\.\s*[едпкнч]\.|и\s+т\.\s*(?:д|п)\.|"
    r"(?:см|рис|гл|ср|стр|табл|напр|им|др)\.(?=\s+\S))"
)
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
TEX_ENV = re.compile(r"\\begin\{([A-Za-z]+\*?)\}")
HIDDEN_ENVS = {
    "code", "verbatim", "Verbatim", "lstlisting", "minted", "alltt",
    "equation", "align", "gather", "multline", "displaymath", "math",
    "eqnarray", "array", "figure", "table", "tabular", "thebibliography",
}
TEX_ARG = r"\{(?:[^{}]|\{[^{}]*\})*\}"
TEX_CODE = re.compile(
    r"\\(?:cd|pred|texttt|url|path|cite\w*|ref|eqref|pageref|rf|label|index|"
    r"input|include|includegraphics|verb\*?)(?![A-Za-z])(?:\[[^\]]*\])?"
    + TEX_ARG
)
TEX_WRAPPER = re.compile(
    r"\\(?:emph|textit|textbf|df|m|q|engl|text|footnote)\{([^{}]*)\}"
)
HEADING = re.compile(r"^\s*#{1,6}(?:[ \t]|$)|^\s*<(?:h[1-6])\b", re.IGNORECASE)
TEX_HEADING = re.compile(r"\\(?:chapter|(?:sub)*section|paragraph|chapabstract)\*?\{")
LIST_ITEM = re.compile(r"^\s{0,3}(?:[-+*]|\d{1,4}[.)])\s+")
INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)")
INLINE_MATH = re.compile(r"(?<![\\$])\$(?!\$)(?:\\.|[^$\\\n])+\$(?!\$)|\\\(.*?\\\)")
MD_LINK = re.compile(r"(!?)\[([^\[\]]*)\](?:\((?:[^()]|\([^()]*\))*\)|\[[^\]]*\])")
TRANSITION = re.compile(
    r"^(?:рассмотрим(?: теперь)?|попробуем|посмотрим|заметим|отметим|"
    r"следует отметить|важно (?:отметить|понимать)|стоит отметить|"
    r"таким образом|при этом|кроме того|более того|в целом|итак|"
    r"как видно|обратим внимание)\b"
)

# The expressions nominate passages for reading. Even a strong match may be quoted.
SIGNALS = {
    "chat_wrapper": (
        "Прочитайте фразу как часть рукописи. Проверьте, принадлежит ли она диалогу с ассистентом.",
        r"отличный вопрос|надеюсь,? (?:это )?поможет|дайте знать,? если|"
        r"хотите,? чтобы я|(?:вот|ниже) (?:ваш|запрошенный) (?:текст|черновик|вариант)|"
        r"по состоянию на дату моего последнего обновления",
    ),
    "generic_opening": (
        "Укажите задачу, условие или наблюдение, если зачин подойдёт к другой теме без изменений.",
        r"в современном мире|в эпоху (?:стремительных|цифровых) (?:перемен|изменений|технологий)|"
        r"давайте (?:погрузимся|разбер[её]мся)|погрузимся в (?:мир|тему)|"
        r"открывает новые горизонты",
    ),
    "rhetorical_contrast": (
        "Проверьте, имеет ли противопоставление проверяемое техническое содержание.",
        r"не просто\b[^.!?…]{0,110}?(?:,\s*(?:а|но)\b|[—–])|"
        r"не столько\b[^.!?…]{0,110}?,\s*сколько\b",
    ),
    "unsupported_emphasis": (
        "Найдите основание оценки в тексте или сформулируйте конкретное свойство.",
        r"играет ключевую роль|выходит на новый уровень|революционн\w+|"
        r"беспрецедентн\w+|эксперты (?:считают|утверждают)|"
        r"исследования показывают",
    ),
    "stock_ending": (
        "Проверьте, какую новую мысль добавляет фраза к предыдущему объяснению.",
        r"вот (?:в ч[её]м|где) (?:настоящая|главная) (?:ценность|сила|магия)|"
        r"и это только начало|подводя итог,? можно сказать",
    ),
}
PATTERNS = [(kind, reason, re.compile(r"(?<!\w)(?:" + pattern + r")(?!\w)", re.IGNORECASE))
            for kind, (reason, pattern) in SIGNALS.items()]


def redact(match):
    return " " * len(match[0])


def strip_blocks(text, form):
    """Blank non-prose blocks while preserving input line numbers."""
    lines = text.splitlines()
    if form == "markdown" and lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in {"---", "..."}:
                lines[:i + 1] = [""] * (i + 1)
                break

    block_end = None
    comment = False
    for number, line in enumerate(lines, 1):
        if block_end:
            if block_end.search(line):
                block_end = None
            yield number, ""
            continue
        if comment:
            _, end, line = line.partition("-->")
            if not end:
                yield number, ""
                continue
            comment = False

        clean = line.strip()
        fence = FENCE.match(line) if form == "markdown" else None
        if fence:
            marker = fence[1]
            block_end = re.compile(r"^ {0,3}" + re.escape(marker[0]) + "{%d,}\\s*$" % len(marker))
        elif clean.startswith("$$") and clean.find("$$", 2) < 0:
            block_end = re.compile(r"(?<!\\)\$\$")
        elif clean.startswith(r"\[") and r"\]" not in clean:
            block_end = re.compile(r"\\\]")
        elif form == "tex":
            line = re.split(r"(?<!\\)%", line, maxsplit=1)[0]
            env = TEX_ENV.match(line.lstrip())
            if env and env[1].rstrip("*") in HIDDEN_ENVS:
                end = r"\end{" + env[1] + "}"
                if end not in line:
                    block_end = re.compile(re.escape(end))
                line = ""
        if block_end or clean.startswith(("$$", r"\[")):
            line = ""
        elif form == "markdown":
            line = INLINE_CODE.sub(redact, line)
            line = re.sub(r"<!--.*?-->", redact, line)
            if "<!--" in line:
                line = line.split("<!--", 1)[0]
                comment = True
        yield number, line


def paragraphs(text, form):
    prose = []
    current = []
    for number, line in strip_blocks(text, form):
        item = LIST_ITEM.match(line) if form != "tex" else re.match(r"^\s*\\item\b\s*", line)
        if item:
            line = line[item.end():]
        if form == "markdown":
            if HEADING.match(line) or re.match(r"^\s*>|^\s{0,3}\[[^]]+\]:", line):
                line = ""
            line = INLINE_MATH.sub(redact, line)
            line = MD_LINK.sub(lambda m: redact(m) if m[1] else m[2], line)
            line = re.sub(r"</?[a-zA-Z][\w-]*(?:\s+[^<>\n]*)?\s*/?>|https?://\S+", redact, line)
            line = re.sub(r"(?<!\w)[*_~]{1,3}|[*_~]{1,3}(?!\w)", "", line)
        if form == "tex":
            if TEX_HEADING.match(line.lstrip()) or re.match(r"\s*\\(?:begin|end)\{", line):
                line = ""
            line = re.sub(r"\\verb\*?([^\w\s]).*?\1", redact, line)
            line = TEX_CODE.sub(redact, line)
            line = TEX_WRAPPER.sub(r"\1", line)
            line = INLINE_MATH.sub(redact, line)
            line = re.sub(r"\\[A-Za-z]+\*?", "", line).replace("~", " ")
        line = INLINE_MATH.sub(redact, line).strip()
        if (item or not line) and current:
            prose.append(current)
            current = []
        if line and WORD.search(line):
            current.append((number, line))
    if current:
        prose.append(current)
    return prose


def sentences(text):
    masked = ABBREVIATION.sub(lambda m: m[0].replace(".", "·"), text)
    lengths = (len(WORD.findall(part)) for part in SENTENCE_END.split(masked))
    return [length for length in lengths if length]


def candidate(kind, first, last, excerpt, reason):
    return {"kind": kind, "lines": [first, last], "excerpt": excerpt[:200], "review": reason}


def read_signals(prose):
    found = []
    beginnings = []
    for parts in prose:
        first, last = parts[0][0], parts[-1][0]
        text = re.sub(r"\s+", " ", " ".join(part for _, part in parts))
        normalized = text.casefold().replace("ё", "е").lstrip('«„“"')
        marker = TRANSITION.match(normalized)
        words = WORD.findall(normalized)[:2]
        opening = " ".join(words) if len(words) == 2 and all(word[0].isalpha() for word in words) else ""
        beginnings.append((first, last, opening, marker[0] if marker else ""))
        # Map cross-line matches to their real source range, including wrapped prose.
        offsets = []
        start = 0
        for number, part in parts:
            end = start + len(re.sub(r"\s+", " ", part))
            offsets.append((end, number))
            start = end + 1
        for kind, reason, pattern in PATTERNS:
            for match in pattern.finditer(text):
                a = next(number for end, number in offsets if match.start() < end)
                b = next(number for end, number in offsets if match.end() <= end)
                found.append(candidate(kind, a, b, match[0], reason))

    cluster_until = -1
    for i, (first, last, beginning, marker) in enumerate(beginnings):
        if i and beginning and beginning == beginnings[i - 1][2]:
            found.append(candidate("repeated_opening", beginnings[i - 1][0], last, beginning,
                                   "Сопоставьте соседние зачины и проверьте, зачем повторяется формулировка."))
        if marker and i > cluster_until:
            cluster = [(j, entry) for j, entry in enumerate(beginnings[i:i + 4], i) if entry[3]]
            if len(cluster) >= 3:
                cluster_until = cluster[-1][0]
                positions = ", ".join(f"{entry[0]}: {entry[3]}" for _, entry in cluster)
                found.append(candidate("transition_cluster", first, cluster[-1][1][1], positions,
                                       "Проверьте функцию каждого перехода и повтор одного способа начать абзац."))
    return sorted(found, key=lambda hit: (hit["lines"], hit["kind"]))


def describe(observations, baseline, minimum):
    values = sorted(size for size, _ in observations)
    if not values:
        return {"count": 0, "status": "no_prose"}
    median = statistics.median(values)
    stats = {"count": len(values), "median_words": median, "min_words": values[0], "max_words": values[-1]}
    if baseline is None or len(values) < minimum:
        stats["status"] = "no_baseline" if baseline is None else "short_sample"
        return stats
    stats["reference_medians"] = baseline
    stats["status"] = "within_reference" if baseline[0] <= median <= baseline[1] else "reread"
    if stats["status"] == "reread":
        ordered = sorted(observations, key=lambda item: item[0], reverse=median > baseline[1])
        stats["review_examples"] = [{"words": size, "lines": lines} for size, lines in ordered[:3]]
    return stats


def analyze(text, form, register, baselines):
    prose = paragraphs(text, form)
    paragraph_lengths = []
    sentence_lengths = []
    for parts in prose:
        text = " ".join(line for _, line in parts)
        span = [parts[0][0], parts[-1][0]]
        paragraph_lengths.append((len(WORD.findall(text)), span))
        sentence_lengths.extend((length, span) for length in sentences(text))
    baseline = baselines.get(register, {})
    return {
        "register": register,
        "words": sum(length for length, _ in paragraph_lengths),
        "sentences": describe(sentence_lengths, baseline.get("sentences"), 25),
        "paragraphs": describe(paragraph_lengths, baseline.get("paragraphs"), 12),
        "signals": read_signals(prose),
    }


def main():
    parser = argparse.ArgumentParser(description="Ищет места для вычитки русскоязычного учебного текста.")
    parser.add_argument("input", help="Путь к файлу или - для stdin.")
    parser.add_argument("--format", choices=["text", "markdown", "tex"])
    parser.add_argument("--encoding", choices=["utf-8", "cp1251"], default="utf-8")
    parser.add_argument("--register", choices=["practical", "theoretical", "mixed"], default="mixed")
    args = parser.parse_args()
    form = args.format or {".md": "markdown", ".markdown": "markdown", ".tex": "tex"}.get(
        Path(args.input).suffix.lower(), "text"
    )
    try:
        data = sys.stdin.buffer.read() if args.input == "-" else Path(args.input).read_bytes()
        text = data.decode("utf-8-sig" if args.encoding == "utf-8" else "cp1251")
        baselines = json.loads(BASELINES.read_text(encoding="utf-8"))["ranges"]
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f"Проверка не выполнена: {exc}\n")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(analyze(text, form, args.register, baselines), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
