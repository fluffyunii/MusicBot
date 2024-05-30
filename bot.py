import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import os

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # Bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        except youtube_dl.DownloadError as e:
            print(f"Download error: {e}")
            return None

        if 'entries' in data:
            # Take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# Define intents
intents = discord.Intents.all()
intents.members = True  # Enable the members intent to receive member events
intents.messages = True  # Enable the messages intent to receive message content

bot = commands.Bot(command_prefix='!', intents=intents)

queue = []

@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/help"))
    print(f'Bot connected as {bot.user}')

@bot.command(name='join', help='Joins the voice channel of the user who typed the command')
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("You are not connected to a voice channel.")
        return

    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"Joined {channel}")

@bot.command(name='play', help='Plays a song from YouTube')
async def play(ctx, *, query):
    global queue

    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You are not connected to a voice channel.")
            return

    async with ctx.typing():
        if 'youtube.com' in query or 'youtu.be' in query:
            # If the query is a YouTube URL
            player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
            if player is None:
                await ctx.send("Could not download the song. This might be due to an issue with the URL or YouTube itself.")
                return
        else:
            # If the query is a search query
            query = f"ytsearch:{query}"
            player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
            if player is None:
                await ctx.send("No videos found with that title.")
                return

        queue.append(player)
        if not ctx.voice_client.is_playing():
            await play_next(ctx)

async def play_next(ctx):
    if queue:
        ctx.voice_client.play(queue.pop(0), after=lambda e: check_queue(ctx))
        await ctx.send(f'Now playing: {ctx.voice_client.source.title}')
    else:
        await ctx.send("Queue is empty.")

def check_queue(ctx):
    if queue:
        ctx.voice_client.play(queue.pop(0), after=lambda e: check_queue(ctx))

@bot.command(name='skip', help='Skips the current song')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await play_next(ctx)

@bot.command(name='stop', help='Stops the bot and clears the queue')
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.is_connected():
        queue.clear()
        await ctx.voice_client.disconnect()
        await ctx.send("Bot disconnected and queue cleared.")
    else:
        await ctx.send("I am not connected to a voice channel.")

@bot.command(name='queue', help='Displays the current queue')
async def show_queue(ctx):
    if queue:
        queue_list = [player.title for player in queue]
        await ctx.send("Current queue:\n" + "\n".join(queue_list))
    else:
        await ctx.send("The queue is empty.")

@bot.command(name='clear', help='Clears the queue')
async def clear(ctx):
    queue.clear()
    await ctx.send("Queue cleared.")

if __name__ == "__main__":
    TOKEN = os.getenv('BOTTOKEN')
    if not TOKEN:
        raise RuntimeError("The BOTTOKEN environment variable is not set.")
    bot.run(TOKEN)