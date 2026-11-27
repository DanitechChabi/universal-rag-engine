"""Échanges ordinaires reconnus ; toute question sur les documents garde la voie documentaire."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from urag_core.rag import social_intent


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Bonjour", "salutation"),
        ("bonjour !", "salutation"),
        ("Salut, ça va ?", "salutation"),
        ("Hello", "salutation"),
        ("Bonsoir l'assistant", "salutation"),
        ("Merci beaucoup", "remerciement"),
        ("merci, c'est parfait", "remerciement"),
        ("Thanks!", "remerciement"),
        ("Au revoir", "au_revoir"),
        ("Bonne journée", "au_revoir"),
        ("Qui es-tu ?", "presentation"),
        ("Que peux-tu faire pour moi ?", "presentation"),
        ("Comment ça marche ?", "presentation"),
        ("What can you do?", "presentation"),
        ("Comment vas-tu ?", "politesse"),
    ],
)
def test_echanges_ordinaires(message, intent):
    assert social_intent(message) == intent


@pytest.mark.parametrize(
    "message",
    [
        "Bonjour, quel est le taux directeur de la BCEAO ?",
        "Merci, et pour les établissements financiers ?",
        "Qui a signé l'avis n°002-04-2023 ?",
        "Quel est le capital minimum ?",
        "Et sa durée ?",
        "Résume le rapport annuel",
        "Que dit le contrat sur le préavis ?",
    ],
)
def test_questions_documentaires(message):
    assert social_intent(message) is None


def test_aucune_question_d_evaluation_prise_pour_un_echange():
    corpus = Path(__file__).resolve().parents[2] / "eval" / "corpus" / "questions.json"
    questions = json.loads(corpus.read_text(encoding="utf-8"))["questions"]
    assert [q["id"] for q in questions if social_intent(q["question"])] == []
