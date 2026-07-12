from __future__ import annotations

from fastapi.testclient import TestClient


def test_runtime_status(client: TestClient):
    resp = client.get("/runtime/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["uptime_seconds"] >= 0
    assert data["started_at"] is not None
    assert data["heartbeat_count"] == 0


def test_manual_heartbeat(client: TestClient):
    resp = client.post("/runtime/heartbeat")
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["uptime_seconds"] >= 0

    status = client.get("/runtime/status").json()
    assert status["heartbeat_count"] == 1
    assert status["last_heartbeat"] is not None


def test_multiple_heartbeats_tracked(client: TestClient):
    client.post("/runtime/heartbeat")
    client.post("/runtime/heartbeat")
    client.post("/runtime/heartbeat")

    resp = client.get("/runtime/heartbeats")
    assert resp.status_code == 200
    beats = resp.json()
    assert len(beats) == 3
    assert beats[0]["uptime_seconds"] <= beats[2]["uptime_seconds"]


def test_runtime_status_after_heartbeats(client: TestClient):
    client.post("/runtime/heartbeat")
    client.post("/runtime/heartbeat")

    status = client.get("/runtime/status").json()
    assert status["heartbeat_count"] == 2
    assert status["status"] == "running"
