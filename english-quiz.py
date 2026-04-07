import anthropic
import json
import os
import random
import requests
from puzzle import ts
from dotenv import load_dotenv

# Load secrets from .env for local testing
load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

CATEGORIES = [
    "idioms",
    "phrasal verbs",
    "vocabulary",
    "verb tenses",
    "prepositions",
    "slang",
    "grammar"
]


def generate_quiz(category):
    """Generate a quiz using the Anthropic API."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Generate a {category} English quiz suitable for B1-level adult learners.

The quiz should:
- Have a clean, unambiguous problem statement and 5 questions about English {category} or the chosen sub-theme
- Be challenging but doable with reasonable confidence
- Have a specific answer to each question
- Be humorous, interesting, or surprising at times (not required)
- Keep the answer concise and significantly under 1500 characters
- If multiple choice, ensure the answers are not all the same letter (e.g., not all answer choice A)
- Provide a response consistent with Discord formatting:
   - *italics* **bold** ***bold italics*** __underscore__ etc. 

Only finalize the questions if the answers are unambiguous and meet all criteria.

Respond in this exact JSON format with no other text:
{{
"problems": "the problem set here",
"answers": "the concise answers",
"insight": "more details of the answers or an insight related to the questions or theme"
}}"""
    message = client.messages.create(
        # model="claude-sonnet-4-6",
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text
    # Strip markdown code blocks if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:-1])
    # print(f"Raw response:\n{raw}") # DEBUG
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Context: {raw[max(0,e.pos-50):e.pos+50]}")
        raise


def post_to_discord(message):
    """Post a message to Discord via webhook."""
    payload = {"content": message, "username": "Daily English Quiz"}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    response.raise_for_status()


def main():
    # Step 1: Generate today's quiz
    category = random.choice(CATEGORIES)
    print(f"[{ts()}] Generating {category} quiz")
    quiz_data = generate_quiz(category)

    # Step 2: Post today's quiz
    print(f"[{ts()}] Posting today's quiz")
    quiz_message = (
        f"📚 **Daily English Quiz — {category.title()}**\n\n"
        f"{quiz_data['problems']}\n\n"
        f"*Think you know the answers? Share below and check the answers!*"
    )
    post_to_discord(quiz_message)

    # Step 3: Post the answers and insight separately from the problems
    print(f"[{ts()}] Posting the answers")
    if "answers" in quiz_data:
        answer_message = (
            f"💡 **Answers to the {category.title()} Quiz:**\n\n"
            f"||{quiz_data['answers']}||\n"
            f"*Please verify the answers with an English Helper*"
        )
        # append insight if available
        if "insight" in quiz_data:
            insight = quiz_data['insight']
            if len(insight) > 1500:
                insight = insight[:1500] + "\n*(truncated)*"
            insight_message = (
                f"🤔 **Did You Know?**\n{insight}"
            )
            answer_message = answer_message + "\n\n" + insight_message
        # append joke if available
        # if "joke" in quiz_data:
        #     joke = quiz_data['joke']
        #     if len(joke) > 1500:
        #         joke = joke[:1500] + "\n*(truncated)*"
        #     joke_message = (
        #         f"🎉 **Joke Time**\n{joke}"
        #     )
        #     answer_message = answer_message + "\n\n" + joke_message
        # print(f"Answer message:\n{answer_message}") # DEBUG
        post_to_discord(answer_message)
    print(f"[{ts()}] Done!")


if __name__ == "__main__":
    main()