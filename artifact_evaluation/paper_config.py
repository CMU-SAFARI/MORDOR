"""Canonical experiment parameters for the final MORDOR paper.

This module is the single source of truth shared by local and Slurm job
generation.  Paper labels retain the nominal :math:`N_RH`, while MORDOR uses
the security margin described in Section 4 of the paper.
"""

from __future__ import annotations

import math


MECHANISMS = ("Hydra", "PARA", "comet", "DAPPER", "graphene", "abacus")
NOMINAL_THRESHOLDS = (125, 250, 500, 1000)
MAIN_INSTRUCTIONS = 10_000_000
LATENCY_INSTRUCTIONS = 100_000_000
MAIN_BRC = 2
MAIN_RADIUS = 1
BLAST_RADII = (2, 4)

LATENCY_GROUPS = {
    "high": (
        "429.mcf", "470.lbm", "random_10.trace", "stream_10.trace",
        "549.fotonik3d",
    ),
}
LATENCY_TRACES = tuple(
    trace for group in LATENCY_GROUPS.values() for trace in group
)

RESET_PERIOD_NS = {
    "Hydra": 32_000_000,
    "DAPPER": 32_000_000,
    "graphene": 32_000_000,
    "abacus": 32_000_000,
    # CoMeT uses k=3 subepochs within the 32 ms DDR5 refresh window.
    "comet": 10_666_667,
}

HYDRA_NOMINAL_TRACKING = {125: 64, 250: 125, 500: 250, 1000: 500}

GRAPHENE_ENTRIES = {
    125: {"priority": 10_377, "mordor": 10_546},
    250: {"priority": 5_189, "mordor": 5_231},
    500: {"priority": 2_595, "mordor": 2_605},
    1000: {"priority": 1_298, "mordor": 1_300},
}
GRAPHENE_RADIUS_ENTRIES = {2: 10_720, 4: 11_087}
GRAPHENE_DRFM_SETUP_ENTRIES = 10_632


def effective_threshold(
    nominal: int,
    scheduler: str,
    *,
    radius: int = MAIN_RADIUS,
    drfm_setup: bool = False,
) -> int:
    """Return the effective threshold used by one generated configuration."""
    if scheduler != "mordor":
        return nominal
    margin = 2 * radius + (1 if drfm_setup else 0)
    threshold = nominal - margin
    if threshold <= 0:
        raise ValueError(
            f"invalid effective threshold: nominal={nominal}, margin={margin}"
        )
    return threshold


def _plugin(config: dict) -> dict:
    plugins = config["MemorySystem"]["Controller"].get("plugins") or []
    if len(plugins) != 1 or "ControllerPlugin" not in plugins[0]:
        raise ValueError("paper configurations require exactly one ControllerPlugin")
    return plugins[0]["ControllerPlugin"]


def apply_paper_parameters(
    config: dict,
    mechanism: str,
    nominal: int,
    scheduler: str,
    *,
    radius: int = MAIN_RADIUS,
    drfm_setup: bool = False,
    instructions: int = MAIN_INSTRUCTIONS,
) -> int:
    """Apply the final-paper parameters and return the effective threshold."""
    if mechanism not in MECHANISMS:
        raise ValueError(f"unknown mechanism: {mechanism}")
    if nominal not in NOMINAL_THRESHOLDS:
        raise ValueError(f"unsupported nominal threshold: {nominal}")
    if scheduler not in {"priority", "mordor", "insecure"}:
        raise ValueError(f"unknown scheduler: {scheduler}")

    parameter_variant = "mordor" if scheduler == "mordor" else "priority"
    effective = effective_threshold(
        nominal, parameter_variant, radius=radius, drfm_setup=drfm_setup
    )

    config["Frontend"]["num_expected_insts"] = instructions
    controller = config["MemorySystem"]["Controller"]
    plugin = _plugin(config)
    plugin["queue_type"] = "priority" if scheduler == "priority" else "read"
    plugin["insecure_read_queue"] = scheduler == "insecure"

    dram = config["MemorySystem"]["DRAM"]
    dram["RFM"] = {"BRC": MAIN_BRC}
    dram["RH_radius"] = radius
    if drfm_setup:
        timing = dram.setdefault("timing", {})
        timing["nDRFMsb"] = 460
        timing["nDRFMab"] = 524

    if mechanism == "Hydra":
        margin = nominal - effective
        plugin["hydra_tracking_threshold"] = (
            HYDRA_NOMINAL_TRACKING[nominal] - math.ceil(margin / 2)
        )
        plugin["hydra_group_threshold"] = math.floor(0.4 * effective)
        plugin["hydra_reset_period_ns"] = RESET_PERIOD_NS[mechanism]
    elif mechanism == "PARA":
        plugin["tRH"] = effective
        plugin["threshold"] = round(
            1.0 - math.pow(1.0e-15, 1.0 / effective), 3
        )
    elif mechanism == "comet":
        plugin["activation_threshold"] = math.ceil(effective / 4)
        plugin["reset_period_ns"] = RESET_PERIOD_NS[mechanism]
    elif mechanism == "DAPPER":
        plugin["tRH"] = effective
        plugin["reset_period_ns"] = RESET_PERIOD_NS[mechanism]
    elif mechanism == "graphene":
        plugin["tRH"] = effective
        plugin["activation_threshold"] = math.ceil(effective / 2)
        if drfm_setup:
            entries = GRAPHENE_DRFM_SETUP_ENTRIES
        elif parameter_variant == "mordor" and radius in GRAPHENE_RADIUS_ENTRIES:
            entries = GRAPHENE_RADIUS_ENTRIES[radius]
        else:
            entries = GRAPHENE_ENTRIES[nominal][parameter_variant]
        plugin["num_table_entries"] = entries
        plugin["reset_period_ns"] = RESET_PERIOD_NS[mechanism]
    elif mechanism == "abacus":
        preventive = effective // 2
        plugin["preventive_refresh_threshold"] = preventive
        plugin["refresh_cycle_threshold"] = preventive - 2
        plugin["reset_period_ns"] = RESET_PERIOD_NS[mechanism]

    return effective


def parameter_manifest(
    mechanism: str,
    nominal: int,
    scheduler: str,
    *,
    radius: int,
    drfm_setup: bool,
    instructions: int,
    cores: int,
) -> dict:
    """Return provenance fields stored beside every generated configuration."""
    return {
        "mechanism": mechanism,
        "scheduler": scheduler,
        "nominal_nrh": nominal,
        "effective_nrh": effective_threshold(
            nominal,
            "mordor" if scheduler == "mordor" else "priority",
            radius=radius,
            drfm_setup=drfm_setup,
        ),
        "brc": MAIN_BRC,
        "blast_radius": radius,
        "drfm_address_setup": drfm_setup,
        "instructions": instructions,
        "cores": cores,
    }
