"""Detect pipeline faults using one documented tool call per event."""
from api import Verdict


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def check_data_batch(payload, ctx):
    profile = ctx.tools.batch_profile(payload["batch_id"])
    if "error" in profile:
        return Verdict(alert=True, pillar="checks", reason=profile["error"])
    baseline = ctx.baseline
    reasons = []
    rows = profile["row_count"]
    mean = profile["mean_amount"]
    null = profile["null_rate"]["customer_id"]
    stale = profile["staleness_min"]
    if rows < baseline["row_count_min"]:
        reasons.append("volume_drop")
    if rows > baseline["row_count_max"]:
        reasons.append("volume_spike")
    if null > baseline["null_rate_max"]:
        reasons.append("null_spike")
    if not baseline["mean_amount_min"] <= mean <= baseline["mean_amount_max"]:
        reasons.append("distribution_shift")
    if stale > baseline["staleness_min_max"]:
        reasons.append("freshness_lag")

    # Normalize by each published 3-sigma half-range, matching the 1.30 cutoff.
    row_mid = (baseline["row_count_min"] + baseline["row_count_max"]) / 2
    row_radius = (baseline["row_count_max"] - baseline["row_count_min"]) / 2
    mean_mid = (baseline["mean_amount_min"] + baseline["mean_amount_max"]) / 2
    mean_radius = (baseline["mean_amount_max"] - baseline["mean_amount_min"]) / 2
    distance_squared = (
        ((rows - row_mid) / row_radius) ** 2
        + ((mean - mean_mid) / mean_radius) ** 2
        + (null / baseline["null_rate_max"]) ** 2
        + (stale / baseline["staleness_min_max"]) ** 2
    )
    if distance_squared > 1.30 ** 2:
        reasons.append("multi_signal_shift")
    return Verdict(alert=bool(reasons), pillar="checks", reason=", ".join(reasons))


def check_contract_checkpoint(payload, ctx):
    diff = ctx.tools.contract_diff(payload["contract_id"], payload["checkpoint_batch_id"])
    if "error" in diff:
        return Verdict(alert=True, pillar="contracts", reason=diff["error"])
    reasons = list(diff["violations"])
    sla = payload.get("declared_sla", {}).get(
        "freshness_min", ctx.baseline["freshness_delay_max_min"]
    )
    if diff["freshness_delay_min"] > min(sla, ctx.baseline["freshness_delay_max_min"]):
        reasons.append("sla_violation")
    return Verdict(alert=bool(reasons), pillar="contracts", reason=", ".join(reasons))


def check_lineage_run(payload, ctx):
    graph = ctx.tools.lineage_graph_slice(payload["run_id"])
    if "error" in graph:
        return Verdict(alert=True, pillar="lineage", reason=graph["error"])
    reasons = []
    if graph["actual_downstream_count"] == 0:
        reasons.append("orphan_output")
    missing = {"raw.orders", "raw.customers"} - set(graph["actual_upstream"])
    if missing:
        reasons.append("missing_upstream: " + ", ".join(sorted(missing)))
    if graph["duration_ms"] > ctx.baseline["lineage_duration_ms_max"]:
        reasons.append("runtime_anomaly")
    return Verdict(alert=bool(reasons), pillar="lineage", reason=", ".join(reasons))


def check_feature_materialization(payload, ctx):
    drift = ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    if "error" in drift:
        return Verdict(alert=True, pillar="ai_infra", reason=drift["error"])
    # Clean serving variation reaches 0.472 sigma; observed skew starts at 0.970.
    if drift["mean_shift_sigma"] > 0.65:
        return Verdict(alert=True, pillar="ai_infra", reason="training_serving_skew")
    return Verdict(alert=False, pillar="ai_infra")


def check_embedding_batch(payload, ctx):
    drift = ctx.tools.embedding_drift(payload["corpus"], payload["chunk_batch_id"])
    if "error" in drift:
        return Verdict(alert=True, pillar="ai_infra", reason=drift["error"])
    reasons = []
    if drift["centroid_shift"] > 0.040:
        reasons.append("embedding_drift")
    if drift["avg_doc_age_days"] > 45:
        reasons.append("corpus_staleness")
    return Verdict(alert=bool(reasons), pillar="ai_infra", reason=", ".join(reasons))
