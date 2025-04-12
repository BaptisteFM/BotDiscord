import discord
from discord import app_commands
from discord.ext import commands
from utils.utils import (
    salon_est_autorise, is_admin, get_or_create_role,
    get_redirection, charger_config
)
import datetime
import random

class SupportCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ───────────── /besoin_d_aide ─────────────
    @app_commands.command(name="besoin_d_aide", description="Explique ton besoin et ouvre un espace d'entraide.")
    async def besoin_d_aide(self, interaction: discord.Interaction):
        if not await salon_est_autorise("besoin_d_aide", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        class ModalBesoinAide(discord.ui.Modal, title="Explique ton besoin d’aide"):
            sujet = discord.ui.TextInput(label="Sujet", placeholder="Ex: Difficultés en anatomie", max_length=100, required=True)
            description = discord.ui.TextInput(label="Détaille ton besoin", style=discord.TextStyle.paragraph, max_length=500, required=True)

            async def on_submit(self, modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(ephemeral=True)
                try:
                    user = modal_interaction.user
                    guild = modal_interaction.guild

                    role_name = f"Aide-{user.name}-{user.id}"
                    role_temp = await get_or_create_role(guild, role_name)
                    await user.add_roles(role_temp)

                    config = charger_config()
                    role_aide_id = config.get("role_aide")
                    role_aide = guild.get_role(int(role_aide_id)) if role_aide_id else None

                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        role_temp: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    }
                    if role_aide:
                        overwrites[role_aide] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

                    category_name = f"aide-{user.name}-{user.id}".lower()
                    category = await guild.create_category(category_name, overwrites=overwrites)
                    text_channel = await guild.create_text_channel("écris-ici", category=category)
                    await guild.create_voice_channel("parle-ici", category=category)

                    view = BoutonsAide(user, category, role_temp)

                    embed = discord.Embed(
                        title=f"🔎 Besoin d'aide : {self.sujet.value}",
                        description=self.description.value,
                        color=discord.Color.orange(),
                        timestamp=datetime.datetime.utcnow()
                    )
                    embed.set_footer(text=f"Demandé par {user.display_name}")
                    await interaction.channel.send(embed=embed, view=view)

                    if role_aide:
                        await text_channel.send(
                            f"🔔 {role_aide.mention}, {user.mention} a besoin d'aide !\n\n"
                            f"**Sujet :** {self.sujet.value}\n"
                            f"**Détails :** {self.description.value}"
                        )

                    await modal_interaction.followup.send("✅ Espace privé créé et demande envoyée.", ephemeral=True)

                except Exception as e:
                    await modal_interaction.followup.send(f"❌ Une erreur est survenue : {e}", ephemeral=True)
                    await self.log_error(modal_interaction.guild, "besoin_d_aide", e)

        await interaction.response.send_modal(ModalBesoinAide(timeout=None))

    # ───────────── /journal_burnout ─────────────
    @app_commands.command(name="journal_burnout", description="Signale un mal-être ou burn-out.")
    @app_commands.describe(message="Décris ce que tu ressens.")
    async def journal_burnout(self, interaction: discord.Interaction, message: str):
        if not await salon_est_autorise("journal_burnout", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        try:
            await interaction.response.defer(ephemeral=True)
            channel_id = get_redirection("burnout")
            salon = interaction.guild.get_channel(int(channel_id)) if channel_id else None
            if not salon:
                return await interaction.followup.send("❌ Salon de redirection non trouvé.", ephemeral=True)

            embed = discord.Embed(
                title="🚨 Signalement Burn-Out",
                description=message,
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Par {interaction.user.display_name}")
            await salon.send(embed=embed)
            await interaction.followup.send("🆘 Ton message a été transmis à l’équipe.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Une erreur est survenue : {e}", ephemeral=True)
            await self.log_error(interaction.guild, "journal_burnout", e)

    # ───────────── /auto_motivation ─────────────
    @app_commands.command(name="auto_motivation", description="Reçois un boost de motivation.")
    async def auto_motivation(self, interaction: discord.Interaction):
        if not await salon_est_autorise("auto_motivation", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        try:
            citations = [
                "🔥 Chaque jour compte, ne lâche rien !",
                "🎯 Pense à ton objectif et dépasse tes limites.",
                "🌟 La discipline forge la réussite.",
                "💪 Fais ce que tu dois pour être fier de toi demain."
            ]
            await interaction.response.send_message(f"💬 {random.choice(citations)}", ephemeral=True)
        except Exception as e:
            await self.log_error(interaction.guild, "auto_motivation", e)

    # ───────────── /challenge_semaine ─────────────
    @app_commands.command(name="challenge_semaine", description="Reçois un défi à appliquer cette semaine.")
    async def challenge_semaine(self, interaction: discord.Interaction):
        if not await salon_est_autorise("challenge_semaine", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        try:
            challenges = [
                "🛌 Se coucher avant 23h chaque soir.",
                "📵 Une journée sans réseaux sociaux.",
                "📚 Revoir ses erreurs chaque soir.",
                "🤝 Aider un camarade en difficulté.",
                "🧘 Faire 10 minutes de méditation quotidienne."
            ]
            await interaction.response.send_message(f"📆 Challenge : **{random.choice(challenges)}**", ephemeral=True)
        except Exception as e:
            await self.log_error(interaction.guild, "challenge_semaine", e)

    # ───────────── LOG ERREUR ─────────────
    async def log_error(self, guild: discord.Guild, commande: str, erreur: Exception):
        config = charger_config()
        salon_log_id = config.get("log_erreurs_channel")
        if not salon_log_id:
            return
        salon_log = guild.get_channel(int(salon_log_id))
        if salon_log:
            embed = discord.Embed(
                title=f"🛑 Erreur dans la commande : `{commande}`",
                description=f"```{str(erreur)}```",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            await salon_log.send(embed=embed)

# ───────────── VUE AVEC BOUTONS ─────────────
class BoutonsAide(discord.ui.View):
    def __init__(self, demandeur, category, temp_role):
        super().__init__(timeout=None)
        self.demandeur = demandeur
        self.category = category
        self.temp_role = temp_role

    @discord.ui.button(label="J’ai aussi ce problème", style=discord.ButtonStyle.primary)
    async def rejoindre(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.temp_role not in interaction.user.roles:
            await interaction.user.add_roles(self.temp_role)
            await interaction.response.send_message("✅ Vous avez rejoint cet espace d’aide.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ Vous êtes déjà dans cet espace.", ephemeral=True)

    @discord.ui.button(label="Supprimer la demande", style=discord.ButtonStyle.danger)
    async def supprimer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.demandeur:
            return await interaction.response.send_message("❌ Seul le demandeur peut supprimer cette demande.", ephemeral=True)
        try:
            await self.category.delete()
            await self.demandeur.remove_roles(self.temp_role)
            await interaction.response.send_message("✅ Demande supprimée.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

# ───────────── SETUP COG ─────────────
async def setup_support_commands(bot):
    await bot.add_cog(SupportCommands(bot))
