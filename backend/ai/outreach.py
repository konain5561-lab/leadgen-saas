"""
Outreach generator: drafts a personalized email or WhatsApp message
pitching business-development/marketing services to a specific lead,
grounded in that lead's actual scraped data (rating, review count,
missing website, etc.) and its lead_score_reason if available.

Compliance note: the generated email template includes a plain-text
sign-off placeholder and assumes YOU fill in your business name /
unsubscribe details before sending at scale -- cold email laws
(CAN-SPAM, GDPR, etc.) generally require sender identification and an
opt-out mechanism. This generator drafts pitch content; it doesn't
handle legal compliance for you.
"""

from ai.llm_client import LLMUnavailable, generate

EMAIL_SYSTEM_PROMPT = (
    "You write short, non-salesy cold outreach emails from a marketing/"
    "business-development agency to local businesses. Tone: friendly, "
    "specific, respectful of their time -- not hypey, no exclamation-mark "
    "spam, no generic flattery. Reference one concrete, real detail about "
    "their business (rating, review count, lack of website, etc.) to prove "
    "this isn't a mass blast. Keep the email under 120 words. End with a "
    "low-pressure call to action (e.g. 'worth a quick chat?'), not a hard "
    "sell. Output ONLY the email body text -- no subject line, no markdown, "
    "no placeholders like [Your Name] left unresolved except a single "
    "'- [Your Name]' sign-off line at the very end."
)

WHATSAPP_SYSTEM_PROMPT = (
    "You write short, casual WhatsApp outreach messages from a marketing/"
    "business-development freelancer/agency to local business owners. "
    "Keep it under 50 words, conversational, no corporate tone, one "
    "specific concrete detail about their business, end with a soft "
    "question inviting a reply. No emojis unless they fit naturally. "
    "Output ONLY the message text."
)

FALLBACK_EMAIL_TEMPLATE = """Hi {name} team,

I came across {name} on Google Maps{detail_clause}. I help local businesses \
like yours improve their online presence and bring in more customers through \
better marketing and reputation management.

Would you be open to a quick chat this week to see if it's a fit?

- [Your Name]"""

FALLBACK_WHATSAPP_TEMPLATE = (
    "Hi! I noticed {name} on Google Maps{detail_clause}. "
    "I help local businesses grow through marketing/reputation management -- "
    "worth a quick chat?"
)


def _detail_clause(business: dict) -> str:
    rating = business.get("rating")
    review_count = business.get("review_count")
    has_website = bool(business.get("website"))
    if not has_website:
        return " and noticed you don't have a website linked yet"
    if rating is not None and rating < 4.0:
        return f" and saw your rating sits around {rating}"
    if review_count is not None and review_count < 10:
        return " and noticed you don't have many reviews yet"
    return ""


def generate_outreach(business: dict, channel: str) -> dict:
    """
    business: dict with name, category, rating, review_count, website,
              lead_score_reason (optional)
    channel: "email" or "whatsapp"

    Returns: {"subject": str|None, "body": str, "source": "llm"|"template"}
    """
    name = business.get("name", "there")
    detail = _detail_clause(business)

    context = (
        f"Business name: {name}\n"
        f"Category: {business.get('category') or 'unknown'}\n"
        f"Rating: {business.get('rating', 'n/a')} ({business.get('review_count', 'n/a')} reviews)\n"
        f"Has website: {'yes' if business.get('website') else 'no'}\n"
        f"Why this business was flagged as a lead: {business.get('lead_score_reason') or 'general prospect'}\n"
    )

    try:
        if channel == "email":
            body = generate(context + "\nWrite the outreach email now.", system=EMAIL_SYSTEM_PROMPT, temperature=0.6)
            subject = f"Quick idea for {name}"
            return {"subject": subject, "body": body, "source": "llm"}
        else:
            body = generate(context + "\nWrite the WhatsApp message now.", system=WHATSAPP_SYSTEM_PROMPT, temperature=0.6)
            return {"subject": None, "body": body, "source": "llm"}
    except LLMUnavailable:
        # Deterministic fallback so the feature still works with Ollama offline.
        if channel == "email":
            body = FALLBACK_EMAIL_TEMPLATE.format(name=name, detail_clause=detail)
            return {"subject": f"Quick idea for {name}", "body": body, "source": "template"}
        else:
            body = FALLBACK_WHATSAPP_TEMPLATE.format(name=name, detail_clause=detail)
            return {"subject": None, "body": body, "source": "template"}
