import discord
from discord import app_commands
from discord.ext import commands
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

    jour = discord.ui.TextInput(label="Date de la sortie", placeholder="Ex: 23 avril", required=True)
    lieu = discord.ui.TextInput(label="Lieu de la sortie", placeholder="Ex: Parc Phoenix", required=True)
    activite = discord.ui.TextInput(label="Activité prévue", placeholder="Ex: Pique-nique, balade, etc.", required=True)
    details = discord.ui.TextInput(label="Détails complémentaires", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cfg = charger_config()
            salon_pub_id = get_redirection("sortie") or cfg.get("sortie_channel")
            role_id = cfg.get("role_sortie")
            staff_id = cfg.get("role_staff_sortie")
            if not salon_pub_id or not role_id:
                return await interaction.response.send_message("❌ Salon ou rôle non défini.", ephemeral=True)

            guild = interaction.guild
            salon_pub = guild.get_channel(int(salon_pub_id))
            role = guild.get_role(int(role_id))
            role_staff = guild.get_role(int(staff_id)) if staff_id else None
            if not salon_pub or not role:
                return await interaction.response.send_message("❌ Configuration invalide.", ephemeral=True)

            # Ping visible et récupération du message ping
            ping_msg = await salon_pub.send(role.mention)

            # Création de la catégorie privée
            slug = self.jour.value.replace(' ', '-')
            cat_name = f"sortie-{slug} - 1"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                self.auteur: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            if role_staff:
                overwrites[role_staff] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            category = await guild.create_category(cat_name, overwrites=overwrites)
            txt = await guild.create_text_channel("discussion-sortie", category=category)
            await guild.create_voice_channel("vocal-sortie", category=category)

            # Envoi du message public embed + participation
            desc = (
                f"**Date :** {self.jour.value}\n"
                f"**Lieu :** {self.lieu.value}\n"
                f"**Activité :** {self.activite.value}"
            ) + (f"\n\n{self.details.value}" if self.details.value else "")
            embed = discord.Embed(title="📢 Nouvelle sortie proposée !", description=desc, color=discord.Color.green())
            embed.set_footer(text=f"Proposée par {self.auteur.display_name}")
            join_view = ParticiperSortieView(category)
            public_msg = await salon_pub.send(embed=embed, view=join_view)

            # Vue de gestion dans le salon privé (quitter + fermer), avec références messages à supprimer
            gestion_view = SortieGestionView(category, self.auteur, role_staff, public_msg, ping_msg)
            await txt.send(f"🔔 {self.auteur.mention}, ta sortie est ici !", view=gestion_view)

            await interaction.response.send_message("✅ Sortie proposée !", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ Erreur lors de la proposition.", ephemeral=True)
            await log_erreur(self.bot, interaction.guild, f"SortieModal: {e}")

class ParticiperSortieView(discord.ui.View):
    def __init__(self, category: discord.CategoryChannel):
        super().__init__(timeout=None)
        self.category = category

    @discord.ui.button(label="Je suis chaud(e) 🔥", style=discord.ButtonStyle.success)
    async def rejoindre(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        # Donner accès aux salons privés
        for ch in self.category.channels:
            await ch.set_permissions(user, read_messages=True, send_messages=True)
        # Incrémenter le compteur dans le nom de la catégorie
        base, count_str = self.category.name.rsplit(' - ', 1)
        new_count = int(count_str) + 1
        await self.category.edit(name=f"{base} - {new_count}")
        await interaction.response.send_message("✅ Tu as rejoint la sortie !", ephemeral=True)

class SortieGestionView(discord.ui.View):
    def __init__(self, category, auteur, staff_role=None, public_msg: discord.Message = None, ping_msg: discord.Message = None):
        super().__init__(timeout=None)
        self.category = category
        self.auteur = auteur
        self.staff_role = staff_role
        self.public_msg = public_msg
        self.ping_msg = ping_msg

    @discord.ui.button(label="Finalement je ne serai pas là ❌", style=discord.ButtonStyle.danger)
    async def quitter(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id == self.auteur.id:
            return await interaction.response.send_message(
                "❌ Tu ne peux pas quitter ta propre sortie.", ephemeral=True
            )
        # Retirer accès
        for ch in self.category.channels:
            await ch.set_permissions(user, overwrite=None)
        # Décrémenter le compteur
        base, count_str = self.category.name.rsplit(' - ', 1)
        new_count = int(count_str) - 1
        await self.category.edit(name=f"{base} - {new_count}")
        await interaction.response.send_message("🚫 Tu as quitté la sortie.", ephemeral=True)

    @discord.ui.button(label="Sortie passée ✅", style=discord.ButtonStyle.danger)
    async def fermer(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        allowed = user.id == self.auteur.id or (self.staff_role and self.staff_role in user.roles)
        if not allowed:
            return await interaction.response.send_message(
                "❌ Seul l’auteur ou le staff peut fermer.", ephemeral=True
            )
        try:
            # Supprimer salons et catégorie
            for ch in list(self.category.channels):
                await ch.delete()
            await self.category.delete()
            # Supprimer le message public et le ping
            if self.public_msg:
                await self.public_msg.delete()
            if self.ping_msg:
                await self.ping_msg.delete()
            await interaction.response.send_message("✅ Sortie fermée.", ephemeral=True)
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"SortieGestionView: {e}")
            await interaction.response.send_message("❌ Erreur lors de la fermeture.", ephemeral=True)

class LoisirCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ Pas accès.", ephemeral=True)
        else:
            await log_erreur(self.bot, interaction.guild, f"LoisirCommands error: {error}")
            raise error

    @app_commands.command(name="proposer_sortie", description="Propose une sortie sociale ou une activité.")
    @app_commands.check(check_verified)
    async def proposer_sortie(self, interaction: discord.Interaction):
        if not salon_est_autorise("proposer_sortie", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Non autorisé.", ephemeral=True)
        try:
            await interaction.response.send_modal(SortieModal(self.bot, interaction.user))
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"Proposer_sortie: {e}")
            await interaction.response.send_message("❌ Erreur.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(LoisirCommands(bot))
