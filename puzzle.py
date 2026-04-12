import anthropic
import json
import os
import random
import requests
from datetime import date
from dotenv import load_dotenv
from shared import ts, parse_json_response, post_to_discord_safe

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
    "number theory"
]

BOT_NAME = "Brainy"
MAX_ATTEMPTS = 3


def get_gist():
    """Read yesterday's puzzle state from GitHub Gist."""
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    content = response.json()["files"]["puzzle_state.json"]["content"]
    data = json.loads(content)
    
    # Ensure puzzle_history exists (for backwards compatibility)
    if "puzzle_history" not in data:
        data["puzzle_history"] = []
    
    return data


def update_gist(data):
    """Write today's puzzle state to GitHub Gist.
    
    Args:
        data: Dictionary to write to Gist
        
    Raises:
        requests.RequestException: If the PATCH request fails
    """
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


def generate_puzzle(category, puzzle_history):
    """Generate a puzzle using the Anthropic API.
    
    Generates a puzzle with solution steps, answer, hint, and difficulty rating.
    Uses two-method verification to ensure solution correctness.
    
    Args:
        category: Puzzle category (e.g., "geometry", "probability")
        puzzle_history: List of recent puzzle texts to inform Claude about recent puzzles
        
    Returns:
        dict: Contains 'puzzle', 'solution_steps', 'solution_answer', 'hint', 'difficulty'
        
    Raises:
        json.JSONDecodeError: If response cannot be parsed as JSON
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    # Build context about recent puzzles if history exists
    history_context = ""
    if puzzle_history:
        history_context = (
            "\n\nAvoid generating puzzles similar to these recent ones:\n"
        )
        for i, past_puzzle in enumerate(puzzle_history[-5:], 1):  # Last 5 puzzles
            history_context += f"{i}. {past_puzzle[:120]}...\n"
    
    prompt = f"""Generate a {category} puzzle suitable for someone with an engineering background who enjoys math puzzles for fun.

The puzzle should:
- Be challenging but solvable in 5-15 minutes
- Have a clean, unambiguous problem statement
- Have a specific numerical or concise answer
- Be interesting or have a surprising result if possible
- Never approximate irrational numbers — leave answers in exact form (e.g. 16 + 8√2)
- Accept non-clean answers if that is the correct result — do not force a clean answer
- Keep solution_steps concise and under 1500 characters total
- Ensure all JSON strings are properly escaped — never use unescaped double quotes inside string values, use single quotes or rephrase instead{history_context}

Solve the puzzle using one method, then verify using a second independent method.
Only finalize the puzzle if both methods agree exactly.

Also provide:
- A subtle one-line hint that points toward *what to think about* without suggesting the method or answer
  (e.g., "Consider how the surfaces connect" NOT "Unfold the cube and use distance formula")
- A difficulty rating from 1-10 (1 = trivial, 10 = extremely hard; aim for 5-7 for typical solvers)

Respond in this exact JSON format with no other text:
{{
"puzzle": "the problem statement here",
"solution_steps": "the step-by-step working shown openly, no final answer here",
"solution_answer": "one concise line stating the final answer",
"hint": "a subtle one-line hint pointing to what to think about, not the method",
"difficulty": 6
}}"""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text
    return parse_json_response(raw)


def main():
    today = str(date.today())

    # Step 1: Read yesterday's state from GitHub Gist
    try:
        print(f"[{ts()}] Reading previous puzzle state from Gist")
        state = get_gist()
    except requests.RequestException as e:
        print(f"[{ts()}] Failed to read Gist: {e}")
        post_to_discord_safe(
            "⚠️ Brainy encountered an error reading the previous puzzle. Please check GitHub Gist access.",
            BOT_NAME,
            DISCORD_WEBHOOK_URL
        )
        return

    # Step 2: Post yesterday's answer if there was a puzzle
    if state.get("puzzle"):
        print(f"[{ts()}] Posting yesterday's answer")
        
        # Handle both old schema (answer/solution) and new schema (solution_answer/solution_steps)
        if "solution_steps" in state:
            solution_answer = state.get("solution_answer", "N/A")
            solution_steps = state.get("solution_steps", "N/A")
        else:
            solution_answer = state.get("answer", "N/A")
            solution_steps = state.get("solution", "N/A")
        
        # Validate solution_steps length before posting
        if len(solution_steps) > 1500:
            solution_steps = solution_steps[:1500] + "\n*(solution truncated)*"
        
        answer_message = (
            f"💡 **Answer to yesterday's {state['category']} puzzle:**\n\n"
            f"**Answer:** ||{solution_answer}||"
        )
        if state.get('difficulty'):
            answer_message += f"\n\n*Difficulty: {state['difficulty']}/10*"
        
        solution_message = f"**Solution:**\n{solution_steps}"
        
        if not post_to_discord_safe(answer_message, BOT_NAME, DISCORD_WEBHOOK_URL):
            print(f"[{ts()}] Warning: Failed to post answer message (may be too long)")
        
        if not post_to_discord_safe(solution_message, BOT_NAME, DISCORD_WEBHOOK_URL):
            print(f"[{ts()}] Warning: Failed to post solution message (may be too long)")
        
        # Step 2b: Post hint if available (with spoiler tag)
        if state.get("hint"):
            hint_message = f"💡 **Hint for reference:**\n||{state['hint']}||"
            if not post_to_discord_safe(hint_message, BOT_NAME, DISCORD_WEBHOOK_URL):
                print(f"[{ts()}] Warning: Failed to post hint message")
    
    # Step 3: Generate today's puzzle
    category = random.choice(CATEGORIES)
    print(f"[{ts()}] Generating {category} puzzle")
    
    puzzle_history = state.get("puzzle_history", [])
    puzzle_data = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            puzzle_data = generate_puzzle(category, puzzle_history)
            print(f"[{ts()}] Puzzle generated successfully on attempt {attempt + 1}")
            break
        except json.JSONDecodeError as e:
            print(f"[{ts()}] Attempt {attempt + 1}/{MAX_ATTEMPTS} failed: {e}")
            if attempt == MAX_ATTEMPTS - 1:
                post_to_discord_safe(
                    "⚠️ Brainy encountered an error generating today's puzzle. Please try again later.",
                    BOT_NAME,
                    DISCORD_WEBHOOK_URL
                )
                print(f"[{ts()}] All {MAX_ATTEMPTS} attempts failed, posted error message.")
                return
        except Exception as e:
            print(f"[{ts()}] Attempt {attempt + 1}/{MAX_ATTEMPTS} failed with unexpected error: {e}")
            if attempt == MAX_ATTEMPTS - 1:
                post_to_discord_safe(
                    "⚠️ Brainy encountered an error generating today's puzzle. Please try again later.",
                    BOT_NAME,
                    DISCORD_WEBHOOK_URL
                )
                print(f"[{ts()}] All {MAX_ATTEMPTS} attempts failed, posted error message.")
                return

    # Step 4: Post today's puzzle
    print(f"[{ts()}] Posting today's puzzle")
    
    difficulty = puzzle_data.get("difficulty")
    puzzle_message = (
        f"🧩 **Daily Puzzle — {category.title()}**\n"
    )
    if difficulty:
        puzzle_message += f"**Difficulty: ⭐** ({difficulty}/10)\n"
    puzzle_message += (
        f"\n{puzzle_data['puzzle']}\n\n"
        f"*Think you know the answer? Share your solution below! "
        f"The answer will be revealed later — please verify it yourself!* 🤓"
    )

    if not post_to_discord_safe(puzzle_message, BOT_NAME, DISCORD_WEBHOOK_URL):
        print(f"[{ts()}] Error: Failed to post puzzle (payload too long). Aborting.")
        return

    # Step 4b: Post hint as a follow-up message
    if puzzle_data.get("hint"):
        hint_message = f"💡 **Hint:** ||{puzzle_data['hint']}||"
        if not post_to_discord_safe(hint_message, BOT_NAME, DISCORD_WEBHOOK_URL):
            print(f"[{ts()}] Warning: Failed to post hint (payload too long)")

    # Step 5: Save today's state to Gist
    # Wrap in try/catch to ensure we only consider success if we can persist the state
    print(f"[{ts()}] Saving today's state to Gist")
    try:
        # Maintain puzzle history (keep last 5 puzzles to match prompt context)
        updated_history = puzzle_history + [puzzle_data["puzzle"]]
        if len(updated_history) > 5:
            updated_history = updated_history[-5:]
        
        new_state = {
            "date": today,
            "category": category,
            "puzzle": puzzle_data["puzzle"],
            "solution_steps": puzzle_data["solution_steps"],
            "solution_answer": puzzle_data["solution_answer"],
            "hint": puzzle_data.get("hint", ""),
            "difficulty": puzzle_data.get("difficulty", 0),
            "puzzle_history": updated_history
        }
        update_gist(new_state)
        print(f"[{ts()}] Successfully saved state to Gist")
    except requests.RequestException as e:
        print(f"[{ts()}] CRITICAL: Failed to save puzzle state to Gist: {e}")
        print(f"[{ts()}] The puzzle was posted but state was not persisted. "
              f"Next run will not have today's solution.")
        post_to_discord_safe(
            "⚠️ Warning: Puzzle was posted but state could not be saved. "
            "Tomorrow's solution reveal may fail.",
            BOT_NAME,
            DISCORD_WEBHOOK_URL
        )
        return

    print(f"[{ts()}] Done!")


if __name__ == "__main__":
    main()