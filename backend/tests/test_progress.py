from __future__ import annotations

from app.progress import ProgressTracker


def test_progress_tracker_records_steps():
    tracker = ProgressTracker()
    tracker.start("learn charts")
    tracker.step("web-search", "query=candles")
    tracker.step("ollama", "model=qwen2.5:1.5b")
    tracker.finish("ok")
    snap = tracker.snapshot()
    assert snap["busy"] is False
    assert snap["step"] == "done"
    assert any("web-search" in line for line in snap["steps"])
    assert snap["elapsed_seconds"] >= 0


def test_voice_status_includes_progress(client):
    resp = client.get("/voice/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "progress" in data
    assert "step" in data["progress"]
