"""Export the inspected CLDR reverse direction; reject unfamiliar rule syntax."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "Latin-ConjoiningJamo.xml"
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == "82f2fc6ae1fca9c71fba7851c0b3ecc7e6e3cbd5aeb74ce80dd6c8c423cddfba"
rules = SOURCE.read_text().split("<![CDATA[", 1)[1].split("]]>", 1)[0]
rules = "\n".join(line.split("#", 1)[0] for line in rules.splitlines())
variables = dict(re.findall(r"\$(\w+)\s*=\s*([^;]+);", rules))
variables = {k: re.sub(r"\s", "", v) for k, v in variables.items()}


def expression(source):
    output, in_class = "", False
    tokens = re.findall(r"\$\w+|[^\s]", source)
    for token in tokens:
        if token == "[":
            assert not in_class
            in_class = True
        if token.startswith("$"):
            token = variables[token[1:]]
            if in_class and token.startswith("["):
                token = token[1:-1]
        assert "$" not in token
        output += token
        if token == "]":
            in_class = False
    assert not in_class
    re.compile(output)
    return output


separators = []
for before, after in re.findall(r"\$sep\s*←\s*([^;]+?)\{\}\s*([^;]+);", rules):
    separators.append((expression(before) + "$", "^" + expression(after)))
assert len(separators) == 53
letters = {}
for clause in rules.split(";"):
    if "↔" not in clause:
        continue
    left, right = clause.split("↔")
    key = right.strip().removeprefix("$")
    if key == "sep":
        continue
    glyph = variables[key]
    latin = re.search(r"\{([a-z]+)\}", left)
    assert latin and len(glyph) == 1, clause
    letters[ord(glyph)] = latin.group(1)
letters[0x110B] = ""
assert len(letters) == 67


def quoted(value):
    # Java/Kotlin dollar signs need escaping in generated strings.
    return json.dumps(value, ensure_ascii=False).replace("$", "\\$")


lines = [
    "// Generated from the pinned Unicode CLDR data. See adjacent LICENSE/upstream.json.",
    "package co.fallsoft.vipi",
    "internal object KoreanLetterRules {",
    '    const val policy = "cldr-f692579-orthographic-1"',
    "    private val letters = mapOf(",
    ",\n".join(f"        {code} to {quoted(value)}" for code, value in sorted(letters.items())),
    "    )",
    "    private data class Rule(val before: Regex, val after: Regex)",
    "    private val rules = listOf(",
    ",\n".join(f"        Rule(Regex({quoted(a)}), Regex({quoted(b)}))" for a, b in separators),
    "    )",
    "    // A fixed dispatch table avoids scanning irrelevant rules per letter.",
    "    private val byFirst = letters.keys.associateWith { code ->",
    "        rules.filter { rule -> (0x1161..0x1175).any { vowel ->",
    "            rule.after.containsMatchIn(code.toChar().toString() + vowel.toChar())",
    "        } }",
    "    }",
    "    fun romanize(source: String): String {",
    "        require(source.isNotEmpty() && source.all { it.code in 0xAC00..0xD7A3 })",
    "        val jamo = StringBuilder(source.length * 3)",
    "        for (syllable in source) {",
    "            val index = syllable.code - 0xAC00",
    "            jamo.append((0x1100 + index / 588).toChar())",
    "            jamo.append((0x1161 + index % 588 / 28).toChar())",
    "            if (index % 28 != 0) jamo.append((0x11A7 + index % 28).toChar())",
    "        }",
    "        val output = StringBuilder()",
    "        for (index in jamo.indices) {",
    "            val candidates = byFirst[jamo[index].code].orEmpty()",
    "            if (candidates.isNotEmpty()) {",
    "                // ICU negated context classes include the start boundary.",
    '                val before = if (output.length < 6) "\\uFFFF" + output.toString() else output.substring(output.length - 6)',
    "                val after = jamo.substring(index, minOf(jamo.length, index + 2))",
    "                if (candidates.any { it.before.containsMatchIn(before) && it.after.containsMatchIn(after) }) output.append('-')",
    "            }",
    "            output.append(letters.getValue(jamo[index].code))",
    "        }",
    "        return output.toString()",
    "    }",
    "}",
]
destination = ROOT / "KoreanLetterRules.kt"
destination.write_text("\n".join(lines) + "\n")
print(json.dumps({"rules": len(separators), "letter_mappings": len(letters),
                  "generated_sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}))
