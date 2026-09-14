"""UI strings live in locales/*.json and are injected at build time.

Every key used by the template (data-i18n* / t() / tf()) must exist in all
locales; all locales share the exact key set of en.json with identical
{placeholder} sets.
"""
import json
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(REPO_ROOT, "templates", "report_template.html")
LOCALES_DIR = os.path.join(REPO_ROOT, "locales")

EXPECTED_LANGS = ["en", "fr", "es", "pt", "zh", "hi", "ar", "bn", "ru", "id"]

ATTR_RE = re.compile(r'data-i18n(?:-html|-ph|-title|-aria)?="([A-Za-z0-9_]+)"')
CALL_RE = re.compile(r"\btf?\(\s*'([A-Za-z0-9_]+)'")
PH_RE = re.compile(r"\{[a-z]+\}")


def _load_locales():
    locales = {}
    for name in sorted(os.listdir(LOCALES_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(LOCALES_DIR, name), encoding="utf-8") as f:
            locales[name[:-5]] = json.load(f)
    return locales


def _load_template():
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


class TestLocales(unittest.TestCase):
    def test_ten_locales_present(self):
        self.assertEqual(sorted(_load_locales()), sorted(EXPECTED_LANGS))

    def test_parity_with_english(self):
        locales = _load_locales()
        ref = list(locales["en"])
        for lang, strings in locales.items():
            self.assertEqual(list(strings), ref, "key order mismatch: %s" % lang)

    def test_placeholders_match_english(self):
        locales = _load_locales()
        ref = locales["en"]
        for lang, strings in locales.items():
            for key, text in strings.items():
                self.assertEqual(set(PH_RE.findall(text)),
                                 set(PH_RE.findall(ref[key])),
                                 "placeholder mismatch %s:%s" % (lang, key))

    def test_no_script_breakout(self):
        for lang, strings in _load_locales().items():
            for key, text in strings.items():
                self.assertNotIn("</script", text.lower(), "%s:%s" % (lang, key))

    def test_used_keys_defined(self):
        locales = _load_locales()
        html = _load_template()
        used = set(ATTR_RE.findall(html)) | set(CALL_RE.findall(html))
        self.assertTrue(used, "no i18n keys found in template")
        self.assertEqual(set(), used - set(locales["en"]),
                         "missing keys: %s" % sorted(used - set(locales["en"])))


class TestTemplateWiring(unittest.TestCase):
    def test_locales_injected_at_build(self):
        html = _load_template()
        self.assertIn("/*__LOCALES__*/", html)
        self.assertNotIn("const I18N={", html)

    def test_switcher_present(self):
        html = _load_template()
        self.assertIn('id="lang-select"', html)
        self.assertIn("function setLang(", html)
        self.assertIn("agentledger_lang", html)
        self.assertIn("document.documentElement.dir", html)

    def test_trio_layout(self):
        html = _load_template()
        trio = html.index('id="trio"')
        for cid in ("anomaly-card", "c-cost-hist", "c-cache"):
            pos = html.index('id="%s"' % cid)
            self.assertTrue(trio < pos, cid)
        trio2 = html.index('id="trio-models"')
        self.assertTrue(html.index('id="c-cache"') < trio2)
        for cid in ("c-tok-model", "c-req-model", "c-cost-model-bar"):
            pos = html.index('id="%s"' % cid)
            self.assertTrue(trio2 < pos, cid)


if __name__ == "__main__":
    unittest.main()
