import re

CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
                   ".rs", ".cpp", ".c", ".cs", ".rb", ".php", ".swift",
                   ".kt", ".scala", ".sh", ".sql"}

# Matches common function/class boundaries across supported languages.
_CODE_BOUNDARY = re.compile(
    r'^\s*(?:'
    r'async\s+def\s+|def\s+|class\s+|'
    r'async\s+function\s+|function\s+|func\s+|'
    r'(?:public|private|protected|static)\s+[\w<>\[\],\s]+\s+\w+\s*\(|'
    r'(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?\(|'
    r'\w+\s*\([^)]*\)\s*\{'
    r')',
    re.MULTILINE
)

_LOGICAL_CODE_BOUNDARY = re.compile(
    r'^\s*(?:if |elif |else:|for |while |try:|except |finally:|with |return |'
    r'raise |yield |await |switch |case |catch |do |'
    r'const |let |var |[A-Za-z_]\w*\s*=)'
)


def _split_long_text_unit(text, max_chars):
    words = text.split()
    if not words:
        return []

    parts = []
    current = []
    current_len = 0
    for word in words:
        next_len = current_len + len(word) + (1 if current else 0)
        if next_len > max_chars and current:
            parts.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = next_len

    if current:
        parts.append(" ".join(current))
    return parts


def _split_sentences(text, max_chars):
    units = []
    for paragraph in re.split(r'\n\s*\n', text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        units.extend(s.strip() for s in re.split(r'(?<=[.!?])\s+', paragraph) if s.strip())

    parts = []
    current = []
    current_len = 0

    for unit in units:
        split_units = [unit] if len(unit) <= max_chars else _split_long_text_unit(unit, max_chars)
        for piece in split_units:
            next_len = current_len + len(piece) + (1 if current else 0)
            if next_len > max_chars and current:
                parts.append(" ".join(current))
                current = [piece]
                current_len = len(piece)
            else:
                current.append(piece)
                current_len = next_len

    if current:
        parts.append(" ".join(current))
    return parts


def _header_context(lines):
    for line in lines:
        stripped = line.strip()
        if stripped:
            if _CODE_BOUNDARY.match(line):
                return line
            return ""
    return ""


def _logical_line_groups(lines, start_line):
    groups = []
    current = []
    current_start = start_line

    for offset, line in enumerate(lines):
        line_no = start_line + offset
        stripped = line.strip()

        if not stripped:
            if current:
                groups.append((current_start, line_no - 1, current))
                current = []
            continue

        if current and _LOGICAL_CODE_BOUNDARY.match(line):
            groups.append((current_start, line_no - 1, current))
            current = [line]
            current_start = line_no
            continue

        if not current:
            current_start = line_no
        current.append(line)

    if current:
        groups.append((current_start, start_line + len(lines) - 1, current))

    return groups


def _split_oversized_group(lines, start_line, max_chars, context):
    parts = []
    current = []
    current_len = len(context) + 1 if context else 0
    current_start = start_line

    for offset, line in enumerate(lines):
        line_no = start_line + offset
        line_len = len(line) + 1
        if current and current_len + line_len > max_chars:
            text = "\n".join(current)
            if context and not text.startswith(context):
                text = f"{context}\n{text}"
            parts.append({
                "text": text,
                "start_line": current_start,
                "end_line": line_no - 1
            })
            current = [line]
            current_len = len(context) + line_len + 1 if context else line_len
            current_start = line_no
        else:
            if not current:
                current_start = line_no
            current.append(line)
            current_len += line_len

    if current:
        text = "\n".join(current)
        if context and not text.startswith(context):
            text = f"{context}\n{text}"
        parts.append({
            "text": text,
            "start_line": current_start,
            "end_line": start_line + len(lines) - 1
        })
    return parts


def _split_logical_lines(lines, start_line, max_chars):
    parts = []
    current = []
    current_len = 0
    current_start = None
    current_end = None
    context = _header_context(lines)

    for group_start, group_end, group_lines in _logical_line_groups(lines, start_line):
        group_text = "\n".join(group_lines)
        group_len = len(group_text) + 2

        if group_len > max_chars:
            if current:
                parts.append({
                    "text": "\n\n".join(current),
                    "start_line": current_start,
                    "end_line": current_end
                })
                current = []
                current_len = 0
                current_start = None
                current_end = None

            parts.extend(_split_oversized_group(group_lines, group_start, max_chars, context))
            continue

        if current and current_len + group_len > max_chars:
            parts.append({
                "text": "\n\n".join(current),
                "start_line": current_start,
                "end_line": current_end
            })
            current = [group_text]
            current_len = group_len
            current_start = group_start
            current_end = group_end
        else:
            if not current:
                current_start = group_start
            current.append(group_text)
            current_len += group_len
            current_end = group_end

    if current:
        parts.append({
            "text": "\n\n".join(current),
            "start_line": current_start,
            "end_line": current_end
        })
    return parts


def _code_blocks(text):
    lines = text.splitlines()
    if not lines:
        return []

    boundary_lines = [
        i + 1
        for i, line in enumerate(lines)
        if _CODE_BOUNDARY.match(line)
    ]

    if not boundary_lines:
        return [{
            "text": text,
            "start_line": 1,
            "end_line": len(lines)
        }]

    starts = boundary_lines[:]
    if starts[0] > 1:
        starts.insert(0, 1)

    blocks = []
    for index, start in enumerate(starts):
        end = starts[index + 1] - 1 if index + 1 < len(starts) else len(lines)
        block_lines = lines[start - 1:end]
        if any(line.strip() for line in block_lines):
            blocks.append({
                "text": "\n".join(block_lines),
                "start_line": start,
                "end_line": end
            })
    return blocks


def _split_code(text, max_chars):
    blocks = _code_blocks(text)
    parts = []
    current = []
    current_len = 0
    current_start = None
    current_end = None

    for block in blocks:
        block_text = block["text"]
        block_len = len(block_text) + 1

        if block_len > max_chars:
            if current:
                parts.append({
                    "text": "\n\n".join(current),
                    "start_line": current_start,
                    "end_line": current_end
                })
                current = []
                current_len = 0
                current_start = None
                current_end = None

            lines = block_text.splitlines()
            parts.extend(_split_logical_lines(lines, block["start_line"], max_chars))
            continue

        if current and current_len + block_len > max_chars:
            parts.append({
                "text": "\n\n".join(current),
                "start_line": current_start,
                "end_line": current_end
            })
            current = [block_text]
            current_len = block_len
            current_start = block["start_line"]
            current_end = block["end_line"]
        else:
            if not current:
                current_start = block["start_line"]
            current.append(block_text)
            current_len += block_len
            current_end = block["end_line"]

    if current:
        parts.append({
            "text": "\n\n".join(current),
            "start_line": current_start,
            "end_line": current_end
        })
    return parts


def _is_code(reference):
    return any(reference.endswith(ext) for ext in CODE_EXTENSIONS)


def chunk(chunks, max_chars=1000, max_chunks=None):
    result = []
    for item in chunks:
        text = item["text"]
        if len(text) <= max_chars:
            result.append(item)
            continue

        is_code = _is_code(item.get("reference", ""))
        if is_code:
            parts = _split_code(text, max_chars)
        else:
            parts = _split_sentences(text, max_chars)

        for j, part in enumerate(parts):
            part_text = part["text"] if is_code else part
            if part_text.strip():
                reference = f"{item['reference']}_part{j + 1}"
                if is_code:
                    reference = (
                        f"{item['reference']}:L{part['start_line']}-L{part['end_line']}"
                    )
                result.append({
                    "text": part_text,
                    "source": item["source"],
                    "reference": reference
                })

    if max_chunks is not None:
        return result[:max_chunks]
    return result
