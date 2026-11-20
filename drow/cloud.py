"""Supabase Storage for client uploads (cloud mode).

The browser uploads each file straight to Supabase with a one-time signed
URL, so big photos never pass through the web server (Vercel only accepts
requests up to 4.5 MB). The team views files through short-lived signed
download links. Only the standard library is used."""

import json
import urllib.error
import urllib.parse
import urllib.request


class SupabaseStorage:
    def __init__(self, url, service_key, bucket="drow-uploads"):
        self.base = url.rstrip("/") + "/storage/v1"
        self.key = service_key
        self.bucket = bucket
        self._bucket_ready = False

    def _call(self, method, path, body=None):
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if not self.key.startswith("sb_"):  # legacy service_role JWT also goes in Authorization
            headers["Authorization"] = f"Bearer {self.key}"
        req = urllib.request.Request(
            self.base + path, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
        return json.loads(raw) if raw else {}

    @staticmethod
    def _q(path):
        return urllib.parse.quote(path, safe="/")

    def ensure_bucket(self):
        """Create the private bucket on first use (ignored if it already exists)."""
        if self._bucket_ready:
            return
        try:
            self._call("POST", "/bucket", {"id": self.bucket, "name": self.bucket, "public": False})
        except urllib.error.HTTPError as e:
            if b"exists" not in e.read():  # "BucketAlreadyExists" is fine
                raise
        self._bucket_ready = True

    def signed_upload_url(self, path):
        self.ensure_bucket()
        res = self._call("POST", f"/object/upload/sign/{self.bucket}/{self._q(path)}", {})
        return self.base + res["url"]

    def signed_download_url(self, path, seconds=300):
        res = self._call("POST", f"/object/sign/{self.bucket}/{self._q(path)}", {"expiresIn": seconds})
        return self.base + res["signedURL"]

    def delete(self, paths):
        if paths:
            self._call("DELETE", f"/object/{self.bucket}", {"prefixes": list(paths)})
