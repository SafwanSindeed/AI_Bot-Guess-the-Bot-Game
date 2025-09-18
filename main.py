import os
import asyncio
import random
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Try to import OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Setup Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Setup OpenAI client if available
if OPENAI_AVAILABLE and OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None
    print("⚠️ OpenAI API not available. Bot will use mock answers.")

# --- Game state ---
joined_users = []           # list of human Discord IDs
players_anonymous = {}      # maps Discord ID / 'BOT' -> 'Player X'
reverse_players = {}        # maps 'Player X' -> Discord ID / 'BOT'
bot_player_id = "BOT"
game_started = False
votes = {}
questions = [
    "If you had to eat one food forever, what would it be?",
    "What’s your dream vacation?",
    "If you won the lottery, what’s the first thing you’d buy?",
    "If you could have any superpower, what would it be?",
    "What is your favorite movie of all time?"
]

# --- Bot ready event ---
@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")

# --- Helper function to get bot answer ---
def get_bot_answer(question: str) -> str:
    if client:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a teenage human in a party game. Give very short, casual answers, mostly 1–2 words."},
                    {"role": "user", "content": question},
                ],
                max_tokens=10
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI API failed: {e}")
    # Fallback mock teen-like answers
    mock_answers = ["Pizza", "Beach", "Car", "Fly", "Inception", "Cat", "Chill", "Gaming", "Da Vinci", "Guitar", "Park", "Paris"]
    return random.choice(mock_answers)

# --- Commands ---
@bot.command(name="join")
async def join(ctx):
    if game_started:
        await ctx.send("Game already started! Wait for the next round.")
        return
    if ctx.author.id in joined_users:
        await ctx.send("You already joined the game!")
        return
    joined_users.append(ctx.author.id)
    await ctx.send("You have joined the game!")

@bot.command(name="startgame")
async def startgame(ctx):
    global game_started, players_anonymous, reverse_players, votes
    if game_started:
        await ctx.send("Game already running!")
        return
    if len(joined_users) == 0:
        await ctx.send("No players joined yet! Players must use `!join` first.")
        return

    game_started = True
    votes = {}
    # Include bot in participants
    all_participants = joined_users + [bot_player_id]
    random.shuffle(all_participants)

    # Assign Player numbers randomly
    players_anonymous = {}
    reverse_players = {}
    for i, uid in enumerate(all_participants, start=1):
        anon_name = f"Player {i}"
        players_anonymous[uid] = anon_name
        reverse_players[anon_name] = uid

    await ctx.send("🎭 The Imitation Game is starting!")
    await ctx.send("Players have been assigned anonymous numbers.")
    await ctx.send("Use `!play` to start the questions!")

@bot.command(name="play")
async def play(ctx):
    if not game_started:
        await ctx.send("No game running. Use !startgame first.")
        return

    human_players = [uid for uid in joined_users]

    for i, q in enumerate(questions, start=1):
        round_answers = {}
        bot_answered = False

        await ctx.send(f"**Question {i}:** {q}")
        await ctx.send("Players, type your answers now! You have 15 seconds per answer.")

        def check(m):
            return m.author.id in human_players and m.channel == ctx.channel

        humans_answered = set()

        try:
            while len(humans_answered) < len(human_players):
                msg = await bot.wait_for("message", timeout=30.0, check=check)
                anon_name = players_anonymous[msg.author.id]
                if anon_name not in round_answers:
                    round_answers[anon_name] = msg.content
                    humans_answered.add(msg.author.id)

                # Bot answers 2 seconds after the first human
                if not bot_answered and len(humans_answered) >= 1:
                    await asyncio.sleep(2)
                    bot_answer = get_bot_answer(q)
                    round_answers[players_anonymous[bot_player_id]] = bot_answer
                    bot_answered = True

        except asyncio.TimeoutError:
            # Add bot if it hasn't answered yet
            if not bot_answered:
                bot_answer = get_bot_answer(q)
                round_answers[players_anonymous[bot_player_id]] = bot_answer

            # Fill missing human answers with "No Answer"
            for uid in human_players:
                anon_name = players_anonymous[uid]
                if anon_name not in round_answers:
                    round_answers[anon_name] = "No Answer"

        # Shuffle and reveal all answers
        shuffled_answers = list(round_answers.items())
        random.shuffle(shuffled_answers)

        await ctx.send("📝 Revealed answers for this question:")
        answers_text = "\n".join([f"{player}: {answer}" for player, answer in shuffled_answers])
        await ctx.send(answers_text)

    await ctx.send("🗳️ Time to vote! Use `!vote <player#>` to guess the bot. You get 1 vote each.")

@bot.command(name="vote")
async def vote(ctx, player_num: int):
    if ctx.author.id not in joined_users:
        await ctx.send("You are not in the game!")
        return
    if ctx.author.id in votes:
        await ctx.send("You already voted!")
        return

    guess = f"Player {player_num}"
    if guess not in reverse_players:
        await ctx.send("Invalid player number.")
        return

    votes[ctx.author.id] = player_num
    await ctx.send(f"You voted for {guess}!")

@bot.command(name="reveal")
async def reveal(ctx):
    bot_player_name = players_anonymous[bot_player_id]       # e.g. "Player 3"
    bot_number = int(bot_player_name.split()[1])             # extract number

    await ctx.send(f"The bot was {bot_player_name}!")

    # Find players who guessed correctly
    winners = []
    for user_id, voted_num in votes.items():
        if voted_num == bot_number:
            if user_id in players_anonymous:
                winners.append(players_anonymous[user_id])
            else:
                winners.append(f"Player {voted_num}")

    if winners:
        await ctx.send(f"🎉 Correct guessers: {', '.join(winners)}")
    else:
        await ctx.send("Nobody guessed correctly!")

# --- Run the bot ---
bot.run(DISCORD_TOKEN)
