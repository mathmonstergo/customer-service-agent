from customer_service_agent.db import format_vector, score_to_distance


def test_format_vector_outputs_pgvector_literal():
    assert format_vector([0.1, -0.2, 3]) == "[0.1,-0.2,3.0]"


def test_score_to_distance_converts_similarity_threshold():
    assert score_to_distance(0.35) == 0.65
