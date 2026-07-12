def test_control_session_requires_shared_true(client):
    denied = client.post(
        "/control/sessions",
        json={"shared": False, "purpose": "Fill invoice form", "allow_write": False},
    )
    assert denied.status_code == 403

    accepted = client.post(
        "/control/sessions",
        json={"shared": True, "purpose": "Fill invoice form", "allow_write": False},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "active"


def test_control_assist_generates_response(client):
    session = client.post(
        "/control/sessions",
        json={"shared": True, "purpose": "Draft customer reply", "allow_write": False},
    ).json()

    assist = client.post(
        f"/control/sessions/{session['id']}/assist",
        json={
            "task": "email_draft",
            "instruction": "Write a polite follow-up email.",
            "screen_context": "Customer asked for deployment timeline and status update.",
        },
    )
    assert assist.status_code == 200
    body = assist.json()
    assert body["session_id"] == session["id"]
    assert body["task"] == "email_draft"
    assert len(body["response"]) > 0


def test_control_action_write_permission_and_approval_flow(client):
    readonly = client.post(
        "/control/sessions",
        json={"shared": True, "purpose": "Read form", "allow_write": False},
    ).json()

    denied_action = client.post(
        "/control/actions",
        json={
            "session_id": readonly["id"],
            "action_type": "submit_form",
            "target": "checkout submit",
            "payload": "{\"confirm\":true}",
        },
    )
    assert denied_action.status_code == 403

    writable = client.post(
        "/control/sessions",
        json={"shared": True, "purpose": "Fill form", "allow_write": True},
    ).json()

    action = client.post(
        "/control/actions",
        json={
            "session_id": writable["id"],
            "action_type": "submit_form",
            "target": "checkout submit",
            "payload": "{\"confirm\":true}",
        },
    )
    assert action.status_code == 200
    action_id = action.json()["id"]

    approve = client.post(f"/control/actions/{action_id}/decision", json={"approve": True})
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    execute = client.post(f"/control/actions/{action_id}/execute")
    assert execute.status_code == 200
    assert execute.json()["status"] == "executed"
