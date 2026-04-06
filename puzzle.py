import anthropic
import json
import os
import random
import requests
from datetime import date
from dotenv import load_dotenv

# Load secrets from .env for local testing
load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GIST_ID = os.environ["GIST_ID"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

CATEGORIES = [
    "probability",
    "geometry",
    "logic",
    "calculus",
    "statistics",
    "number theory",
]


def get_gist():
    """Read yesterday's puzzle state from GitHub Gist."""
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    content = response.json()["files"]["puzzle_state.json"]["content"]
    return json.loads(content)


def update_gist(data):
    """Write today's puzzle state to GitHub Gist."""
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    payload = {
        "files": {
            "puzzle_state.json": {
                "content": json.dumps(data, indent=2)
            }
        }
    }
    response = requests.patch(url, headers=headers, json=payload)
    response.raise_for_status()


def generate_puzzle(category):
    """Generate a puzzle using the Anthropic API."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Generate a {category} puzzle suitable for someone with an engineering background who enjoys math puzzles for fun.

The puzzle should:
- Be challenging but solvable in 5-15 minutes
- Have a clean, unambiguous problem statement
- Have a specific numerical or concise answer
- Be interesting or have a surprising result if possible
- Never approximate irrational numbers — leave answers in exact form (e.g. 16 + 8√2)
- Accept non-clean answers if that is the correct result — do not force a clean answer
- Keep solution_steps concise and under 1500 characters total
- Ensure all JSON strings are properly escaped — never use unescaped double quotes inside string values, use single quotes or rephrase instead

Solve the puzzle using one method, then verify using a second independent method.
Only finalize the puzzle if both methods agree exactly.

Respond in this exact JSON format with no other text:
{{
"puzzle": "the problem statement here",
"solution_steps": "the step-by-step working shown openly, no final answer here",
"solution_answer": "one concise line stating the final answer"
}}"""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text
    # Strip markdown code blocks if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:-1])
    # print(f"Raw response:\n{raw}") # DEBUG
    # DEBUG: Putting the return in a try/except catch because sometimes the load brings back
    #        characters that can't be parsed, but then when I rerun it's already changed, so this
    #        except block prints the parsing error before terminating the run
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Context: {raw[max(0,e.pos-50):e.pos+50]}")
        # Attempt to fix common issues: unescaped quotes inside strings
        # This is a last resort — add to prompt instead
        raise


def post_to_discord(message):
    """Post a message to Discord via webhook."""
    payload = {"content": message, "username": "Brainy"}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    response.raise_for_status()


def main():
    today = str(date.today())

    # Step 1: Read yesterday's state from GitHub Gist
    print("Reading previous puzzle state from Gist")
    state = get_gist()

    # Step 2: Post yesterday's answer if there was a puzzle
    if state["puzzle"]:
        print("Posting yesterday's answer")
        if "solution_steps" in state:
            # Post answer separately from solution
            answer_message = (
                f"💡 **Answer to yesterday's {state['category']} puzzle:**\n\n"
                f"**Answer:** ||{state['solution_answer']}||"
            )
            solution_steps = state['solution_steps']
            if len(solution_steps) > 1500:
                solution_steps = solution_steps[:1500] + "\n*(solution truncated)*"
            solution_message = (
                f"**Solution:**\n{solution_steps}"
            )
        else:
            answer_message = (
                f"💡 **Answer to yesterday's {state['category']} puzzle:**\n\n"
                f"**Answer:** ||{state['answer']}||"
            )
            solution_steps = state['solution']
            if len(solution_steps) > 1500:
                solution_steps = solution_steps[:1500] + "\n*(solution truncated)*"
            solution_message = (
                f"**Solution:**\n{solution_steps}"
            )
        # print(f"Answer message:\n{answer_message}") # DEBUG
        post_to_discord(answer_message)
        post_to_discord(solution_message)
    
    # Step 3: Generate today's puzzle
    category = random.choice(CATEGORIES)
    print(f"Generating {category} puzzle")
    puzzle_data = None
    for attempt in range(3):
        try:
            puzzle_data = generate_puzzle(category)
            break
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                post_to_discord("⚠️ Brainy encountered an error generating today's puzzle. Please try again later.")
                print("All attempts failed, posted error message.")
                return

    # Step 4: Post today's puzzle
    print("Posting today's puzzle")
    puzzle_message = (
        f"🧩 **Daily Puzzle — {category.title()}**\n\n"
        f"{puzzle_data['puzzle']}\n\n"
        f"*Think you know the answer? Share your solution below! "
        f"The answer will be revealed tomorrow — please verify it yourself!* 🤓"
    )

    post_to_discord(puzzle_message)

    # Step 5: Save today's state to Gist
    print("Saving today's state to Gist")
    new_state = {
        "date": today,
        "category": category,
        "puzzle": puzzle_data["puzzle"],
        "solution_steps": puzzle_data["solution_steps"],
        "solution_answer": puzzle_data["solution_answer"]
    }
    update_gist(new_state)
    print("Done!")


if __name__ == "__main__":
    main()