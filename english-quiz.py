import anthropic
import json
import os
import random
from dotenv import load_dotenv
from shared import ts, parse_json_response, post_to_discord_safe

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

BOT_NAME = "Daily English Quiz"


def generate_quiz(category):
    """Generate an English quiz using the Anthropic API.
    
    Args:
        category: Quiz category (e.g., "idioms", "phrasal verbs")
        
    Returns:
        dict: Contains 'problems', 'answers', and 'insight'
        
    Raises:
        json.JSONDecodeError: If response cannot be parsed as JSON
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Generate a {category} English quiz suitable for B1-level adult learners.

The quiz should:
- Have a clean, unambiguous problem statement with exactly 5 questions about English {category} or the chosen sub-theme
- Be challenging but doable with reasonable confidence
- Have a specific, unambiguous answer to each question
- Be humorous, interesting, or surprising at times (not required, but appreciated)
- Keep the answers concise and significantly under 1500 characters combined
- If using multiple choice, randomize the correct answer positions so that they are different letters (vary answer positions on at least 3)
- Use Discord formatting: *italics* **bold** ***bold italics*** __underscore__ etc. where appropriate
- Never include unescaped double quotes in string values; use single quotes or rephrase instead

Only finalize the questions if the answers are unambiguous and meet all criteria above.

Respond in this exact JSON format with no other text:
{{
"problems": "the problem set here with 5 questions",
"answers": "the concise answers to all 5 questions, clearly numbered",
"insight": "interesting details about the answers, or a broader insight related to the theme"
}}"""
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text
    return parse_json_response(raw)


def main():
    # Step 1: Generate today's quiz
    category = random.choice(CATEGORIES)
    print(f"[{ts()}] Generating {category} quiz")
    
    try:
        quiz_data = generate_quiz(category)
    except json.JSONDecodeError as e:
        print(f"[{ts()}] Failed to generate quiz: {e}")
        post_to_discord_safe(
            "⚠️ Daily English Quiz encountered an error generating today's quiz. Please try again later.",
            BOT_NAME,
            DISCORD_WEBHOOK_URL
        )
        return
    except Exception as e:
        print(f"[{ts()}] Unexpected error during quiz generation: {e}")
        post_to_discord_safe(
            "⚠️ Daily English Quiz encountered an unexpected error. Please try again later.",
            BOT_NAME,
            DISCORD_WEBHOOK_URL
        )
        return

    # Step 2: Post today's quiz
    print(f"[{ts()}] Posting today's quiz")
    quiz_message = (
        f"📚 **Daily English Quiz — {category.title()}**\n\n"
        f"{quiz_data['problems']}\n\n"
        f"*Think you know the answers? Share below and check the answers!*"
    )
    
    if not post_to_discord_safe(quiz_message, BOT_NAME, DISCORD_WEBHOOK_URL):
        print(f"[{ts()}] Error: Failed to post quiz (payload too long). Aborting.")
        return

    # Step 3: Post the answers and insight separately from the problems
    print(f"[{ts()}] Posting the answers and insight")
    
    answers = quiz_data.get("answers", "N/A")
    insight = quiz_data.get("insight", "")
    
    # Validate insight length
    if len(insight) > 1500:
        insight = insight[:1500] + "\n*(truncated)*"
    
    answer_message = (
        f"💡 **Answers to the {category.title()} Quiz:**\n\n"
        f"||{answers}||\n\n"
        f"*Please verify the answers with an English helper or native speaker*"
    )
    
    # Append insight if available
    if insight:
        insight_message = (
            f"🤔 **Did You Know?**\n\n"
            f"{insight}"
        )
        # Check combined length before appending
        combined = answer_message + "\n\n" + insight_message
        if len(combined) <= 2000:
            answer_message = combined
        else:
            # Post separately if too long
            if not post_to_discord_safe(answer_message, BOT_NAME, DISCORD_WEBHOOK_URL):
                print(f"[{ts()}] Warning: Failed to post answer message")
            if not post_to_discord_safe(insight_message, BOT_NAME, DISCORD_WEBHOOK_URL):
                print(f"[{ts()}] Warning: Failed to post insight message")
            print(f"[{ts()}] Done!")
            return
    
    if not post_to_discord_safe(answer_message, BOT_NAME, DISCORD_WEBHOOK_URL):
        print(f"[{ts()}] Warning: Failed to post answer and insight message")
    
    print(f"[{ts()}] Done!")


if __name__ == "__main__":
    main()