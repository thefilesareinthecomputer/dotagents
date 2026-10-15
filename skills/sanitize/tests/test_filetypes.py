#!/usr/bin/env python3
"""Tests for skills/sanitize/scripts/filetypes.py: how each file type is parsed so a term
inside a JSON escape, a CSV cell or a Word document's XML is found and replaced, and
how binaries are skipped. Every term is invented.
Run: python3 -m unittest discover -s skills/sanitize/tests -v
"""

import base64
import csv
import importlib.util
import io
import json
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ft = load("filetypes")
sz = load("sanitize")

T = {"zorbulate"}


def scrub(text, counts):
    return sz.scrub_text(text, T, counts)


def field(key, value, counts):
    return sz.scrub_field(key, value, counts, scrub)


def run(name, data, docx=True):
    counts = {}
    out, why = ft.sanitize_bytes(name, data, scrub, counts, field, docx=docx)
    return out, why, counts


class TestClassify(unittest.TestCase):
    def test_by_extension(self):
        self.assertEqual(ft.classify("notes.md", b""), "text")
        self.assertEqual(ft.classify("x.py", b""), "text")
        self.assertEqual(ft.classify("data.json", b""), "json")
        self.assertEqual(ft.classify("rows.jsonl", b""), "jsonl")
        self.assertEqual(ft.classify("t.csv", b""), "csv")
        self.assertEqual(ft.classify("t.tsv", b""), "csv")
        self.assertEqual(ft.classify("memo.docx", b""), "docx")
        self.assertEqual(ft.classify("paper.pdf", b""), "pdf")
        self.assertEqual(ft.classify("pic.png", b""), "binary")

    def test_unknown_extension_is_sniffed(self):
        self.assertEqual(ft.classify("README", b"plain words\n"), "text")
        self.assertEqual(ft.classify("blob.dat", bytes(range(256))), "binary")
        self.assertEqual(ft.classify("blob.dat", b"\x00\x00text"), "binary")


class TestText(unittest.TestCase):
    def test_text_is_scrubbed_and_reencoded(self):
        out, why, counts = run("a.md", "# zorbulate\nbody\n".encode())
        self.assertEqual(out, b"# [TERM]\nbody\n")
        self.assertIsNone(why)
        self.assertEqual(counts, {"term": 1})

    def test_undecodable_text_extension_is_skipped_as_undecodable(self):
        # a text type that did not decode was not inspected, which a tree scan reports apart from a known binary
        out, why, _ = run("a.txt", b"\xff\xfe\x00\x01" * 10)
        self.assertIsNone(out)
        self.assertEqual(why, "undecodable")


class TestJson(unittest.TestCase):
    def test_term_behind_unicode_escape_is_found(self):
        data = b'{"owner": "zorbul\\u0061te", "n": 1}'
        out, _, counts = run("x.json", data)
        self.assertEqual(json.loads(out), {"owner": "[TERM]", "n": 1})
        self.assertEqual(counts, {"term": 1})

    def test_keys_and_nested_values_are_scrubbed(self):
        data = json.dumps({"zorbulate": {"list": ["ok", "zorbulate"]}}).encode()
        out, _, counts = run("x.json", data)
        self.assertEqual(json.loads(out), {"[TERM]": {"list": ["ok", "[TERM]"]}})
        self.assertEqual(counts["term"], 2)

    def test_non_string_values_survive(self):
        data = json.dumps({"a": 1.5, "b": None, "c": True}).encode()
        out, _, _ = run("x.json", data)
        self.assertEqual(json.loads(out), {"a": 1.5, "b": None, "c": True})

    def test_invalid_json_falls_back_to_text(self):
        out, why, counts = run("x.json", b"{not json zorbulate")
        self.assertEqual(out, b"{not json [TERM]")
        self.assertIsNone(why)

    def test_jsonl_is_scrubbed_line_by_line(self):
        data = b'{"a": "zorbulate"}\n{"a": "fine"}\nnot json zorbulate\n'
        out, _, counts = run("x.jsonl", data)
        lines = out.decode().splitlines()
        self.assertEqual(json.loads(lines[0]), {"a": "[TERM]"})
        self.assertEqual(json.loads(lines[1]), {"a": "fine"})
        self.assertEqual(lines[2], "not json [TERM]")
        self.assertEqual(counts, {"term": 2})


class TestFieldContext(unittest.TestCase):
    """A credential split into a key and a value by the parser must still meet the
    assignment rule: `{"password": "..."}` is `password=...` to a reader."""

    def test_json_credential_value_under_a_key_like_name_is_masked(self):
        out, _, counts = run("cfg.json", json.dumps({"password": "Hunter2Hunter2x9", "name": "zorbulate"}).encode())
        self.assertEqual(json.loads(out), {"password": "[SECRET]", "name": "[TERM]"})
        self.assertEqual((counts["secret"], counts["term"]), (1, 1))
        nested = {"db": {"api_key": "AbCdEf123456GhIjK", "host": "db.internal"}, "tokens": ["x", {"token": "k9k9k9k9k9k9k9"}]}
        out, _, counts = run("cfg.json", json.dumps(nested).encode())
        self.assertEqual(json.loads(out), {"db": {"api_key": "[SECRET]", "host": "db.internal"}, "tokens": ["x", {"token": "[SECRET]"}]})
        self.assertEqual(counts["secret"], 2)

    def test_short_or_wordlike_values_under_a_key_like_name_are_left_alone(self):
        out, _, counts = run("cfg.json", json.dumps({"password": "abc", "token": "[SECRET]", "key": "parts[0]"}).encode())
        self.assertEqual(json.loads(out), {"password": "abc", "token": "[SECRET]", "key": "parts[0]"})
        self.assertNotIn("secret", counts)

    def test_jsonl_rows_and_csv_columns_get_the_same_context(self):
        rows = [json.dumps({"user": "u1", "secret": "s3cr3ts3cr3ts3"}), json.dumps({"user": "u2", "secret": "short"})]
        out, _, counts = run("rows.jsonl", "\n".join(rows).encode())
        self.assertEqual([json.loads(l)["secret"] for l in out.decode().splitlines()], ["[SECRET]", "short"])
        csv_text = "user,api_key,note\nu1,ZxZxZxZx1234ZxZx,fine\nu2,nope,zorbulate\n"
        out, _, counts = run("t.csv", csv_text.encode())
        got = list(csv.reader(io.StringIO(out.decode())))
        self.assertEqual(got, [["user", "api_key", "note"], ["u1", "[SECRET]", "fine"], ["u2", "nope", "[TERM]"]])
        self.assertEqual((counts["secret"], counts["term"]), (1, 1))


class TestCsv(unittest.TestCase):
    def test_cells_are_scrubbed_and_quoting_survives(self):
        data = 'name,note\nzorbulate,"hello, world"\n'.encode()
        out, _, counts = run("t.csv", data)
        rows = list(csv.reader(io.StringIO(out.decode())))
        self.assertEqual(rows, [["name", "note"], ["[TERM]", "hello, world"]])
        self.assertEqual(counts, {"term": 1})

    def test_tsv_keeps_tabs(self):
        data = "a\tb\nzorbulate\tx\n".encode()
        out, _, _ = run("t.tsv", data)
        self.assertEqual(out.decode().splitlines()[1], "[TERM]\tx")


def make_docx(document_xml: str, extra: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        z.writestr("word/document.xml", document_xml)
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


DOC = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="urn:x"><w:body>'
       '<w:p><w:r><w:t>Owner: zorbulate &amp; co</w:t></w:r></w:p>'
       '<w:p><w:r><w:t xml:space="preserve"> plain </w:t></w:r></w:p>'
       '</w:body></w:document>')


class TestDocx(unittest.TestCase):
    def test_text_nodes_are_scrubbed_and_other_parts_are_byte_identical(self):
        media = b"\x89PNG\r\n\x1a\n" + bytes(range(64))
        src = make_docx(DOC, {"word/media/image1.png": media, "word/styles.xml": "<w:styles/>"})
        out, why, counts = run("memo.docx", src)
        self.assertIsNone(why)
        self.assertEqual(counts, {"term": 1})
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            names = z.namelist()
            doc = z.read("word/document.xml").decode()
            self.assertEqual(z.read("word/media/image1.png"), media)
            self.assertEqual(z.read("word/styles.xml"), b"<w:styles/>")
        self.assertEqual(names, ["[Content_Types].xml", "word/document.xml", "word/media/image1.png", "word/styles.xml"])
        self.assertIn("<w:t>Owner: [TERM] &amp; co</w:t>", doc)
        self.assertIn('<w:t xml:space="preserve"> plain </w:t>', doc)
        self.assertNotIn("zorbulate", doc)

    def test_xml_escapes_round_trip(self):
        doc = DOC.replace("Owner: zorbulate &amp; co", "a &lt; b &gt; c &quot;zorbulate&quot;")
        out, _, _ = run("memo.docx", make_docx(doc))
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            text = z.read("word/document.xml").decode()
        self.assertIn("a &lt; b &gt; c &quot;[TERM]&quot;", text)

    def test_headers_footers_and_comments_are_scanned_too(self):
        part = '<w:hdr xmlns:w="urn:x"><w:p><w:r><w:t>zorbulate</w:t></w:r></w:p></w:hdr>'
        src = make_docx(DOC.replace("zorbulate", "x"), {"word/header1.xml": part, "word/comments.xml": part})
        out, _, counts = run("memo.docx", src)
        self.assertEqual(counts, {"term": 2})
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            self.assertIn("[TERM]", z.read("word/header1.xml").decode())
            self.assertIn("[TERM]", z.read("word/comments.xml").decode())

    def test_a_docx_that_is_not_a_zip_is_skipped(self):
        out, why, _ = run("memo.docx", b"not a zip at all")
        self.assertIsNone(out)
        self.assertEqual(why, "binary")

    def test_docx_is_refused_unless_asked_for_and_document_properties_are_scanned_when_it_is(self):
        # the text-node parser misses attributes, CDATA and a term split across runs, so a Word file
        # is skipped as uninspected until the caller opts into the best-effort pass
        out, why, counts = run("memo.docx", make_docx(DOC), docx=False)
        self.assertIsNone(out)
        self.assertEqual((why, counts), ("docx", {}))
        props = '<cp:coreProperties xmlns:cp="urn:x"><dc:creator>zorbulate</dc:creator></cp:coreProperties>'
        out, why, counts = run("memo.docx", make_docx(DOC.replace("zorbulate", "x"), {"docProps/core.xml": props}))
        self.assertIsNone(why)
        self.assertEqual(counts, {"term": 1})
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            self.assertIn("<dc:creator>[TERM]</dc:creator>", z.read("docProps/core.xml").decode())

    def test_a_docx_whose_parts_inflate_past_the_bound_is_skipped(self):
        big = make_docx(DOC, {"word/pad.xml": "<x>" + "a" * (ft.DOCX_MAX_INFLATED + 10) + "</x>"})
        out, why, _ = run("memo.docx", big)
        self.assertIsNone(out)
        self.assertEqual(why, "too-large")


class TestSkipped(unittest.TestCase):
    def test_pdf_and_binary_are_skipped_with_a_reason(self):
        out, why, counts = run("p.pdf", b"%PDF-1.4")
        self.assertIsNone(out)
        self.assertEqual(why, "pdf")
        out, why, counts = run("i.png", b"\x89PNG")
        self.assertIsNone(out)
        self.assertEqual(why, "binary")
        self.assertEqual(counts, {})

    def test_base64_inside_a_text_file_still_goes_through_the_engine(self):
        enc = base64.b64encode(b"the zorbulate memo").decode()
        out, _, counts = run("notes.txt", f"blob {enc}\n".encode())
        self.assertEqual(out, b"blob [TERM]\n")
        self.assertEqual(counts, {"term-encoded": 1})


if __name__ == "__main__":
    unittest.main()
