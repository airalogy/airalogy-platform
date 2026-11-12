"""Boundary examples for the documented trial policy; no scientific claims."""

import math

import pytest

from app.services.protocol_rating_score import recommendation


def ratings(scores, labs=None):
    return [
        {
            "user_id": str(i),
            "lab_id": (labs or ["one"] * len(scores))[i],
            "score": score,
        }
        for i, score in enumerate(scores)
    ]


def test_cold_start_and_unknown_are_not_zero_or_full_score():
    for scores in ([], [5], [5, 5]):
        result = recommendation(ratings(scores), {"one": 10000}, ["two"])
        assert result["score"] is None
    assert recommendation([], {}, [])["rating_average"] is None


def test_raw_rating_is_separate_from_popularity_and_authors_are_filtered_upstream():
    reviews = ratings([2, 3, 4])
    small = recommendation(reviews, {}, [])
    large = recommendation(
        reviews, {str(i): 10000 for i in range(100)}, [str(i) for i in range(100)]
    )
    assert small["rating_average"] == large["rating_average"] == 3
    assert large["score"] - small["score"] <= 10
    assert large["components"]["bounded_uses"] == 20
    assert large["components"]["bounded_reuse_labs"] == 5


def test_a_single_lab_cannot_dominate_by_volume():
    reviews = ratings([5] * 20)
    low = recommendation(reviews, {"one": 3}, ["two"])
    high = recommendation(reviews, {"one": 100000}, ["two", "two"])
    assert low["score"] == high["score"]
    assert low["components"] == high["components"]

    assert recommendation(reviews, {}, [])["components"]["effective_reviewers"] == 5
    many = recommendation(ratings([5] * 20, list(map(str, range(20)))), {}, [])
    assert many["components"]["effective_reviewers"] == 20


def test_negative_feedback_is_not_erased_by_high_adoption():
    bad = recommendation(
        ratings([1] * 100, [str(i) for i in range(100)]),
        {str(i): 99999 for i in range(100)},
        [str(i) for i in range(100)],
    )
    assert bad["score"] < 10
    assert recommendation(ratings([5] * 3), {}, [])["score"] > bad["score"]


@pytest.mark.parametrize(
    "value", [0, 6, -1, True, 3.5, float("nan"), float("inf"), "5"]
)
def test_invalid_rating_never_enters_math(value):
    with pytest.raises(ValueError):
        recommendation(ratings([value]), {}, [])


@pytest.mark.parametrize("value", [-1, True, 1.2, math.nan, math.inf])
def test_invalid_counts_are_rejected(value):
    with pytest.raises(ValueError):
        recommendation([], {"one": value}, [])


def test_bounds_distribution_determinism_and_diminishing_returns():
    for score in range(1, 6):
        for count in range(3, 20):
            result = recommendation(ratings([score] * count), {"one": count}, ["two"])
            assert 0 <= result["score"] <= 100
            assert sum(result["distribution"].values()) == count
            assert result == recommendation(
                ratings([score] * count), {"one": count}, ["two"]
            )
    review = ratings([4, 5, 4])
    points = [
        recommendation(review, {"one": n}, [])["components"]["adoption_points"]
        for n in range(4)
    ]
    assert points[1] - points[0] > points[2] - points[1] > points[3] - points[2]
    with pytest.raises(ValueError):
        recommendation([ratings([4])[0]] * 3, {}, [])
