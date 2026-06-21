"""
guardrails.py — the input scope gate + output validator that wrap the LLM.

Where this sits in the pipeline (see main.chatbot_endpoint):

    bot.handle_message() could not classify the message  ->  intent == "fallback"
        |
        v
    is_in_scope()        -> is this even about our company/transport?
        |  no  -> return kb.REFUSAL  (the LLM is NEVER called)
        |  yes
        v
    llm_smart_reply()    -> the Groq model answers
        |
        v
    validate_output()    -> did it invent a price / promise a service we don't offer?
        |  violation -> replace with a safe canned message
        |  clean     -> show as-is

The point: the rules the small (8B) model is unreliable at — never quote a
price, never promise air/sea/rail or non-produce cargo — are enforced here in
CODE, not merely requested in the prompt.
"""

import re
import chatbot as bot   # reuse normalize() + the entity extractors
import kb


# Pre-compute a flat, normalized vocabulary set once at import (fast lookups).
_VOCAB = set()
for _d in (kb.SERVICES_VOCAB, kb.DOMAIN_VOCAB):
    for _lg in _d:
        for _w in _d[_lg]:
            _VOCAB.add(bot.normalize(_w))

_MARKERS = [bot.normalize(_m) for _m in kb.OUT_OF_SCOPE_MARKERS]


def _norm(text: str) -> str:
    return bot.normalize(text or "")


# ---------------------------------------------------------------------------
# INPUT GATE
# ---------------------------------------------------------------------------
def is_in_scope(text, available_cities, available_products, lang="en"):
    """Decide whether an unclassified message is about the app at all.

    Returns (in_scope: bool, signals: list[str]).

    We let the message reach the LLM ONLY when we find at least one domain
    signal: a known city, a known product, a weight, or a logistics keyword.
    A strong off-topic marker (e.g. "weather", "capital of") refuses outright,
    even if a network city happens to be mentioned.
    """
    n = _norm(text)
    if not n:
        return False, []

    # 0) Hard off-topic markers win immediately (strict scope, as requested).
    for m in _MARKERS:
        if m and m in n:
            return False, [f"offtopic:{m}"]

    signals = []

    # 1) Real entities from the live app data (strongest signal).
    pickup, dest = bot.extract_cities(text, available_cities)
    if pickup or dest:
        signals.append("city")
    if bot.extract_product(text, available_products):
        signals.append("product")
    if bot.extract_weight(text) is not None:
        signals.append("weight")

    # 2) Services / domain vocabulary (any supported language).
    for kw in _VOCAB:
        if kw and kw in n:
            signals.append("vocab")
            break

    return (len(signals) > 0, signals)


# ---------------------------------------------------------------------------
# OUTPUT VALIDATOR
# ---------------------------------------------------------------------------
# A number glued to a currency token, in either order ("1500 MAD" / "€20").
_PRICE_RE = re.compile(
    r"\d[\d.,\s]*\s*(?:mad|dhs?|dirhams?|درهم|€|eur|euros?|\$|usd|dollars?)"
    r"|(?:mad|dhs?|dirhams?|درهم|€|eur|euros?|\$|usd|dollars?)\s*\d",
    re.IGNORECASE,
)
# A per-unit rate without a currency ("10 per kg", "3/pallet").
_PER_UNIT_RE = re.compile(
    r"\d[\d.,\s]*\s*(?:/|per |par |por )\s*(?:kg|kilo|kilos|tonne|ton|palette|pallet)",
    re.IGNORECASE,
)
# A specific operational figure the model must not invent: a percentage
# (deposit), a temperature, or a transit duration. Exact values come from the
# deterministic FAQ / quote engine, not the LLM.
_FACT_NUM_RE = re.compile(
    r"\d+\s*%"
    r"|\d+\s*(?:°|degrees?|degr[ée]s?|grados?|درجة|درجات)"
    r"|\d+\s*(?:hours?|hrs?|days?|heures?|jours?|d[ií]as?|horas?|ساعة|ساعات|يوم|[أا]يام)",
    re.IGNORECASE,
)

# If a reply names an out-of-network place but ALSO frames it as a refusal
# ("we don't serve X", "only ...", "outside our network"), it's a correct answer,
# not a hallucination — these markers stop us from mangling a valid refusal.
_REFUSAL_MARKERS = [
    "not", "n't", "do not", "cannot", "only", "outside", "unfortunately", "sorry",
    "ne ", "pas", "n'", "seulement", "uniquement", "hors", "desole",
    "no ", "solo", "unicamente", "fuera", "lo siento",
    "لا", "ليس", "فقط", "خارج", "عذرا",
]

def _has_refusal_marker(n: str) -> bool:
    return any(m in n for m in _REFUSAL_MARKERS)


def validate_output(reply, available_cities, available_products, lang="en"):
    """Check an LLM reply before showing it.

    Returns (clean_reply, violations). On a hard violation we DROP the model's
    text and return a safe canned message instead.
    """
    violations = []
    if not reply:
        return reply, violations

    n = _norm(reply)

    # 1) Invented price -> deflect to the real quote engine.
    if _PRICE_RE.search(reply) or _PER_UNIT_RE.search(reply):
        violations.append("price")
        return kb.PRICE_DEFLECTION.get(lang, kb.PRICE_DEFLECTION["en"]), violations

    # 2) Promised a transport mode we don't run.
    for kw in kb.UNSUPPORTED_MODES:
        if _norm(kw) in n:
            violations.append(f"mode:{kw}")
            break
    # 3) Mentioned cargo we don't carry.
    for kw in kb.UNSUPPORTED_CARGO:
        if _norm(kw) in n:
            violations.append(f"cargo:{kw}")
            break
    # 4) Affirmatively named a place we don't serve (without framing it as a
    #    refusal) -> likely an invented route. Correct refusals are preserved.
    if not _has_refusal_marker(n):
        for place in kb.FOREIGN_PLACES:
            pn = _norm(place)
            if pn and bot._word_in(pn, n):
                violations.append(f"unlisted_place:{place}")
                break

    if violations:
        return kb.REFUSAL.get(lang, kb.REFUSAL["en"]), violations

    # 5) Stated a specific operational figure it shouldn't invent (deposit %,
    #    temperature, transit duration) -> defer to the authoritative source.
    if _FACT_NUM_RE.search(reply):
        return kb.FACT_DEFLECTION.get(lang, kb.FACT_DEFLECTION["en"]), ["fact_number"]

    return reply, violations
