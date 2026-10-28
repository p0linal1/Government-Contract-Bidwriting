"""Offline tests for how the server keeps Doug's answers. Nothing here calls Cloud Storage."""

import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import answers  # noqa: E402


def test_only_the_exact_code_opens_the_answers(monkeypatch):
    monkeypatch.setenv("DOUG_ANSWERS_CODE", "right-code")
    assert answers.code_matches("right-code")
    assert not answers.code_matches("wrong-code")
    assert not answers.code_matches("")


def test_no_code_on_the_server_opens_nothing(monkeypatch):
    monkeypatch.delenv("DOUG_ANSWERS_CODE", raising=False)
    assert not answers.code_matches("")
    assert not answers.configured()


def test_a_save_that_loses_a_race_reads_again_and_keeps_both_answers(monkeypatch):
    stored = {"answers": {"range": {"choice": "Per year"}}, "generation": 1}
    attempts = []

    def read():
        return dict(stored["answers"]), stored["generation"]

    def write(new_answers, generation):
        attempts.append(generation)
        if len(attempts) == 1:
            # Another save lands between this save's read and its write.
            stored["answers"]["va"] = {"choice": "Yes"}
            stored["generation"] = 2
            raise urllib.error.HTTPError("url", 412, "Precondition Failed", {}, None)
        stored["answers"] = new_answers
        stored["generation"] = generation + 1

    monkeypatch.setattr(answers, "read", read)
    monkeypatch.setattr(answers, "write", write)
    answers.save("military", {"choice": "No"})

    assert attempts == [1, 2]
    assert stored["answers"]["range"] == {"choice": "Per year"}
    assert stored["answers"]["va"] == {"choice": "Yes"}
    assert stored["answers"]["military"]["choice"] == "No"
