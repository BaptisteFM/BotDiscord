import discord
from discord import app_commands
from discord.ext import commands
import datetime
import asyncio
from utils.utils import (
    charger_config,
    log_erreur,
    get_redirection,
    salon_est_autorise,
    is_verified_user
)

async def check_verified(interaction: discord.Interaction) -> bool:
    if await is_verified_user(interaction.user):
        return True
    raise app_commands.CheckFailure("Commande réservée aux membres vérifiés.")

class SortieModal(discord.ui.Modal, title="Proposer une sortie / activité"):
    def __init__(self, bot, auteur):
        super().__init__()
        self.bot = bot
        self.auteur = auteur

    jour = discord.ui.TextInput(
        label="Date de la sortie",
        placeholder="Ex: 23 avril",
        required=True
    )
    lieu = discord.ui.TextInput(
        label="Lieu de la sortie",
        placeholder="Ex: Parc Phoenix",
        required=True
    )
    activite = discord.ui.TextInput(
        label="Activité prévue",
        placeholder="Ex: Pique-nique, balade, etc.",
        required=True
    )
    details = discord.ui.TextInput(
        label="Détails complémentaires",
        style=discord.TextStyle.paragraph,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            config = charger_config()
            salon_id = get_redirection("sortie") or config.get("sortie_channel")
            role_id = config.get("role_sortie")

            if not salon_id or not role_id:
                return await interaction.response.send_message(
                    "❌ Salon ou rôle pour la sortie non défini par l’admin.", ephemeral=True
                )

            salon = interaction.guild.get_channel(int(salon_id))
            role = interaction.guild.get_role(int(role_id))
            if not salon or not role:
                return await interaction.response.send_message(
                    "❌ Configuration invalide.", ephemeral=True
                )

            # On construit la description avec le ping du rôle
            description = f"{role.mention}\n**Date :** {self.jour.value}\n**Lieu :** {self.lieu.value}\n**Activité :** {self.activite.value}"
            if self.details.value:
                description += f"\n\n{self.details.value}"

            embed = discord.Embed(
                title="📢 Nouvelle sortie proposée !",
                description=description,
                color=discord.Color.green()
            )
            embed.set_footer(
                text=f"Proposée par {self.auteur.display_name}",
                icon_url=self.auteur.avatar.url if self.auteur.avatar else None
            )

            view = ParticiperSortieView(self.bot, self.jour.value, self.auteur)
            await salon.send(embed=embed, view=view)
            await interaction.response.send_message(
                "✅ Ta sortie a été proposée avec succès !", ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                "❌ Erreur lors de la création de la sortie.", ephemeral=True
            )
            await log_erreur(
                self.bot, interaction.guild, f"SortieModal on_submit : {e}"
            )

class ParticiperSortieView(discord.ui.View):
    def __init__(self, bot, date_sortie: str, auteur: discord.Member):
        super().__init__(timeout=None)
        self.bot = bot
        self.date_sortie = date_sortie
        self.auteur = auteur
        self.participants = set()

    @discord.ui.button(label="Je suis chaud(e) 🔥", style=discord.ButtonStyle.success)
    async def chaud_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if interaction.user.id in self.participants:
                return await interaction.response.send_message(
                    "ℹ️ Tu es déjà inscrit à cette sortie.", ephemeral=True
                )

            self.participants.add(interaction.user.id)
            guild = interaction.guild

            # Préparer les permissions pour créer la catégorie privée
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                self.auteur: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            for uid in self.participants:
                user = guild.get_member(uid)
                if user:
                    overwrites[user] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            category = await guild.create_category(
                f"sortie du {self.date_sortie}", overwrites=overwrites
            )
            salon_texte = await guild.create_text_channel("discussion-sortie", category=category)
            salon_vocal = await guild.create_voice_channel("vocal-sortie", category=category)

            await salon_texte.send(
                f"👋 Hello {interaction.user.mention} ! Explique un peu plus ton idée si tu veux :"
            )
            await salon_texte.send(view=SupprimerSortieView(category, self.auteur))

            # Supression auto après 24h
            now = datetime.datetime.utcnow()
            sortie_datetime = now + datetime.timedelta(hours=24)
            await asyncio.sleep((sortie_datetime - now).total_seconds())
            try:
                for c in category.channels:
                    await c.delete()
                await category.delete()
            except Exception:
                pass

            await interaction.response.send_message(
                "✅ Tu as rejoint la sortie ! Un espace privé a été créé.", ephemeral=True
            )

        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ParticiperSortieView: {e}")
            await interaction.response.send_message(
                "❌ Erreur lors de la création de l’espace privé.", ephemeral=True
            )

class SupprimerSortieView(discord.ui.View):
    def __init__(self, category: discord.CategoryChannel, auteur: discord.Member):
        super().__init__(timeout=None)
        self.category = category
        self.auteur = auteur

    @discord.ui.button(label="Sortie passée ✅", style=discord.ButtonStyle.danger)
    async def supprimer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.auteur:
            return await interaction.response.send_message(
                "❌ Seul l’auteur de la sortie peut la supprimer.", ephemeral=True
            )
        try:
            for channel in self.category.channels:
                await channel.delete()
            await self.category.delete()
            await interaction.response.send_message(
                "✅ Sortie supprimée.", ephemeral=True
            )
        except Exception as e:
            await log_erreur(
                interaction.client, interaction.guild, f"SupprimerSortieView: {e}"
            )
            await interaction.response.send_message(
                "❌ Erreur lors de la suppression.", ephemeral=True
            )

class LoisirCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Vous n'avez pas accès à cette commande. Rapprochez-vous du staff.",
                ephemeral=True
            )
        else:
            await log_erreur(self.bot, interaction.guild, f"LoisirCommands error: {error}")
            raise error

    @app_commands.command(name="proposer_sortie", description="Propose une sortie sociale ou une activité.")
    @app_commands.check(check_verified)
    async def proposer_sortie(self, interaction: discord.Interaction):
        if not salon_est_autorise("proposer_sortie", interaction.channel_id, interaction.user):
            return await interaction.response.send_message(
                "❌ Commande non autorisée dans ce salon.", ephemeral=True
            )
        try:
            await interaction.response.send_modal(SortieModal(self.bot, interaction.user))
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"Erreur dans /proposer_sortie : {e}")
            await interaction.followup.send(
                "❌ Erreur lors de l’ouverture du formulaire.", ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(LoisirCommands(bot))
