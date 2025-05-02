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
            role_staff_id = config.get("role_staff_sortie")

            if not salon_id or not role_id:
                return await interaction.response.send_message(
                    "❌ Salon ou rôle pour la sortie non défini.", ephemeral=True
                )

            salon = interaction.guild.get_channel(int(salon_id))
            role = interaction.guild.get_role(int(role_id))
            role_staff = interaction.guild.get_role(int(role_staff_id)) if role_staff_id else None

            if not salon or not role:
                return await interaction.response.send_message(
                    "❌ Configuration invalide.", ephemeral=True
                )

            # Création catégorie privée dès la proposition
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                self.auteur: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }
            if role_staff:
                overwrites[role_staff] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            category = await interaction.guild.create_category(
                f"sortie du {self.jour.value} - 0", overwrites=overwrites
            )
            salon_texte = await interaction.guild.create_text_channel("discussion-sortie", category=category)
            salon_vocal = await interaction.guild.create_voice_channel("vocal-sortie", category=category)

            await salon_texte.send(
                f"📢 Nouvelle sortie proposée par {self.auteur.mention} !",
                view=SupprimerSortieView(category, self.auteur, role_staff)
            )

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

            view = ParticiperSortieView(self.bot, category, self.auteur)
            await salon.send(embed=embed, view=view)

            await interaction.response.send_message("✅ Ta sortie a bien été proposée !", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message("❌ Erreur lors de la proposition.", ephemeral=True)
            await log_erreur(self.bot, interaction.guild, f"SortieModal on_submit: {e}")

class ParticiperSortieView(discord.ui.View):
    def __init__(self, bot, category, auteur):
        super().__init__(timeout=None)
        self.bot = bot
        self.category = category
        self.auteur = auteur
        self.participants = set()

    @discord.ui.button(label="Je suis chaud(e) 🔥", style=discord.ButtonStyle.success)
    async def chaud_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.participants:
            return await interaction.response.send_message(
                "ℹ️ Tu es déjà dans le groupe.", ephemeral=True
            )
        try:
            self.participants.add(interaction.user.id)
            for channel in self.category.channels:
                await channel.set_permissions(interaction.user, read_messages=True, send_messages=True)

            nb = len(self.participants)
            base_name = self.category.name.split(" - ")[0]
            await self.category.edit(name=f"{base_name} - {nb}")

            await interaction.response.send_message("✅ Tu as rejoint la sortie !", ephemeral=True)

            self.add_item(QuitterSortieButton(self.category, self.auteur, self.participants))

        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ParticiperSortieView: {e}")
            await interaction.response.send_message("❌ Erreur technique.", ephemeral=True)

class QuitterSortieButton(discord.ui.Button):
    def __init__(self, category, auteur, participants):
        super().__init__(label="Finalement je ne serai pas là", style=discord.ButtonStyle.secondary)
        self.category = category
        self.auteur = auteur
        self.participants = participants

    async def callback(self, interaction: discord.Interaction):
        if interaction.user == self.auteur:
            return await interaction.response.send_message("❌ Tu ne peux pas quitter une sortie que tu as proposée.", ephemeral=True)

        try:
            for channel in self.category.channels:
                await channel.set_permissions(interaction.user, overwrite=None)

            self.participants.discard(interaction.user.id)
            nb = len(self.participants)
            base_name = self.category.name.split(" - ")[0]
            await self.category.edit(name=f"{base_name} - {nb}")

            await interaction.response.send_message("🚫 Tu as quitté la sortie.", ephemeral=True)
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"QuitterSortieButton: {e}")
            await interaction.response.send_message("❌ Erreur technique.", ephemeral=True)

class SupprimerSortieView(discord.ui.View):
    def __init__(self, category, auteur, role_staff=None):
        super().__init__(timeout=None)
        self.category = category
        self.auteur = auteur
        self.role_staff = role_staff

    @discord.ui.button(label="Sortie passée ✅", style=discord.ButtonStyle.danger)
    async def supprimer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.auteur and (not self.role_staff or self.role_staff not in interaction.user.roles):
            return await interaction.response.send_message(
                "❌ Seul l’auteur ou le staff peut fermer cette sortie.", ephemeral=True
            )
        try:
            for channel in self.category.channels:
                await channel.delete()
            await self.category.delete()
            await interaction.response.send_message("✅ Sortie supprimée.", ephemeral=True)
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"SupprimerSortieView: {e}")
            await interaction.response.send_message("❌ Erreur lors de la suppression.", ephemeral=True)

class LoisirCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Vous n'avez pas accès à cette commande.", ephemeral=True
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
            await interaction.followup.send("❌ Erreur lors de l’ouverture du formulaire.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(LoisirCommands(bot))
