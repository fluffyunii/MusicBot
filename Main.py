import discord
from discord.ext import commands
import youtube_dl
import asyncio
import os
import subprocess

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
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # Take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

bot = commands.Bot(command_prefix='!')

queue = []

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user}')

@bot.command(name='play', help='Plays a song from YouTube')
async def play(ctx, url):
    global queue

    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You are not connected to a voice channel.")
            return

    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        queue.append(player)
        if not ctx.voice_client.is_playing():
            ctx.voice_client.play(queue.pop(0), after=lambda e: check_queue(ctx))
            await ctx.send(f'Now playing: {player.title}')

def check_queue(ctx):
    if queue:
        ctx.voice_client.play(queue.pop(0), after=lambda e: check_queue(ctx))

@bot.command(name='skip', help='Skips the current song')
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Song skipped.")
        if queue:
            ctx.voice_client.play(queue.pop(0), after=lambda e: check_queue(ctx))

@bot.command(name='stop', help='Stops the bot and clears the queue')
async def stop(ctx):
    if ctx.voice_client:
        queue.clear()
        await ctx.voice_client.disconnect()
        await ctx.send("Bot disconnected and queue cleared.")

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

def check_ffmpeg_installed():
    try:
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("FFmpeg must be installed and available in your PATH.")

if __name__ == "__main__":
    check_ffmpeg_installed()
    TOKEN = 'TOKEN'
    bot.run(TOKEN)
