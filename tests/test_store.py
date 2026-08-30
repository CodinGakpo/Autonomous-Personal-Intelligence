"""Tests for the entity-graph store: idempotent upserts and edges (the persistence guarantee)."""

from brain import store


def _conn(tmp_path):
    return store.connect(tmp_path / "t.db")


def _person(name, email):
    return {"name": name, "assignee": email, "headline": f"{name} the engineer"}


def test_upsert_creates(tmp_path):
    conn = _conn(tmp_path)
    res, pid = store.upsert(conn, "person", _person("Sai Prakash", "sai@x.com"),
                            title="Sai Prakash", summary="s", source="f")
    assert res.action == "create"
    assert store.get(conn, pid)["title"] == "Sai Prakash"


def test_reupsert_same_updates_not_duplicates(tmp_path):
    conn = _conn(tmp_path)
    _, first = store.upsert(conn, "person", _person("Sai Prakash", "sai@x.com"),
                            title="Sai Prakash", summary="v1", source="f")
    res, second = store.upsert(conn, "person", _person("Sai Prakash", "sai@x.com"),
                               title="Sai Prakash", summary="v2", source="f")
    assert res.action == "update"
    assert second == first                                   # same node, not a new one
    assert len(store.all_of_type(conn, "person")) == 1       # no duplicate row
    assert store.get(conn, first)["summary"] == "v2"         # latest write wins


def test_distinct_person_creates_second_node(tmp_path):
    conn = _conn(tmp_path)
    store.upsert(conn, "person", _person("Sai Prakash", "sai@x.com"),
                 title="Sai Prakash", summary="s", source="f")
    store.upsert(conn, "person", _person("Pruthvik Jadhav", "pru@x.com"),
                 title="Pruthvik Jadhav", summary="s", source="f")
    assert len(store.all_of_type(conn, "person")) == 2


def test_edges_and_neighbors_are_directional(tmp_path):
    conn = _conn(tmp_path)
    _, pid = store.upsert(conn, "person", _person("Sai Prakash", "sai@x.com"),
                          title="Sai Prakash", summary="s", source="f")
    _, tid = store.upsert(conn, "task", {"name": "Ship it", "assignee": "Sai"},
                          title="Ship it", summary="d", source="f")
    store.add_edge(conn, tid, pid, "assigned_to")
    # incoming assigned_to on the person surfaces the task; outgoing on the person does not.
    assert [n["id"] for n in store.neighbors(conn, pid, "assigned_to", incoming=True)] == [tid]
    assert store.neighbors(conn, pid, "assigned_to") == []


def test_add_edge_is_idempotent(tmp_path):
    conn = _conn(tmp_path)
    _, pid = store.upsert(conn, "person", _person("Sai Prakash", "sai@x.com"),
                          title="Sai Prakash", summary="s", source="f")
    _, tid = store.upsert(conn, "task", {"name": "Ship it", "assignee": "Sai"},
                          title="Ship it", summary="d", source="f")
    store.add_edge(conn, tid, pid, "assigned_to")
    store.add_edge(conn, tid, pid, "assigned_to")
    count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    assert count == 1
