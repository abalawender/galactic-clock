#!/usr/bin/env python3
"""Mint the Spotify refresh token via a local PKCE callback server (host-side).

The board (main.py) is a *public* Spotify client -- it holds no client
secret, only the client id plus the long-lived refresh token. A public
client cannot do the plain authorization-code grant, so the one-time browser
login uses **PKCE**: a per-run random ``code_verifier`` is hashed into a
``code_challenge`` in the authorize URL, and the same verifier is sent back
in the token exchange. The board can't do this browser login, so the mint
happens here on the host: a small HTTP server on 127.0.0.1 catches
Spotify's redirect (``?code=...``), exchanges the code for the refresh_token
right there, and prints it. This script never reads or writes secrets.py
(do that by hand).
The callback server binds 127.0.0.1, so the ``--redirect-uri`` registered
on the app must be on that host (e.g. ``http://127.0.0.1:8888/callback``).

    python3 scripts/spotify_auth.py \
        --client-id ID --redirect-uri http://127.0.0.1:8888/callback

Open the printed authorize URL in your browser, log in, and approve. On the
Spotify redirect the server exchanges the code and prints
``SPOTIFY_CLIENT_ID`` / ``SPOTIFY_REFRESH_TOKEN`` -- copy those into the
board's secrets.py. The access token is short-lived; the board mints its
own from the refresh token.

The Spotify app must be a *public* (no client secret) client for this flow
to work; a confidential app needs the classic secret-based grant instead.

The authorization ``code`` is time-limited (Spotify does not document the
exact window; it is short) and single-use, so complete the browser login
promptly. Stdlib only (http.server, urllib, urllib.parse).

    --client-id ID      your Spotify app's client id (required)
    --redirect-uri URI  must exactly match a redirect URI registered on the
                        app (default http://127.0.0.1:8888/callback)
    --port N            listen port (default: port of --redirect-uri)
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
import time
import urllib.parse
import urllib.request
from typing import cast

TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTHORIZE = "https://accounts.spotify.com/authorize"
SCOPE = "user-read-currently-playing"
DEFAULT_REDIRECT = "http://127.0.0.1:8888/callback"
WAIT_SECONDS = 300


def _b64url(n):
    """n random bytes -> a base64url string (no padding), for PKCE."""
    return base64.urlsafe_b64encode(os.urandom(n)).rstrip(b"=").decode()


def _pkce_challenge(verifier):
    """S256 challenge: base64url(SHA256(verifier)), no padding."""
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def authorize_url(client_id, redirect_uri, challenge):
    """The browser login URL with the PKCE challenge attached."""
    return "%s?%s" % (AUTHORIZE, urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }))


def exchange(code, client_id, redirect_uri, code_verifier):
    """Authorization-code + PKCE grant -> the token JSON (dict w/
    refresh_token). Public client: no client_secret; a code_verifier is
    required (a public client can't exchange a code any other way)."""
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


class _MintServer(http.server.HTTPServer):
    """The callback server, carrying the per-run exchange context that the
    handler reads via ``self.server`` (set in main(), before the wait)."""

    verifier: str
    client_id: str
    redirect_uri: str
    exit_code: int


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """One-shot GET handler. A callback (``?code=`` / ``?error=``) is
    exchanged on the spot and closes the listener; any other GET (no code in
    the query) gets an empty 200 and the wait continues."""

    def do_GET(self):
        params = dict(urllib.parse.parse_qsl(
            urllib.parse.urlparse(self.path).query))
        if "code" not in params and "error" not in params:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"")
            return  # no code in the query -- keep waiting
        s = cast(_MintServer, self.server)  # the per-run exchange context
        if "error" in params:
            note = params["error"]
            if params.get("error_description"):
                note += " (%s)" % params["error_description"]
            print("Spotify returned an error: %s (check the app's "
                  "registered redirect URI matches --redirect-uri)" % note)
            s.exit_code = 1
            body = "<html><body><h2>Spotify auth error</h2><p>%s</p></body></html>" \
                % (params["error"] or "unspecified")
        else:
            try:
                tok = exchange(params["code"], s.client_id, s.redirect_uri,
                               s.verifier)
            except Exception as e:
                print("token exchange failed: %s" % e)
                s.exit_code = 1
                tok = None
            if tok is not None and "refresh_token" in tok:
                print("\n=== copy these (they go in secrets.py on the board) ===")
                print('SPOTIFY_CLIENT_ID = "%s"' % s.client_id)
                print('SPOTIFY_REFRESH_TOKEN = "%s"' % tok["refresh_token"])
                print("(access_token is short-lived; the board mints its own "
                      "from the refresh token)")
            else:
                print("no refresh_token in token exchange response")
                s.exit_code = 1
            body = ("<html><body><h2>Spotify now-playing</h2>"
                    "<p>Refresh token minted - you can close this tab.</p>"
                    "</body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))
        s.server_close()  # close the listener: main() then exits

    def log_message(self, format, *args):
        pass  # silence BaseHTTPRequestHandler access log


def main():
    ap = argparse.ArgumentParser(
        description="Mint a Spotify refresh token via a local PKCE callback "
                    "server (prints it; writes nothing).")
    ap.add_argument("--client-id", required=True,
                    help="your Spotify app's client id")
    ap.add_argument("--redirect-uri", default=DEFAULT_REDIRECT,
                    help="must exactly match a redirect URI registered on "
                         "the app")
    ap.add_argument("--port", type=int, default=None,
                    help="listen port (default: port of --redirect-uri)")
    args = ap.parse_args()

    if args.port is None:
        args.port = urllib.parse.urlparse(args.redirect_uri).port or 8888

    # PKCE: one verifier per run; its S256 challenge goes in the authorize
    # URL and the verifier is sent back in the token exchange.
    verifier = _b64url(32)
    challenge = _pkce_challenge(verifier)

    print("callback server listening on 127.0.0.1:%d  (redirect: %s)"
          % (args.port, args.redirect_uri))
    print("\nOpen this in your browser, log in to Spotify, and approve:\n  %s\n"
          % authorize_url(args.client_id, args.redirect_uri, challenge))
    print("waiting up to %ds for the Spotify redirect..." % WAIT_SECONDS)

    # One-shot: Spotify's 302 redirect hits the callback exactly once, so a
    # single handle_request() suffices. With server.timeout = WAIT_SECONDS it
    # blocks (select) that whole window; on idle timeout it returns with the
    # listener still open (server.socket is not None), which we read as "timed
    # out". No loop, no retry bookkeeping.
    server = _MintServer(("127.0.0.1", args.port), _CallbackHandler)
    server.timeout = WAIT_SECONDS
    # per-run exchange context, read by the handler via self.server:
    server.verifier = verifier
    server.client_id = args.client_id
    server.redirect_uri = args.redirect_uri
    server.exit_code = 0
    with server:
        server.handle_request()

    # A received code/error has the handler call server_close() (socket ->
    # None); an idle timeout leaves the listener open. So "socket is None"
    # means the redirect arrived and the token was minted.
    if server.socket is None:
        return server.exit_code
    print("timed out after %ds (no redirect received); re-run and complete "
          "the login promptly" % WAIT_SECONDS)
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())