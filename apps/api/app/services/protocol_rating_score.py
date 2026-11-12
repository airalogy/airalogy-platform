"""Deterministic trial recommendation. This is a product heuristic, not certification."""

from collections import Counter, defaultdict
from math import log1p

ALGORITHM = "protocol-rating-v1-trial"
POLICY = {
    "minimum_reviewers": 3,
    "prior_score": 3,
    "prior_weight": 3,
    "reviewers_per_lab_cap": 5,
    "uses_per_lab_cap": 3,
    "use_cap": 20,
    "reuse_cap": 5,
    "rating_points": 90,
    "adoption_points": 10,
}


def recommendation(
    ratings: list[dict], uses_by_lab: dict[str, int], reuse_labs: list[str]
) -> dict:
    """Input contains only eligible, permission-filtered, deduplicated facts."""
    groups = defaultdict(list)
    users = set()
    distribution = {str(i): 0 for i in range(1, 6)}
    for rating in ratings:
        score = rating["score"]
        if type(score) is not int or not 1 <= score <= 5:
            raise ValueError("Rating must be an integer from 1 to 5")
        if rating["user_id"] in users:
            raise ValueError("Duplicate reviewer")
        users.add(rating["user_id"])
        groups[rating["lab_id"]].append(score)
        distribution[str(score)] += 1
    if any(type(n) is not int or n < 0 for n in uses_by_lab.values()):
        raise ValueError("Use counts must be non-negative integers")
    count = len(ratings)
    weighted_count = sum(min(len(g), 5) for g in groups.values())
    weighted_sum = sum(sum(g) / len(g) * min(len(g), 5) for g in groups.values())
    posterior = (weighted_sum + 9) / (weighted_count + 3)
    quality = (posterior - 1) / 4
    bounded_uses = min(sum(min(n, 3) for n in uses_by_lab.values()), 20)
    bounded_reuse = min(len(set(reuse_labs)), 5)
    adoption = (log1p(bounded_uses) / log1p(20) + log1p(bounded_reuse) / log1p(5)) / 2
    rating_points = 90 * quality
    adoption_points = 10 * adoption * quality
    score = round(rating_points + adoption_points, 1) if count >= 3 else None
    return {
        "algorithm": ALGORITHM,
        "policy": POLICY.copy(),
        "status": "available" if score is not None else "insufficient_evidence",
        "score": score,
        "rating_count": count,
        "rating_average": round(sum(r["score"] for r in ratings) / count, 2)
        if count
        else None,
        "distribution": distribution,
        "components": {
            "rating_points": round(rating_points, 4),
            "adoption_points": round(adoption_points, 4),
            "posterior_rating": round(posterior, 6),
            "effective_reviewers": weighted_count,
            "bounded_uses": bounded_uses,
            "bounded_reuse_labs": bounded_reuse,
        },
        # An anonymous calculation basis, sufficient to reproduce the result.
        "basis": {
            "rating_groups": sorted(
                [dict(sorted(Counter(g).items())) for g in groups.values()], key=str
            ),
            "uses_per_lab": sorted(uses_by_lab.values()),
            "reuse_lab_count": len(set(reuse_labs)),
        },
    }
