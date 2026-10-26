"""synthlabel —— 自检测试。

为每条合成数据记录生成方式、筛选依据与不确定度，随数据一起流转。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import synthlabel  # noqa: E402


class TestSynthLabel(unittest.TestCase):
    def test_label_has_all_fields(self):
        label = synthlabel.make_label({"text": "内容"}, "text", 0)
        for f in synthlabel.LABEL_FIELDS:
            self.assertIn(f, label)

    def test_generator_is_guessed(self):
        label = synthlabel.make_label({"text": "x", "model": "gpt-4o"}, "text", 0)
        self.assertEqual(label["generated_by"], "gpt")

    def test_missing_filter_is_marked_not_invented(self):
        label = synthlabel.make_label({"text": "x"}, "text", 0)
        self.assertEqual(label["filter_criteria"], "未标注")

    def test_uncertainty_detects_ai_markers(self):
        label = synthlabel.make_label(
            {"text": "As an AI language model, I cannot do that."}, "text", 0)
        self.assertNotEqual(label["uncertainty"]["level"], "low")

    def test_clean_text_has_low_uncertainty(self):
        label = synthlabel.make_label({"text": "今天天气不错，适合出门走走。"},
                                   "text", 0)
        self.assertEqual(label["uncertainty"]["level"], "low")

    def test_audit_reports_missing_source(self):
        rows = [{"text": "x", "model": "gpt-4o"}]
        labels = [synthlabel.make_label(r, "text", i) for i, r in enumerate(rows)]
        a = synthlabel.audit(rows, labels, "text")
        self.assertEqual(a["summary"]["missing_source_count"], 1)
