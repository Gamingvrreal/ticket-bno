import discord
from discord import app_commands
from discord.ext import commands
import json
import os

CONFIG_FILE = "ticket_config.json"
SETUP_ROLE_ID = 123456789012345678  # 🔁 Replace with your Setup Manager Role ID

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = {}

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync()

# Button View
class TicketButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.success, custom_id="open_ticket_button")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild_id = str(interaction.guild_id)
        if guild_id not in config:
            await interaction.response.send_message("❌ Ticket system not configured.", ephemeral=True)
            return

        data = config[guild_id]
        category = interaction.guild.get_channel(data["category_id"])
        staff_role = interaction.guild.get_role(data["staff_role_id"])

        existing = discord.utils.get(category.channels, name=f"ticket-{interaction.user.id}")
        if existing:
            await interaction.response.send_message(f"❗ You already have a ticket open: {existing.mention}", ephemeral=True)
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.id}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket by {interaction.user}"
        )

        await interaction.response.send_message(f"🎟️ Ticket created: {channel.mention}", ephemeral=True)
        await channel.send(f"{interaction.user.mention} Your ticket has been created! A staff member will assist you soon.\nUse `/close_ticket` to close it.")

# Setup command
@bot.tree.command(name="setup_ticket", description="Set up the ticket system and send a button panel")
@app_commands.describe(category="Category for tickets", staff_role="Staff role", log_channel="Ticket log channel", panel_channel="Channel to post the ticket button")
async def setup_ticket(interaction: discord.Interaction, category: discord.CategoryChannel, staff_role: discord.Role, log_channel: discord.TextChannel, panel_channel: discord.TextChannel):
    if SETUP_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("❌ You don't have permission to set up the ticket system.", ephemeral=True)
        return

    guild_id = str(interaction.guild_id)
    config[guild_id] = {
        "category_id": category.id,
        "staff_role_id": staff_role.id,
        "log_channel_id": log_channel.id
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

    view = TicketButtonView()
    await panel_channel.send("✅ Click the green button below to open a ticket.", view=view)
    await interaction.response.send_message("✅ Ticket system set up and panel sent!", ephemeral=True)

@bot.tree.command(name="close_ticket", description="Close this ticket and generate a transcript")
async def close_ticket(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    guild_id = str(interaction.guild_id)
    if guild_id not in config:
        await interaction.followup.send("❌ Ticket system not configured.", ephemeral=True)
        return

    channel = interaction.channel
    if not channel.name.startswith("ticket-"):
        await interaction.followup.send("⚠️ This is not a ticket channel.", ephemeral=True)
        return

    creator_id = int(channel.name.replace("ticket-", ""))
    is_creator = interaction.user.id == creator_id
    staff_role = interaction.guild.get_role(config[guild_id]["staff_role_id"])

    if not is_creator and staff_role not in interaction.user.roles:
        await interaction.followup.send("❌ Only the ticket creator or staff can close this ticket.", ephemeral=True)
        return

    # Build transcript
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    transcript_lines = [
        f"[{msg.created_at.strftime('%Y-%m-%d %H:%M')}] {msg.author}: {msg.content}"
        for msg in messages if not msg.author.bot
    ]
    transcript = "\n".join(transcript_lines) or "No messages."

    # DM user
    user = await interaction.guild.fetch_member(creator_id)
    try:
        await user.send(f"📁 Your ticket (`{channel.name}`) has been closed. Here's the transcript:\n```{transcript[:1900]}```")
    except discord.Forbidden:
        await interaction.followup.send("⚠️ Could not DM the user.", ephemeral=True)

    # Log transcript to log channel
    log_channel = interaction.guild.get_channel(config[guild_id]["log_channel_id"])
    if log_channel:
        embed = discord.Embed(title="📝 Ticket Closed", color=discord.Color.red())
        embed.add_field(name="Channel", value=channel.name, inline=False)
        embed.add_field(name="Closed by", value=interaction.user.mention, inline=True)
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.description = f"**Transcript:**\n```{transcript[:1000]}```"
        await log_channel.send(embed=embed)

    # Lock channel and notify deletion with countdown
    await channel.set_permissions(user, send_messages=False)

    # Countdown loop (60 seconds)
    for i in range(60, 0, -1):
        await channel.send(
            f"🔒 This ticket has been closed by {interaction.user.mention}. The channel is now locked.\n"
            f"⏳ **This channel will be deleted in {i} second{'s' if i > 1 else ''}.**"
        )
        await discord.utils.sleep(1)  # Wait for 1 second before updating

    # Delete the channel after 60 seconds
    await channel.delete()

    await interaction.followup.send("✅ Ticket closed, transcript sent, and channel deleted.", ephemeral=True)

# Start bot
bot.run("MTMyOTUxOTkxNDU2MTgzNTEzOQ.GxMhcT.EyI0pGMJsfDI48fRE2i5B_XY5SCk9xig1IfUbg")