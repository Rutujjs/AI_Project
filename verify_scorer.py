import sys, os
sys.path.insert(0, os.path.abspath('AI_ESG_Platform/backend'))
from app.green.scorer import calculate_score, DIMENSION_WEIGHTS, SEVERITY_PENALTY

def verify_scorer_mathematics():
    print("=================================================================")
    print("  AREA 4: GREEN SCORE AND ESG IMPACT MATHEMATICAL VERIFICATION")
    print("=================================================================\n")

    # 1. Weight Sum Verification
    print("[TEST 4.1] Verifying Dimension Weights Sum to Exactly 1.0:")
    total_weight = sum(DIMENSION_WEIGHTS.values())
    print(f"  Dimension Weights: {DIMENSION_WEIGHTS}")
    print(f"  Sum of Weights: {total_weight:.4f}")
    assert abs(total_weight - 1.0) < 1e-6, "Weights must sum to 1.0!"
    print("  --> Result: PASSED (Exact 1.00)\n")

    # 2. Perfect Score
    print("[TEST 4.2] Verifying Perfect Score (0 findings):")
    res_clean = calculate_score([])
    print(f"  Score with 0 findings: {res_clean['overall_score']}")
    assert res_clean['overall_score'] == 100.0
    for dim, score in res_clean['dimension_scores'].items():
        assert score == 100.0
    print("  --> Result: PASSED (All dimensions 100.0)\n")

    # 3. Testing each individual dimension penalty
    print("[TEST 4.3] Verifying Individual Dimension Impact:")
    dims = list(DIMENSION_WEIGHTS.keys())
    for d in dims:
        w = DIMENSION_WEIGHTS[d]
        # 1 High finding in dimension d should subtract 15 from d, reducing overall by 15 * w
        finding = [{"severity": "high", "category": d}]
        res = calculate_score(finding)
        dim_score = res['dimension_scores'][d]
        expected_dim = 85.0
        expected_overall = round(100.0 - (15.0 * w), 1)
        print(f"  - Dimension '{d}' (weight {w}): dim_score={dim_score} (exp: {expected_dim}), overall={res['overall_score']} (exp: {expected_overall})")
        assert dim_score == expected_dim
        assert res['overall_score'] == expected_overall
    print("  --> Result: PASSED for all 7 dimensions\n")

    # 4. Consistency & Determinism
    print("[TEST 4.4] Verifying Deterministic Consistency:")
    test_set = [
        {"severity": "high", "category": "network"},
        {"severity": "medium", "category": "database"},
        {"severity": "low", "category": "compute"},
        {"severity": "high", "category": "memory"},
        {"severity": "medium", "category": "cicd"},
    ]
    scores = [calculate_score(test_set)['overall_score'] for _ in range(20)]
    assert len(set(scores)) == 1, "The score must be 100% deterministic!"
    print(f"  Calculated 20 times: all scores identically = {scores[0]}")
    print("  --> Result: PASSED (100% Deterministic)\n")

    # 5. Clamping & Worst-Case Scenario
    print("[TEST 4.5] Verifying Clamping to [0.0, 100.0]:")
    worst_case = [{"severity": "high", "category": d} for d in dims for _ in range(10)]
    res_worst = calculate_score(worst_case)
    print(f"  Score with 70 high-severity findings: {res_worst['overall_score']}")
    assert res_worst['overall_score'] == 0.0
    for dim, score in res_worst['dimension_scores'].items():
        assert score == 0.0, f"Dimension {dim} should clamp to 0.0!"
    print("  --> Result: PASSED (Strictly clamped to 0.0)\n")

    print("=================================================================")
    print("  GREEN SCORE MATHEMATICAL VERIFICATION: ALL CHECKS PASSED")
    print("=================================================================")

if __name__ == '__main__':
    verify_scorer_mathematics()

