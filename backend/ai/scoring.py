"""
Lead scoring: "does this business need business-development help?"

Two layers, on purpose:

1. Rule-based signals (cheap, deterministic, always available) -- low
   rating, few reviews, no website, etc. These alone are enough to
   rank leads even if the LLM is down.
2. An LLM pass on top that turns those signals into a 0-100 score and
   a short human-readable reason, the way a person skimming the list
   would explain their gut call.

If Ollama isn't reachable, scoring falls back to the rule-based score
alone rather than failing outright.
"""

from dataclasses import dataclass

from ai.llm_client import LLMUnavailable, extract_json, generate

SYSTEM_PROMPT = (
    "You are a business-development analyst. Given data about a local "
    "business scraped from Google Maps, judge how much that business "
    "likely needs marketing / reputation-management / business-development "
    "help, and how good a prospect it is for an agency selling those "
    "services. Respond with ONLY a JSON object, no other text, no markdown "
    'fences: {"score": <integer 0-100>, "reason": "<one short sentence>"}. '
    "Higher score = better prospect (needs help AND seems reachable/viable). "
    "A business with no online presence at all, or clearly closed/defunct, "
    "is a weak prospect even if their rating is bad -- there may be no one "
    "to sell to. The best prospects are active, real businesses whose "
    "online presence is visibly neglected or underperforming."
)


@dataclass
class RuleSignals:
    rule_score: int
    signals: list[str]


def compute_rule_signals(rating: float | None, review_count: int | None, has_website: bool) -> RuleSignals:
    """Cheap deterministic scoring used as a floor / fallback, and as
    context fed into the LLM prompt."""
    score = 50
    signals = []

    if rating is not None:
        if rating < 3.5:
            score += 25
            signals.append(f"low rating ({rating})")
        elif rating < 4.0:
            score += 12
            signals.append(f"mediocre rating ({rating})")
        elif rating >= 4.7:
            score -= 15
            signals.append(f"already excellent rating ({rating})")

    if review_count is not None:
        if review_count < 5:
            score += 10
            signals.append(f"very few reviews ({review_count})")
        elif review_count < 20:
            score += 5
            signals.append(f"low review count ({review_count})")
        elif review_count > 500:
            score -= 10
            signals.append(f"already high review volume ({review_count})")

    if not has_website:
        score += 15
        signals.append("no website listed")

    score = max(0, min(100, score))
    return RuleSignals(rule_score=score, signals=signals)


def score_business(business: dict) -> dict:
    """
    business: dict with keys name, category, rating, review_count,
              address, website (any may be None/missing).

    Returns: {"score": int, "reason": str, "source": "llm" | "rules_only"}
    """
    rules = compute_rule_signals(
        rating=business.get("rating"),
        review_count=business.get("review_count"),
        has_website=bool(business.get("website")),
    )

    prompt = (
        f"Business: {business.get('name')}\n"
        f"Category: {business.get('category') or 'unknown'}\n"
        f"Rating: {business.get('rating') if business.get('rating') is not None else 'no rating'}\n"
        f"Review count: {business.get('review_count') if business.get('review_count') is not None else 'unknown'}\n"
        f"Has a website: {'yes' if business.get('website') else 'no'}\n"
        f"Address: {business.get('address') or 'unknown'}\n"
        f"Preliminary rule-based signals: {', '.join(rules.signals) or 'none notable'}\n\n"
        "Score this lead."
    )

    try:
        raw = generate(prompt, system=SYSTEM_PROMPT, temperature=0.3)
        parsed = extract_json(raw)
        score = int(parsed["score"])
        reason = str(parsed["reason"]).strip()
        score = max(0, min(100, score))
        return {"score": score, "reason": reason, "source": "llm"}
    except (LLMUnavailable, ValueError, KeyError, TypeError):
        # Fall back to the deterministic score so the feature still
        # works with Ollama offline -- just less nuanced.
        reason = "Rule-based only (LLM unavailable): " + (", ".join(rules.signals) or "no strong signals")
        return {"score": rules.rule_score, "reason": reason, "source": "rules_only"}
