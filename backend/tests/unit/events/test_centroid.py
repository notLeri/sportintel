from sportintel.modules.events.domain.policies.clustering import incremental_centroid


def test_first_vector_is_normalized_and_mean_moves() -> None:
    assert incremental_centroid(None, 0, [3.0, 4.0]) == [0.6, 0.8]
    c = incremental_centroid([1.0, 0.0], 1, [0.0, 1.0])
    assert abs(c[0] - c[1]) < 1e-9
    assert abs(sum(x * x for x in c) - 1) < 1e-9
