"""Endpoint de misiones solo de ida (016)."""


def test_open_path_returns_only_outbound_legs(client, habitat):
    body = {
        "habitat": habitat,
        "open_path": True,
        "pop_size": 20,
        "n_generations": 10,
        "max_radius_m": 100000,
    }
    r = client.post("/api/regions/jezero/missions", json=body)
    assert r.status_code == 200
    seqs = [m for m in r.json()["front"] if m["sequence"]]
    assert seqs
    for m in seqs:
        assert len(m["legs"]) == len(m["sequence"])  # sin tramo de regreso
        assert m["legs"][-1]["to"] != "habitat"
