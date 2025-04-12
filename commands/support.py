import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random
from utils.utils import charger_config, log_erreur, is_verified_user

async def check_verified(interaction: discord.Interaction) -> bool:
    if await is_verified_user(interaction.user):
        return True
    raise app_commands.CheckFailure("Commande réservée aux membres vérifiés.")

class JournalBurnoutModal(discord.ui.Modal, title="Journal Burn-Out"):
    message = discord.ui.TextInput(
        label="Décris ton état (anonymement)",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: Je suis épuisé(e), démotivé(e), etc...",
        required=True
    )
    emoji = discord.ui.TextInput(
        label="Emoji d'état (optionnel)",
        style=discord.TextStyle.short,
        placeholder="Ex: 😞, 😴, etc.",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            config = charger_config()
            burnout_channel_id = config.get("journal_burnout_channel")
            if not burnout_channel_id:
                await interaction.response.send_message("❌ Le salon pour le journal burnout n'est pas configuré.", ephemeral=True)
                return
            
            channel = interaction.guild.get_channel(int(burnout_channel_id))
            if not channel:
                await interaction.response.send_message("❌ Le salon pour le journal burnout est introuvable.", ephemeral=True)
                return

            emoji_used = self.emoji.value.strip() if self.emoji.value.strip() else random.choice(["😞", "😔", "😢", "😴", "😓", "💤"])

            embed = discord.Embed(
                title="🚨 Signalement de Burn-Out",
                description=self.message.value,
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="État", value=emoji_used, inline=True)
            embed.set_footer(text="Signalé anonymement")
            
            await channel.send(embed=embed)
            await interaction.response.send_message("✅ Ton signalement a été envoyé. Prends soin de toi.", ephemeral=True)
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"JournalBurnoutModal on_submit: {e}")
            await interaction.response.send_message("❌ Une erreur est survenue lors de l'envoi de ton signalement.", ephemeral=True)

class SupportCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Vous n'avez pas accès aux commandes support. Si vous rencontrez un problème, contactez le staff.",
                ephemeral=True
            )
        else:
            await log_erreur(self.bot, interaction.guild, f"SupportCommands error: {error}")
            raise error

    @app_commands.command(name="journal_burnout", description="Signale anonymement une baisse de moral, une fatigue mentale ou un burn-out.")
    @app_commands.check(check_verified)
    async def journal_burnout(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(JournalBurnoutModal())
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"journal_burnout: {e}")
            await interaction.response.send_message("❌ Une erreur est survenue lors de l'ouverture du formulaire.", ephemeral=True)

async def setup_support_commands(bot: commands.Bot):
    await bot.add_cog(SupportCommands(bot))
