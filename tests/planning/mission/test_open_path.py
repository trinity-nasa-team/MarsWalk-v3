"""Misión solo de ida (016): no se cuenta el regreso al inicio."""

from marsmap.planning.mission.encoding import tour_time, two_opt


def test_tour_time_open_path_skips_return():
    tm = [[0, 1, 9], [1, 0, 1], [9, 1, 0]]
    assert tour_time((1, 2), tm) == 1 + 1 + 9
    assert tour_time((1, 2), tm, open_path=True) == 2


def test_two_opt_open_path_prefers_ending_far():
    # inicio 0; ir a 1 (cerca) y luego a 2 (lejos) es mejor solo-ida; en ida y vuelta da igual.
    tm = [[0, 1, 5], [1, 0, 1], [5, 1, 0]]
    assert two_opt((2, 1), tm, open_path=True) == (1, 2)
