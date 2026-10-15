"""Synthetic boundary checks; no phase answers or harness imports."""
import importlib.util
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch


@dataclass
class Verdict:
    alert: bool
    pillar: str
    reason: str = ""


spec = importlib.util.spec_from_file_location("defense_under_test", Path(__file__).with_name("defense.py"))
defense = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"api": SimpleNamespace(Verdict=Verdict)}):
    spec.loader.exec_module(defense)


class DefenseTests(unittest.TestCase):
    def setUp(self):
        self.ctx = SimpleNamespace(
            baseline={
                "row_count_min": 80, "row_count_max": 120,
                "null_rate_max": 0.1,
                "mean_amount_min": 80, "mean_amount_max": 120,
                "staleness_min_max": 10,
                "freshness_delay_max_min": 20,
                "lineage_duration_ms_max": 1000,
                "feature_mean_shift_sigma_max": 0.4095,
                "embedding_centroid_shift_max": 0.039,
                "corpus_avg_doc_age_days_max": 41,
            },
            tools=Mock(), state={}, on=Mock(),
        )
        self.cases = [
            ("data_batch", "batch_profile", {"batch_id": "batch"}, ("batch",),
             {"row_count": 100, "null_rate": {"customer_id": 0}, "mean_amount": 100, "staleness_min": 0}, "checks"),
            ("contract_checkpoint", "contract_diff", {"contract_id": "contract", "checkpoint_batch_id": "batch", "declared_sla": {"freshness_min": 15}},
             ("contract", "batch"), {"violations": [], "freshness_delay_min": 5}, "contracts"),
            ("lineage_run", "lineage_graph_slice", {"run_id": "run"}, ("run",),
             {"actual_upstream": ["raw.orders", "raw.customers"], "actual_downstream_count": 1, "duration_ms": 500}, "lineage"),
            ("feature_materialization", "feature_drift", {"feature_view": "features", "batch_id": "batch"}, ("features", "batch"),
             {"mean_shift_sigma": 0.472}, "ai_infra"),
            ("embedding_batch", "embedding_drift", {"corpus": "docs", "chunk_batch_id": "batch"}, ("docs", "batch"),
             {"centroid_shift": 0.038, "avg_doc_age_days": 40}, "ai_infra"),
        ]

    def check_case(self, index, changes=None, alert=False, payload=None):
        event, tool, default_payload, args, result, pillar = self.cases[index]
        self.ctx.tools.reset_mock()
        getattr(self.ctx.tools, tool).return_value = result | (changes or {})
        verdict = getattr(defense, "check_" + event)(default_payload if payload is None else payload, self.ctx)
        self.assertIsInstance(verdict, Verdict)
        self.assertEqual((verdict.alert, verdict.pillar), (alert, pillar))
        if alert:
            self.assertTrue(verdict.reason)
        self.assertEqual(self.ctx.tools.mock_calls, [getattr(call, tool)(*args)])

    def test_register(self):
        defense.register(self.ctx)
        self.assertEqual(self.ctx.on.call_count, 5)
        for event, *_ in self.cases:
            self.ctx.on.assert_any_call(event, getattr(defense, "check_" + event))

    def test_clean_events_and_tool_arguments(self):
        for index in range(5):
            with self.subTest(event=self.cases[index][0]):
                self.check_case(index)

    def test_tool_errors_alert(self):
        for event, tool, payload, args, _, pillar in self.cases:
            with self.subTest(event=event):
                self.ctx.tools.reset_mock()
                getattr(self.ctx.tools, tool).return_value = {"error": "unavailable"}
                verdict = getattr(defense, "check_" + event)(payload, self.ctx)
                self.assertEqual((verdict.alert, verdict.pillar), (True, pillar))
                self.assertTrue(verdict.reason)
                self.assertEqual(self.ctx.tools.mock_calls, [getattr(call, tool)(*args)])

    def test_data_limits(self):
        for field, boundary, faulty in [
            ("row_count", 80, 79), ("row_count", 120, 121),
            ("mean_amount", 80, 79), ("mean_amount", 120, 121),
            ("null_rate", {"customer_id": 0.1}, {"customer_id": 0.101}),
            ("staleness_min", 10, 10.01),
        ]:
            with self.subTest(field=field, boundary=boundary):
                self.check_case(0, {field: boundary})
                self.check_case(0, {field: faulty}, alert=True)

    def test_composite_distance(self):
        self.check_case(0, {"row_count": 119})
        self.check_case(0, {"mean_amount": 119})
        self.check_case(0, {"row_count": 119, "mean_amount": 119}, alert=True)
        self.check_case(0, {"null_rate": {"customer_id": 0.095}, "staleness_min": 9.5}, alert=True)

    def test_contract_violations_and_sla(self):
        for violation in ["type_violation", "schema_hash_mismatch"]:
            with self.subTest(violation=violation):
                self.check_case(1, {"violations": [violation]}, alert=True)
        self.check_case(1, {"freshness_delay_min": 15})
        self.check_case(1, {"freshness_delay_min": 15.01}, alert=True)
        payload = self.cases[1][2] | {"declared_sla": {"freshness_min": 30}}
        self.check_case(1, {"freshness_delay_min": 20}, payload=payload)
        self.check_case(1, {"freshness_delay_min": 20.01}, alert=True, payload=payload)
        payload = {key: value for key, value in payload.items() if key != "declared_sla"}
        self.check_case(1, {"freshness_delay_min": 20}, payload=payload)
        self.check_case(1, {"freshness_delay_min": 20.01}, alert=True, payload=payload)

    def test_lineage(self):
        for changes in [
            {"actual_downstream_count": 0},
            {"actual_upstream": ["raw.orders"]},
            {"actual_upstream": ["raw.customers"]},
            {"duration_ms": 1001},
        ]:
            with self.subTest(changes=changes):
                self.check_case(2, changes, alert=True)
        self.check_case(2, {"duration_ms": 1000})
        self.check_case(2, {"actual_upstream": ["raw.customers", "raw.orders", "raw.extra"]})

    def test_feature_threshold(self):
        self.check_case(3, {"mean_shift_sigma": 0.65})
        self.check_case(3, {"mean_shift_sigma": 0.6501}, alert=True)
        self.check_case(3, {"mean_shift_sigma": 0.970}, alert=True)

    def test_embedding_thresholds(self):
        for field, boundary, faulty in [
            ("centroid_shift", 0.040, 0.0401),
            ("avg_doc_age_days", 45, 45.01),
        ]:
            with self.subTest(field=field):
                self.check_case(4, {field: boundary})
                self.check_case(4, {field: faulty}, alert=True)


if __name__ == "__main__":
    unittest.main()
