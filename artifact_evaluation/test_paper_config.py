"""Regression tests for camera-ready experiment parameters."""

from __future__ import annotations

import unittest

from paper_config import apply_paper_parameters, effective_threshold


def base_config(mechanism: str) -> dict:
    return {
        "Frontend": {},
        "MemorySystem": {
            "Controller": {
                "plugins": [{"ControllerPlugin": {"impl": mechanism}}]
            },
            "DRAM": {},
        },
    }


class PaperConfigTests(unittest.TestCase):
    def plugin(self, mechanism: str, nominal: int, scheduler: str, **kwargs):
        config = base_config(mechanism)
        threshold = apply_paper_parameters(
            config, mechanism, nominal, scheduler, **kwargs
        )
        return threshold, config, config["MemorySystem"]["Controller"]["plugins"][0]["ControllerPlugin"]

    def test_security_margins(self):
        self.assertEqual(effective_threshold(125, "priority"), 125)
        self.assertEqual(effective_threshold(125, "mordor", radius=1), 123)
        self.assertEqual(effective_threshold(125, "mordor", radius=2), 121)
        self.assertEqual(effective_threshold(125, "mordor", radius=4), 117)
        self.assertEqual(
            effective_threshold(125, "mordor", radius=1, drfm_setup=True),
            122,
        )

    def test_graphene_table_sizes(self):
        expected = {125: (10_377, 10_546), 250: (5_189, 5_231),
                    500: (2_595, 2_605), 1000: (1_298, 1_300)}
        for nominal, (priority_entries, mordor_entries) in expected.items():
            _, _, priority = self.plugin("graphene", nominal, "priority")
            _, _, mordor = self.plugin("graphene", nominal, "mordor")
            self.assertEqual(priority["num_table_entries"], priority_entries)
            self.assertEqual(mordor["num_table_entries"], mordor_entries)
        _, _, radius2 = self.plugin("graphene", 125, "mordor", radius=2)
        _, _, radius4 = self.plugin("graphene", 125, "mordor", radius=4)
        _, _, setup = self.plugin(
            "graphene", 125, "mordor", drfm_setup=True
        )
        self.assertEqual(radius2["num_table_entries"], 10_720)
        self.assertEqual(radius4["num_table_entries"], 11_087)
        self.assertEqual(setup["num_table_entries"], 10_632)

    def test_blast_radius_and_drfm_parameters(self):
        threshold, config, hydra = self.plugin(
            "Hydra", 125, "mordor", radius=4
        )
        self.assertEqual(threshold, 117)
        self.assertEqual(hydra["hydra_tracking_threshold"], 60)
        self.assertEqual(hydra["hydra_group_threshold"], 46)
        self.assertEqual(config["MemorySystem"]["DRAM"]["RFM"]["BRC"], 2)

        threshold, config, para = self.plugin(
            "PARA", 125, "mordor", drfm_setup=True
        )
        self.assertEqual(threshold, 122)
        self.assertEqual(para["threshold"], 0.247)
        timing = config["MemorySystem"]["DRAM"]["timing"]
        self.assertEqual(timing, {"nDRFMsb": 460, "nDRFMab": 524})

    def test_reset_periods_and_no_controller_qos(self):
        expected = {"Hydra": 32_000_000, "comet": 10_666_667,
                    "DAPPER": 32_000_000, "graphene": 32_000_000,
                    "abacus": 32_000_000}
        reset_key = {"Hydra": "hydra_reset_period_ns"}
        for mechanism, period in expected.items():
            _, config, plugin = self.plugin(mechanism, 125, "mordor")
            self.assertEqual(plugin[reset_key.get(mechanism, "reset_period_ns")], period)
            self.assertNotIn("enable_qos", config["MemorySystem"]["Controller"])


if __name__ == "__main__":
    unittest.main()
