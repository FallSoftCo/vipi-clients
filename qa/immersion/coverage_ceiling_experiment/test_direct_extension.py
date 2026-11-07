import re
import unittest

from compare_direct_extension import aligned, mixed, select


def call(text, translation):
    # Mirrors the observed native behavior relevant to this regression:
    # alphabetic word ranges exclude stand-alone numeric tokens.
    return {"text": text, "translation": translation, "status": "translated",
            "identifiers_preserved": True,
            "native_target_word_ranges": [[m.start(), m.end()] for m in re.finditer(r"[A-Za-z]+", translation)]}


def fixture(original, chunk, translation, full):
    words = [[m.start(), m.end()] for m in re.finditer(r"\w+", original)]
    start = original.index(chunk)
    end = start + len(chunk)
    indices = [i for i, (a, b) in enumerate(words) if start <= a and b <= end]
    message = {"text": original, "full_query_id": "full", "native_source_word_ranges": words,
               "candidates": [{"source_range": [start, end], "source_word_indices": [indices[0], indices[-1]+1],
                               "text": chunk, "query_id": "chunk", "arms": ["bounded_window"]}]}
    return message, {"full": call(original, full), "chunk": call(chunk, translation)}


class DirectAlignmentTests(unittest.TestCase):
    def test_date_reordering_cannot_drop_day_to_manufacture_agreement(self):
        message, capture = fixture("Return the 3rd of March please", "3rd of March", "Machi 3", "Rudi 3 ya Machi tafadhali")
        spans, rejects = aligned(message, capture)
        self.assertEqual([], spans)
        self.assertEqual(1, rejects["no_full_translation_agreement"])

    def test_date_projection_retains_numeric_edge(self):
        message, capture = fixture("Stay to the 27th please", "to the 27th", "hadi 27", "Kaa hadi 27 tafadhali")
        spans, _ = aligned(message, capture)
        self.assertEqual("hadi 27", spans[0]["translated"])
        self.assertEqual("Stay hadi 27 please", mixed(message["text"], spans))

    def test_article_deletion_is_not_target_language_immersion(self):
        message, capture = fixture("I want a comedy", "a comedy", "comedy", "Ninataka comedy")
        spans, rejects = aligned(message, capture)
        self.assertEqual([], spans)
        self.assertEqual(1, rejects["no_new_target_tokens"])

    def test_competing_disjoint_sources_cannot_both_claim_one_target(self):
        a = {"sourceStartUTF16": 0, "sourceEndUTF16": 3, "targetStartUTF16": 0, "targetEndUTF16": 4, "source_words": 1}
        b = dict(a, sourceStartUTF16=5, sourceEndUTF16=8)
        spans, covered, _ = select([a, b], 2)
        self.assertEqual([], spans)
        self.assertEqual(0, covered)


if __name__ == "__main__":
    unittest.main()
