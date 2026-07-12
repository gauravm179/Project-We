def test_sos_trigger_locks_non_safety_endpoints(client):
    trigger = client.post("/safety/sos/trigger", json={"reason": "Immediate shutdown requested"})
    assert trigger.status_code == 200
    trigger_body = trigger.json()
    assert trigger_body["emergency_stop_active"] is True
    assert trigger_body["sos_non_removable"] is True

    chat = client.post("/chat", json={"message": "hello after sos"})
    assert chat.status_code == 423

    controls = client.get("/control/sessions")
    assert controls.status_code == 423


def test_safety_status_still_available_after_sos(client):
    client.post("/safety/sos/trigger", json={"reason": "Stop all activity"})
    status = client.get("/safety/status")
    assert status.status_code == 200
    body = status.json()
    assert body["emergency_stop_active"] is True
    assert body["sos_non_removable"] is True
