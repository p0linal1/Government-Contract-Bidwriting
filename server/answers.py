"""Doug's answers to the agent's questions, kept in one private Cloud Storage object.

They include his rates and insurance, and the app has no login, so only a request carrying the
code from Doug's private link may read or change them. On Cloud Run the server's own service
account reaches the bucket, so no storage key exists anywhere.
"""

import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

TOKEN_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
STORAGE = "https://storage.googleapis.com"
OBJECT = "answers.json"
# A write that loses a race with another write reads again and retries, at most this many times.
WRITE_ATTEMPTS = 3


def configured():
    return bool(os.environ.get("DOUG_ANSWERS_CODE") and os.environ.get("ANSWERS_BUCKET"))


def code_matches(code):
    expected = os.environ.get("DOUG_ANSWERS_CODE", "")
    return bool(expected) and hmac.compare_digest(code.encode(), expected.encode())


def access_token():
    request = urllib.request.Request(TOKEN_URL, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(request, timeout=5) as reply:
        return json.load(reply)["access_token"]


def read():
    """The saved answers and the object's generation. Generation 0 means nothing is saved yet."""
    bucket = os.environ["ANSWERS_BUCKET"]
    url = f"{STORAGE}/storage/v1/b/{bucket}/o/{OBJECT}?alt=media"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token()}"})
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            return json.load(reply), int(reply.headers["x-goog-generation"])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}, 0
        raise


def write(answers, generation):
    """Replaces the object only if it is still at `generation`, so two saves never overwrite each other."""
    bucket = os.environ["ANSWERS_BUCKET"]
    query = urllib.parse.urlencode({"uploadType": "media", "name": OBJECT, "ifGenerationMatch": generation})
    request = urllib.request.Request(
        f"{STORAGE}/upload/storage/v1/b/{bucket}/o?{query}",
        data=json.dumps(answers, indent=2).encode(),
        headers={"Authorization": f"Bearer {access_token()}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10):
        pass


def save(question_id, answer):
    """Saves one question's answer and returns when it was saved."""
    saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for attempt in range(WRITE_ATTEMPTS):
        answers, generation = read()
        answers[question_id] = {**answer, "savedAt": saved_at}
        try:
            write(answers, generation)
            return saved_at
        except urllib.error.HTTPError as error:
            if error.code != 412 or attempt == WRITE_ATTEMPTS - 1:
                raise
