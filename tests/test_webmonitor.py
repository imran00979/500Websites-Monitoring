import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from webmonitor.checks import CheckResult, check_site, classify, normalize_url
from webmonitor.monitor import Monitor, Settings
from webmonitor.server import make_handler
from webmonitor.store import Store

PAGES = {
    "/ok": (200, "<html><head><title>Acme</title></head><body><h1>Welcome to Acme</h1>"
                 "<p>We build things for people every single day.</p></body></html>"),
    "/blank": (200, "<html><head><title>x</title></head><body>  </body></html>"),
    "/empty": (200, ""),
    "/spa": (200, '<html><body><div id="root"></div><script src="/app.js"></script></body></html>'),
    "/image-only": (200, '<html><body><img src="/hero.jpg"></body></html>'),
    "/missing": (404, "<html><body><h1>Not Found</h1></body></html>"),
    "/soft404": (200, "<html><head><title>Page not found</title></head>"
                      "<body><p>Sorry, we could not find that page.</p></body></html>"),
    "/500": (500, "<html><body><h1>Internal Server Error</h1></body></html>"),
    "/502": (502, "<html><body>Bad Gateway</body></html>"),
    "/wpdb": (500, "<html><body><h1>Error establishing a database connection</h1></body></html>"),
    "/sqlstate": (200, "<html><body>SQLSTATE[HY000] [2002] Connection refused</body></html>"),
    "/wpcrit": (200, "<html><body><p>There has been a critical error on this website."
                     "</p></body></html>"),
    "/phpfatal": (200, "<html><body><b>Fatal error</b>: Uncaught Error: Call to undefined "
                       "function foo() in /var/www/index.php on line 12</body></html>"),
    "/forbidden": (403, "<html><body>Forbidden</body></html>"),
    "/sql-article": (200, "<html><body><h1>Debugging MySQL</h1><p>"
                          + "If you see SQLSTATE[HY000] errors, check your credentials. " * 80
                          + "</p></body></html>"),
}


class FakeSite(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        code, body = PAGES.get(self.path.split("?")[0], (404, "nope"))
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def base():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeSite)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.mark.parametrize("path,status", [
    ("/ok", "ok"),
    ("/blank", "blank"),
    ("/empty", "blank"),
    ("/spa", "blank"),
    ("/image-only", "ok"),
    ("/missing", "not_found"),
    ("/soft404", "not_found"),
    ("/500", "http_500"),
    ("/502", "server_error"),
    ("/wpdb", "db_error"),
    ("/sqlstate", "db_error"),
    ("/wpcrit", "internal_error"),
    ("/phpfatal", "internal_error"),
    ("/forbidden", "http_error"),
    ("/sql-article", "ok"),
])
def test_check_site_classifies(base, path, status):
    res = check_site(base + path, timeout=5, retries=0)
    assert res.status == status, res.detail
    assert res.ip == "127.0.0.1"


def test_spa_is_flagged_as_js_shell(base):
    res = check_site(base + "/spa", timeout=5, retries=0)
    assert res.js_shell and "JavaScript" in res.detail


def test_wp_db_error_keeps_500_as_secondary_issue(base):
    res = check_site(base + "/wpdb", timeout=5, retries=0)
    assert res.issues[:2] == ["db_error", "http_500"]


def test_dns_failure():
    res = check_site("https://no-such-host.invalid/", timeout=5, retries=0)
    assert res.status == "dns_error"


def test_connection_refused():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    res = check_site(f"http://127.0.0.1:{port}/", timeout=3, retries=0)
    assert res.status == "down"


def test_normalize_url():
    assert normalize_url("Example.COM") == "https://example.com/"
    assert normalize_url("http://a.b/x?y=1") == "http://a.b/x?y=1"
    assert normalize_url("# comment") is None
    assert normalize_url("") is None
    assert normalize_url("word") is None
    assert normalize_url("ftp://a.b/") is None


def test_classify_status_codes_without_body():
    r = CheckResult(url="x")
    classify(503, "", r)
    assert r.status == "server_error"


def test_monitor_run_and_dashboard_api(base, tmp_path):
    store = Store(tmp_path / "m.db")
    added, rejected = store.add_sites([f"{base}/ok", f"{base}/500", f"{base}/ok", "not a url"])
    assert added == 2
    mon = Monitor(store, Settings(workers=4, timeout=5, retries=0))
    counts = mon.run_once()
    assert counts == {"ok": 1, "http_500": 1}
    mon.run_once()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, mon, None))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_port}"
        state = json.load(urllib.request.urlopen(url + "/api/state"))
        by_url = {s["url"]: s for s in state["sites"]}
        assert by_url[f"{base}/500"]["last_status"] == "http_500"
        assert by_url[f"{base}/500"]["fail_streak"] == 2
        assert by_url[f"{base}/ok"]["recent"] == ["ok", "ok"]
        assert by_url[f"{base}/ok"]["uptime_24h"] == 100.0
        assert len(state["runs"]) == 2
        csv_text = urllib.request.urlopen(url + "/api/export.csv").read().decode("utf-8-sig")
        assert "http_500" in csv_text
        html = urllib.request.urlopen(url + "/").read().decode()
        assert "Website Monitor" in html
    finally:
        srv.shutdown()


def test_dashboard_password(base, tmp_path):
    store = Store(tmp_path / "m.db")
    mon = Monitor(store, Settings())
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, mon, "s3cret"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_port}/api/state"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url)
        assert exc.value.code == 401
        req = urllib.request.Request(url, headers={"Authorization": "Basic YWRtaW46czNjcmV0"})
        assert urllib.request.urlopen(req).status == 200
    finally:
        srv.shutdown()


def test_alert_sent_after_consecutive_failures(base, tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr("webmonitor.monitor.requests.post",
                        lambda url, json, timeout: sent.append(json["text"]))
    store = Store(tmp_path / "m.db")
    store.add_sites([f"{base}/500"])
    mon = Monitor(store, Settings(workers=2, timeout=5, retries=0, alert_after=2,
                                  webhook_url="http://hook"))
    mon.run_once()
    assert sent == []
    mon.run_once()
    assert len(sent) == 1 and "/500" in sent[0]
    mon.run_once()
    assert len(sent) == 1
