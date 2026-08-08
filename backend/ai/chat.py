"""
Chat layer: lets the user ask natural-language questions about their
scraped leads ("which of these need help?", "who has the worst
reviews?") and get an answer grounded in the actual DB rows, rather
than the model guessing.

Approach: pull the current lead list (already sorted/scored by the DB
layer) as compact text, drop it into the system prompt as context, and
let the LLM reason over it conversationally. This is a simple form of
retrieval-augmented generation -- good enough for hundreds of leads;
for thousands you'd want real vector search instead of dumping
everything into context.
"""

from ai.llm_client import LLMUnavailable, chat as llm_chat

SYSTEM_PROMPT_TEMPLATE = """You are a business-development assistant helping the user decide \
which local businesses to pitch marketing/reputation-management services to.

You have the following leads available (already scraped from Google Maps). \
Base every factual claim on this data -- do not invent businesses, ratings, \
or contact details that aren't listed below.

{leads_context}

Answer the user's question conversationally and concisely. When recommending \
specific businesses, name them and give a one-line reason grounded in their \
data (rating, review count, missing website, lead score, etc). If asked something \
the data can't answer, say so plainly instead of guessing.
"""


def format_leads_context(leads: list[dict], max_leads: int = 60) -> str:
    """leads: list of dicts with name, category, rating, review_count,
    website, lead_score, lead_score_reason, status."""
    lines = []
    for lead in leads[:max_leads]:
        lines.append(
            f"- {lead.get('name')} | category: {lead.get('category') or 'n/a'} "
            f"| rating: {lead.get('rating', 'n/a')} ({lead.get('review_count', 'n/a')} reviews) "
            f"| website: {'yes' if lead.get('website') else 'no'} "
            f"| lead_score: {lead.get('lead_score', 'not scored')} "
            f"| status: {lead.get('status', 'new')}"
        )
    if len(leads) > max_leads:
        lines.append(f"... and {len(leads) - max_leads} more leads not shown here.")
    return "\n".join(lines) if lines else "(no leads scraped yet)"


def answer(user_message: str, history: list[dict], leads: list[dict]) -> str:
    """
    history: prior turns as [{"role": "user"/"assistant", "content": "..."}]
    leads: current lead rows to ground the answer in
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(leads_context=format_leads_context(leads))
    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": user_message}
    ]
    try:
        return llm_chat(messages, temperature=0.5)
    except LLMUnavailable as e:
        return (
            "I can't reach the local AI model right now, so I can't answer that "
            f"conversationally. ({e})\n\nIn the meantime, your leads are still "
            "browsable via GET /leads sorted by lead_score."
        )
