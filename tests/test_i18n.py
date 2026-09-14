"""Every i18n key used by the report template must exist in EN and FR."""
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(REPO_ROOT, "templates", "report_template.html")

ATTR_RE = re.compile(r'data-i18n(?:-html|-ph|-title|-aria)?="([A-Za-z0-9_]+)"')
CALL_RE = re.compile(r"\btf?\(\s*'([A-Za-z0-9_]+)'")


def _load():
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def _dict_keys(html, lang):
    start = html.index("const I18N=")
    block_start = html.index(lang + ":{", start)
    if lang == "en":
        block_end = html.index("\n},\nfr:{", block_start)
    else:
        block_end = html.index("\n}\n};", block_start)
    return set(re.findall(r"^  ([A-Za-z0-9_]+):", html[block_start:block_end], re.M))


class TestI18nCoverage(unittest.TestCase):
    def test_used_keys_defined_in_both_languages(self):
        html = _load()
        used = set(ATTR_RE.findall(html)) | set(CALL_RE.findall(html))
        self.assertTrue(used, "no i18n keys found in template")
        for lang in ("en", "fr"):
            defined = _dict_keys(html, lang)
            self.assertTrue(defined, "no %s dict found" % lang)
            self.assertEqual(set(), used - defined,
                             "missing %s keys: %s" % (lang, sorted(used - defined)))

    def test_language_parity(self):
        html = _load()
        self.assertEqual(_dict_keys(html, "en"), _dict_keys(html, "fr"))

    def test_switcher_present(self):
        html = _load()
        self.assertIn('id="lang-toggle"', html)
        self.assertIn("function setLang(", html)
        self.assertIn("agentledger_lang", html)

    def test_trio_layout(self):
        html = _load()
        trio = html.index('id="trio"')
        for cid in ("anomaly-card", "c-cost-hist", "c-cache"):
            pos = html.index('id="%s"' % cid)
            self.assertTrue(trio < pos, cid)


if __name__ == "__main__":
    unittest.main()
