"""The call to Claude that turns a tour's facts into a short text.

One request per tour, no tools, no conversation. The feature is off unless
``ANTHROPIC_API_KEY`` is set: nothing here runs, and nothing is shown.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import anthropic

MODEL = "claude-sonnet-5-5"

# Bump when the instructions change in a way that should count as different input.
PROMPT_VERSION = 1

# The text is a few sentences; the rest is room for the model's own thinking.
MAX_TOKENS = 4000

# A refusal is unlikely for hiking numbers, but if the model declines, the API
# may answer with the model it falls back to instead of leaving the tour blank.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """\
Du skriver en kort tilbakemelding på en tur for han som gikk den. Han er eneste bruker av \
Yamabiko, en privat app for fjellturer, og leser teksten nederst på turens \
side, under grafene, etter at han har sett kartet og tallene selv.

Du får et JSON-objekt med tall appen har regnet ut. Det er alt du vet om turen. Bruk bare det \
som står der: ikke anslå, ikke regn ut nye tall utover enkle forskjeller, og ikke gjett på vær, \
føre, form eller følelser. Mangler noe (null eller tom liste), nevner du det ikke.

Det han har mest nytte av er det tallene ikke sier av seg selv når de står hver for seg: \
hvordan turen står mot de tidligere turene hans, hvor på et segment tiden ble vunnet eller \
tapt, om han var på nytt terreng, og hvordan året ligger an mot fjoråret. Velg det ene eller \
de to mest interessante poengene og si dem tydelig, heller enn å gå gjennom alt. Er turen helt \
vanlig, er det greit å si det kort.

Noen ting å vite om tallene:
- Tider er i sekunder. Skriv dem som minutter og sekunder (34:06) eller timer og minutter.
- «moving»-tid er uten lange stopp; det er den som sammenlignes mellom turer.
- En plassering er blant hans egne turer på segmentet, ikke mot andre. Med «is_personal_record» \
er dette den raskeste turen hans der.
- Står det noe i «time_uncertain_because», er tiden usikker (GPS-en falt ut, eller sporet var \
bare så vidt innom start- eller målsirkelen). Si da at tiden, og en eventuell rekord, er usikker.
- «against_fastest_pass» sammenligner med den raskeste turen på segmentet, prosent av veien.
- Kartceller er ruter på rundt 300 meter; «never_visited_before» er nytt terreng for ham.

Skriv på norsk bokmål, rett til ham («du»), i en rolig og saklig tone, som en turkamerat som \
har sett på tallene. To til fire setninger, ren tekst uten overskrifter, punktlister eller \
markdown. Ikke si noe om helse, og gi ikke treningsråd.\
"""


class FeedbackUnavailableError(Exception):
    """The model gave no usable text (declined, cut off, or the API failed)."""


def is_enabled() -> bool:
    """Whether an API key is configured; without one the feature is off."""
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def auto_enabled() -> bool:
    """Whether new tours get a text on their own after import (``ACTIVITY_FEEDBACK_AUTO``)."""
    return is_enabled() and os.environ.get("ACTIVITY_FEEDBACK_AUTO", "false").strip().lower() in {"1", "true", "yes"}


def facts_json(facts: dict[str, Any]) -> str:
    """The facts as the model gets them: stable key order, so equal facts are equal text."""
    return json.dumps(facts, ensure_ascii=False, sort_keys=True, indent=1)


def facts_hash(facts: dict[str, Any]) -> str:
    """Identifies the input a text was made from: the facts, the instructions and the model."""
    payload = f"{MODEL}\n{PROMPT_VERSION}\n{facts_json(facts)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def write_feedback(facts: dict[str, Any]) -> str:
    """Ask Claude for the feedback text.

    Args:
        facts: The tour's facts (``activity_feedback.facts.build_facts``).

    Returns:
        The text.

    Raises:
        FeedbackUnavailableError: When there is no usable text. The cause is in the message.
    """
    client = anthropic.Anthropic(timeout=60.0)
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            # A few sentences from a page of numbers: low effort is plenty.
            output_config={"effort": "low"},
            betas=[_FALLBACK_BETA],
            fallbacks="default",
            messages=[{"role": "user", "content": facts_json(facts)}],
        )
    except anthropic.AuthenticationError as err:
        raise FeedbackUnavailableError("the API key was rejected") from err
    except anthropic.RateLimitError as err:
        raise FeedbackUnavailableError("rate limited") from err
    except anthropic.APIStatusError as err:
        raise FeedbackUnavailableError(f"API error {err.status_code}") from err
    except anthropic.APIConnectionError as err:
        raise FeedbackUnavailableError("could not reach the API") from err

    if response.stop_reason == "refusal":
        raise FeedbackUnavailableError("the model declined")
    if response.stop_reason == "max_tokens":
        raise FeedbackUnavailableError("the text was cut off")
    text = "\n".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise FeedbackUnavailableError("the model returned no text")
    return text
