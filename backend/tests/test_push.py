from tests.test_records import act, new_sub, site, submit  # noqa: F401


def test_push_subscribe_and_send(client, site, monkeypatch):
    import app.core.push as push
    sent = []
    monkeypatch.setattr(push, "webpush", lambda info, data, **kw: sent.append((info["endpoint"], data)))
    key = client.get("/api/v1/push/key", headers=site["hce"]).json()["public_key"]
    assert len(key) > 80
    sub = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "BPk" + "x" * 80, "auth": "authkey123"}}
    assert client.post("/api/v1/push/subscribe", headers=site["hce"], json=sub).status_code == 204
    assert client.get("/api/v1/push/status", headers=site["hce"]).json()["devices"] == 1
    # a request submitted for the civil engineer is pushed to his browser
    submit(client, site, new_sub(client, site))
    assert sent and sent[-1][0] == "https://push.example.com/abc" and "بانتظار ردك" in sent[-1][1]
    assert client.post("/api/v1/push/unsubscribe", headers=site["hce"], json={"endpoint": sub["endpoint"]}).status_code == 204
    assert client.get("/api/v1/push/status", headers=site["hce"]).json()["devices"] == 0
