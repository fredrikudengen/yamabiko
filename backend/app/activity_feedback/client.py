"""The call to Claude that turns a tour's facts into a short text.

One request per tour, no tools, no conversation. The feature is off unless
``ANTHROPIC_API_KEY`` is set: nothing here runs, and nothing is shown.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Final

import anthropic

MODEL = "claude-sonnet-5-5"

# Bump when the instructions change in a way that should count as different input.
# 2: tell a story instead of listing numbers; segment history, pulse per climb, milestones.
# 3: no reasons read into the tour, no talk of missing data, one paragraph.
# 4: heart-rate counts only where comparable, no source fields; never more than four sentences.
# 5: time lost per half given outright.
PROMPT_VERSION = 5

# The text is a few sentences; the rest is room for the model's own thinking.
MAX_TOKENS = 8000

# Medium rather than low: picking the one thing worth saying is the hard part.
EFFORT: Final = "medium"

# A refusal is unlikely for hiking numbers, but if the model declines, the API
# may answer with the model it falls back to instead of leaving the tour blank.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# The app's languages (``users.preferred_language``) and how the prompt names them.
LANGUAGES = {"nb": "Norwegian Bokmål", "en": "English"}
DEFAULT_LANGUAGE = "nb"

SYSTEM_PROMPT = """\
You write a short note about one hike for the person who walked it. They are the only user of \
Yamabiko, a private app for their own hikes and mountain walks. They read your note at the very \
bottom of the tour's page, after they have already looked at the map, the charts, the segment \
table and every number on it.

So do not repeat the numbers back to them. Your job is to notice what the numbers mean together \
and tell them that, the way a hiking friend who knows all their earlier tours would after a quick \
look. Find the one thing about this tour that is most worth saying, and say it well. A second \
point is fine if it really adds something; a list of observations is not.

Where to look for it, roughly in order of how interesting it tends to be:
- Form: on a segment, beats_per_100m_climbed against the same count on earlier passes (it is \
only given where the two can be compared). The same time at a lower count, or a faster time \
at the same count, means they are fitter. A higher count on a slow day may just mean a hard day.
- A trend in earlier_passes_newest_first: getting faster pass by pass, the first time under a \
round time, the fastest this year, back on a segment after a long break (days_since_previous_pass).
- How the pass went along the way (against_fastest_pass_so_far): lost early or late, held the \
pace to halfway and dropped off after. Say it as a picture of the climb, not as percentages.
- The tour among their own tours this year (compared_with_your_other_tours), a long gap since \
the previous tour, a lot of new ground.
- The year, only when year.milestones is not empty. Otherwise leave the year out entirely.

What the numbers mean:
- Times are seconds; write them as 34:06 or 1 h 12 min. Moving time leaves out long stops and is \
what is compared between tours.
- Ranks and records are among their own passes only, as they stood on the day of this tour.
- time_uncertain_because not empty: the time may be off (GPS dropped out, or the track only \
touched the edge of the start or finish circle). If you mention that time, or a record it \
sets, say briefly that it is uncertain. Earlier passes have time_uncertain the same way.
- Squares are a grid of about 300 m used for the map of where they have been.

Use only what is in the JSON, and do not work out new numbers beyond simple differences. Never \
explain why something went the way it did: not from the weather, the company, the tour's name \
or anything else you might read between the lines. Say what happened, not why. Do not mention \
what is missing or what cannot be compared (no heart rate, a different heart-rate source): \
just leave that topic out. Nothing about health, and no training advice. If nothing stands \
out, one plain, friendly sentence saying it was a solid, ordinary tour is better than \
inventing something.

Write in {language}, to them directly ("du" in Norwegian, "you" in English), warm and a little \
personal, but not gushing: no exclamation marks, no superlatives the numbers do not earn. One \
paragraph of two to four sentences, never more, and at most two or three numbers in all. Plain text: no \
headings, lists or markdown. Use the segment and place names as they are written.\
"""


def system_prompt(language: str) -> str:
    """The instructions, asking for the text in the app's language."""
    return SYSTEM_PROMPT.format(language=LANGUAGES.get(language, LANGUAGES[DEFAULT_LANGUAGE]))


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


def facts_hash(facts: dict[str, Any], language: str = DEFAULT_LANGUAGE) -> str:
    """Identifies the input a text was made from: the facts, language, instructions and model."""
    payload = f"{MODEL}\n{PROMPT_VERSION}\n{language}\n{facts_json(facts)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def write_feedback(facts: dict[str, Any], language: str = DEFAULT_LANGUAGE) -> str:
    """Ask Claude for the feedback text.

    Args:
        facts: The tour's facts (``activity_feedback.facts.build_facts``).
        language: The app language to write in (``nb`` or ``en``).

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
            system=system_prompt(language),
            output_config={"effort": EFFORT},
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
