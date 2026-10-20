"""Run the whole pipeline on synthetic data and verify the accuracy checker catches every planted error.
Usage:  python -m tests.test_pipeline"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline import load_config, run_pipeline  # noqa: E402


def main():
    out = run_pipeline(load_config(), demo=True)
    hh, flags, truth = out["hh"], out["flags"], out["truth"]
    print(f"surveys={len(hh)}  members={len(out['mem'])}  flags={len(flags)}  monitoring={len(out['monitoring'])}")
    ok = True
    print("\nRule      planted  caught  missed")
    for rid, ids in sorted(truth.items()):
        got = set(flags.loc[flags["rule_id"] == rid, "uuid"])
        missed = ids - got
        ok &= not missed
        print(f"{rid:8}  {len(ids):7}  {len(ids & got):6}  {len(missed):6}")
    print("\nFlags by rule (all):")
    print(flags.groupby(["rule_id", "severity"]).size().sort_values(ascending=False).head(25).to_string())
    clean = out["integrity"]
    clean_ok = clean[~clean["uuid"].isin({u for s in truth.values() for u in s})]
    unplanned = flags[~flags["uuid"].isin({u for s in truth.values() for u in s})]
    print(f"\nSurveys with NO planted error: {len(clean_ok)}; unexpected flags on them: {len(unplanned)}")
    print(unplanned.groupby("rule_id").size().to_string() if len(unplanned) else "none")
    print("\nEnumerator confidence (lowest 8):")
    print(out["enumerators"][["enumerator_label", "surveys", "integrity_score", "monitored", "monitoring_score",
                              "confidence_score", "confidence_level"]].head(8).round(1).to_string())
    print("\nRESULT:", "ALL PLANTED ERRORS CAUGHT" if ok else "SOME MISSED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
