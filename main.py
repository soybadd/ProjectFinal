# Import Libary Discord
import discord
from discord.ext import commands
from discord.utils import get
import youtube_dl
import asyncio
from async_timeout import timeout
from functools import partial
import itertools


# Get Token from env file
import os
from dotenv import load_dotenv
load_dotenv()
token = os.getenv('Token')


#from host_cloud import keep_alive

# Declare prefix of the command
bot = commands.Bot(command_prefix = '*', help_command = None)


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
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
}


# Song won't be played until the end if you don't have this line 
ffmpeg_options = {
    'options': '-vn',
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
}


ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

 
class YTDLSource(discord.PCMVolumeTransformer):

    def __init__(self, source, *, data, requester):
        super().__init__(source)
        self.requester = requester

        self.title = data.get('title')
        self.web_url = data.get('webpage_url')

        # YTDL info dicts (data) have other useful information you might want
        # https://github.com/rg3/youtube-dl/blob/master/README.md

    def __getitem__(self, item: str):
        """Allows us to access attributes similar to a dict.
        This is only useful when you are NOT downloading.
        """
        return self.__getattribute__(item)

    @classmethod
    async def create_source(cls, ctx, search: str, *, loop, download=False):
        loop = loop or asyncio.get_event_loop()

        to_run = partial(ytdl.extract_info, url=search, download=download)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        await ctx.send(f'```ini\n[Added {data["title"]} to the Queue.]\n```') #delete after can be added

        if download:
            source = ytdl.prepare_filename(data)
        else:
            return {'webpage_url': data['webpage_url'], 'requester': ctx.author, 'title': data['title']}

        return cls(discord.FFmpegPCMAudio(source, **ffmpeg_options), data=data, requester=ctx.author)
        # Add function 'ffmepeg_options' for plying until the end
    @classmethod
    async def regather_stream(cls, data, *, loop):
        """Used for preparing a stream, instead of downloading.
        Since Youtube Streaming links expire."""
        loop = loop or asyncio.get_event_loop()
        requester = data['requester']

        to_run = partial(ytdl.extract_info, url=data['webpage_url'], download=False)
        data = await loop.run_in_executor(None, to_run)

        return cls(discord.FFmpegPCMAudio(data['url'], **ffmpeg_options), data=data, requester=requester)

class MusicPlayer:
    """A class which is assigned to each guild using the bot for Music.
    This class implements a queue and loop, which allows for different guilds to listen to different playlists
    simultaneously.
    When the bot disconnects from the Voice it's instance will be destroyed.
    """

    __slots__ = ('bot', '_guild', '_channel', '_cog', 'queue', 'next', 'current', 'np', 'volume')

    def __init__(self, ctx):
        self.bot = ctx.bot
        self._guild = ctx.guild
        self._channel = ctx.channel
        self._cog = ctx.cog

        self.queue = asyncio.Queue()
        self.next = asyncio.Event()

        self.np = None  # Now playing message
        self.volume = .5
        self.current = None

        ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        """Our main player loop."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            try:
                # Wait for the next song. If we timeout cancel the player and disconnect...
                async with timeout(300):  # 5 minutes...
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                del players[self._guild]
                return await self.destroy(self._guild)

            if not isinstance(source, YTDLSource):
                # Source was probably a stream (not downloaded)
                # So we should regather to prevent stream expiration
                try:
                    source = await YTDLSource.regather_stream(source, loop=self.bot.loop)
                except Exception as e:
                    await self._channel.send(f'There was an error processing your song.\n'
                                             f'```css\n[{e}]\n```')
                    continue

            source.volume = self.volume
            self.current = source

            self._guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
            self.np = await self._channel.send(f'**Now Playing:** `{source.title}` requested by '
                                               f'`{source.requester}`')
            await self.next.wait()

            # Make sure the FFmpeg process is cleaned up.
            source.cleanup()
            self.current = None

            try:
                # We are no longer playing this song...
                await self.np.delete()
            except discord.HTTPException:
                pass

    # Leaving itslef out function
    async def destroy(self, guild,text):
        """Disconnect and cleanup the player."""
        await self._guild.voice_client.disconnect()
        return self.bot.loop.create_task(self._cog.cleanup(guild))



# Turning on Bot
@bot.event
async def on_ready():
    # When Bot is ready
    print('We have logged in as {0.user}'.format(bot))
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name='*help'))


# Test Command
@bot.command()
async def test(ctx, *, message):
    # '*' is for spacebar
    await ctx.channel.send(message)


# Clear Command
@bot.command()
async def clear(ctx, amount = 1):
    await ctx.channel.purge(limit = amount + 1)


# Logout Command
@bot.command()
async def logout(ctx):
    await ctx.channel.send('Loging Out...', delete_after = 5)
    await bot.logout()


# Design 'Help' Command by emBed
@bot.command()
async def help(ctx):
    print('help')
    emBed = discord.Embed(title = 'Toturial Lil Krit', description = 'Let\'s see what\'s Lil Krit can do for you', color = 0xFF7A33)
    emBed.add_field(name='*help', value = 'Get help commands', inline = False)
    emBed.add_field(name='*test <text>', value = 'Respond message you\'ve send', inline = False)
    emBed.add_field(name='*clear <number of messages>', value = 'Delete the previous messages', inline = False)
    emBed.add_field(name='*play <URL or name of the song>', value = 'Play the song and add it in to a queue', inline = False)
    emBed.add_field(name='*pause', value = 'Pause the song', inline = False)
    emBed.add_field(name='*resume', value = 'Resume the song', inline = False)
    emBed.add_field(name='*skip', value = 'Skip the song', inline = False)
    emBed.add_field(name='*stop', value = 'Stop the song', inline = False)
    emBed.add_field(name='*queue', value = 'Show the queue list', inline = False)
    emBed.add_field(name='*leave', value = 'Leave bot out of channel', inline = False)
    emBed.add_field(name='*logout', value = 'Turn to be offline', inline = False)
    emBed.set_thumbnail(url='https://i.postimg.cc/W1CR8p3c/IMG-6998.jpg')
    emBed.set_author(name='Krithoolychit\'s Project', url = 'https://discord.com/users/496281331060178944', icon_url='https://i.postimg.cc/Vv2s2xBJ/Presentation1.png')
    await ctx.channel.send(embed = emBed)


# Play the Song Command
@bot.command()
async def play(ctx, *,  search:str):
    print('play')
    my_channel = ctx.author.voice.channel
    # is where the channel you are
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    # is the variable that is the sound for a bot, get is function that store the information in a channel
    '''if my_channel == None:
        await ctx.channel.send('You aren\'t in any channel', delete_after = 8)'''
    if voice_client == None:
        # Check if a bot isn't in any sever 
        await ctx.channel.send('Lil Krit has joined to {0}\nWhat\'s up Dude!'.format(my_channel), delete_after = 8)
        await my_channel.connect()
        # A bot will connect to the sever
        voice_client = get(bot.voice_clients, guild=ctx.guild)

    await ctx.trigger_typing()
    #  Putting 'Bot's Krit is typing...' just for decorate a bot

    startplayer = get_player(ctx)
    source = await YTDLSource.create_source(ctx, search, loop=bot.loop, download=False)

    await startplayer.queue.put(source)
    #add the song in to queue


# In case, there are many sever that our bot are running in. We need to seperate the music player for preventing the song overlapping.
# Creating this function will be very helpful. The music player will be generate in server by sever. 
players = {}
# This variable is for storing an information about the music player and the amount of sever
def get_player(ctx):
# It will check if there is any music player in {players}
    try:
        player = players[ctx.guild.id] 
        # If it already has in players, it will = player 
    except:
        player = MusicPlayer(ctx)
        players[ctx.guild.id] = player
        # If there is not, it will create a new object from MusicPlayer Class and put it = player 
    return player
    # Then return player



# Pause the Song Command
@bot.command()
async def pause(ctx):
    print('pause')
    my_channel = ctx.author.voice.channel
    # is where the channel you are
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    # is the variable that store the sound for a bot, (get is function that store the information in a channel)
    bot_channel = voice_client.channel
    # is where the channel your bot is
    if voice_client == None:
        # Check if a bot isn't in any sever
        await ctx.channel.send("Lil Krit is not connected to the Voice Channel", delete_after = 8)
        return

    if bot_channel != my_channel:
        # Check if a bot and you are not in the same sever  
        # 'voice_client.channel' = where the channel bot is, 'channel' = where the channel you are
        await ctx.channel.send("Can't do that. Lil Krit is currently connected to {0}".format(bot_channel), delete_after = 8)
        return

    else:
        # A bot will stop the song
        voice_client.pause()


# Resume the Song Command
@bot.command()
async def resume(ctx):
    print('resume')
    my_channel = ctx.author.voice.channel
    # is where the channel you are
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    # is the variable that store the sound for a bot, (get is function that store the information in a channel)
    bot_channel = voice_client.channel
    # is where the channel your bot is
    if voice_client == None:
        # Check if a bot isn't in any sever
        await ctx.channel.send("Lil Krit is not connected to the Voice Channel", delete_after = 8)
        return

    if bot_channel != my_channel:
        # Check if a bot and you are not in the same sever  
        # 'voice_client.channel' = where the channel bot is, 'channel' = where the channel you are
        await ctx.channel.send("Can't do that. Lil Krit is currently connected to {0}".format(bot_channel), delete_after = 8)
        return

    else:
        # A bot will resume the song
        voice_client.resume()


# Stop the Song Command
@bot.command()
async def stop(ctx):
    print('stop')
    my_channel = ctx.author.voice.channel
    # is where the channel you are
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    # is the variable that store the sound for a bot, (get is function that store the information in a channel)
    bot_channel = voice_client.channel
    # is where the channel your bot is
    if voice_client == None:
        # Check if a bot isn't in any sever
        await ctx.channel.send("Lil Krit is not connected to the Voice Channel", delete_after = 8)
        return

    if bot_channel != my_channel:
        # Check if a bot and you are not in the same sever  
        # 'voice_client.channel' = where the channel bot is, 'channel' = where the channel you are
        await ctx.channel.send("Can't do that. Lil Krit is currently connected to {0}".format(bot_channel), delete_after = 8)
        return

    else:
        # A bot will stop the song
        voice_client.stop()


# Skip the Song in Queue Command
@bot.command()
async def skip(ctx):
    print('skip')
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    # is the variable that store the sound for a bot, (get is function that store the information in a channel)
    if voice_client == None:
        # Check if a bot isn't in any sever
        await ctx.channel.send("Lil Krit is not connected to the Voice Channel", delete_after = 8)
        return
    
    await ctx.send(f'**`{ctx.author}`**: Skipped the song!')
    voice_client.stop()


# Open Queue List Command
@bot.command()
async def queue(ctx):
    print('queue')
    voice_client = get(bot.voice_clients, guild=ctx.guild)
    # is the variable that store the sound for a bot, (get is function that store the information in a channel)
    if voice_client == None:
        # Check if a bot isn't in any sever
        await ctx.channel.send("Lil Krt is not connected to the Voice Channel", delete_after = 8)
        return
        
    player = get_player(ctx)
    # We need player for get information about list of the song
    if player.queue.empty():
        # Check if there is no song in the queue
        await ctx.send('There are currently no more queued songs', delete_after = 6)
        return
        
    upcoming = list(itertools.islice(player.queue._queue,0,player.queue.qsize()))
    # The asyncio queue is similar to list but it isn't. So we create list for storage the song from the asyncio queue
    listtostr = '\n'.join(f'**`{song["title"]}`**' for song in upcoming)
    # Format list to string
    embed = discord.Embed(title=f'Upcoming - Next {len(upcoming)}', description=listtostr, color=0xFF7A33)
    await ctx.send(embed=embed)


# Leave Channel Command
@bot.command()
async def leave(ctx):
    print('Leave')
    # deleting music player profile
    await ctx.channel.send('See ya Dude!', delete_after = 5)
    await ctx.voice_client.disconnect()

#run the web sever
#keep_alive()

# Putting token in for activating Bot
bot.run(token)
