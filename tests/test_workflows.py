"""Regression tests for state transitions, policy retrieval, and audit integrity."""
import os
import tempfile
import unittest

from elyraops import core


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        core.DB_PATH = os.path.join(self.temp.name, "tests.db")
        core.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_seeded_five_cases(self):
        self.assertGreaterEqual(len(core.list_cases()), 5)

    def test_dashboard_counts_match(self):
        self.assertEqual(core.dashboard()["cases_total"], len(core.list_cases()))

    def test_retrieval_cites_correct_policy(self):
        with core.connect() as db:
            hits=core.retrieve(db,"Duplicate payment after subscription upgrade", "Billing")
        self.assertEqual(hits[0]["id"], "POL-001")

    def test_investigation_is_idempotent(self):
        first = core.investigate("EC-1042")
        again = core.investigate("EC-1042")
        self.assertFalse(first["already_processed"])
        self.assertTrue(again["already_processed"])
        self.assertEqual(first["workflow_run_id"], again["workflow_run_id"])
        c=core.get_case("EC-1042")
        self.assertEqual(sum(e["type"] == "approval_requested" for e in c["events"]), 1)

    def test_no_approval_before_investigation(self):
        with self.assertRaisesRegex(ValueError,"pending approval"):
            core.decide("EC-1043", "approve", "tester")

    def test_approval_simulates_only(self):
        core.investigate("EC-1042")
        core.decide("EC-1042", "approve", "tester")
        c=core.get_case("EC-1042")
        self.assertEqual(c["status"], "Approved · simulated")
        self.assertTrue(any(e["type"] == "simulated_execution" for e in c["events"]))

    def test_rejection_does_not_execute(self):
        core.investigate("EC-1043")
        core.decide("EC-1043", "reject", "tester")
        c=core.get_case("EC-1043")
        self.assertEqual(c["status"], "Rejected")
        self.assertFalse(any(e["type"] == "simulated_execution" for e in c["events"]))

    def test_create_and_investigate_custom_case(self):
        created=core.create_case({"title":"Supplier dispute review","description":"Supplier provided an invoice with inconsistent payment terms and mismatched line items.","domain":"Procurement","priority":"High","organization":"Test Co"})
        core.investigate(created["id"])
        c=core.get_case(created["id"])
        self.assertEqual(c["status"], "Pending approval")
        self.assertIn("POL-004",[d["id"] for d in c["evidence"]])

    def test_reject_invalid_case(self):
        with self.assertRaises(ValueError):
            core.create_case({"title":"x","description":"short"})

    def test_unknown_case(self):
        with self.assertRaises(KeyError):
            core.investigate("EC-DOES-NOT-EXIST")

if __name__ == "__main__":
    unittest.main()
