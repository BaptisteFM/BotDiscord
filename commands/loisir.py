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
            pub_id = get_redirection("sortie") or cfg.get("sortie_channel")
            role_id = cfg.get("role_sortie")
            staff_id = cfg.get("role_staff_sortie")

            if not pub_id or not role_id:
                return await interaction.response.send_message("❌ Salon ou rôle non défini.", ephemeral=True)

            guild = interaction.guild
            salon_pub = guild.get_channel(int(pub_id))
            role = guild.get_role(int(role_id))
            role_staff = guild.get_role(int(staff_id)) if staff_id else None
            if not salon_pub or not role:
                return await interaction.response.send_message("❌ Configuration invalide.", ephemeral=True)

            # Ping visible
            await salon_pub.send(role.mention)

            # Créer catégorie privée avec author et staff
            chan_name = f"sortie-{self.jour.value.replace(' ','-')}-{self.auteur.id} - 1"
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                self.auteur: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            if role_staff:
                overwrites[role_staff] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            category = await guild.create_category(chan_name, overwrites=overwrites)
            txt = await guild.create_text_channel("discussion-sortie", category=category)
            await guild.create_voice_channel("vocal-sortie", category=category)

            # Alerte auteur dans privé
            await txt.send(f"🔔 {self.auteur.mention}, ta sortie est ici !", view=SupprimerSortieView(category, self.auteur, role_staff))

            # Message public embed + participation
            desc = f"**Date :** {self.jour.value}\n**Lieu :** {self.lieu.value}\n**Activité :** {self.activite.value}"
            if self.details.value:
                desc += f"\n\n{self.details.value}"
            embed = discord.Embed(title="📢 Nouvelle sortie proposée !", description=desc, color=discord.Color.green())
            embed.set_footer(text=f"Proposée par {self.auteur.display_name}")
            view = ParticiperSortieView(self.bot, category, self.auteur)
            await salon_pub.send(embed=embed, view=view)

            await interaction.response.send_message("✅ Sortie proposée avec succès !", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ Erreur lors de la proposition.", ephemeral=True)
            await log_erreur(self.bot, interaction.guild, f"SortieModal: {e}")

class ParticiperSortieView(discord.ui.View):
    def __init__(self, bot, category: discord.CategoryChannel, auteur: discord.Member):
        super().__init__(timeout=None)
        self.bot = bot
        self.category = category
        self.auteur = auteur
        self.participants = {auteur.id}

    @discord.ui.button(label="Je suis chaud(e) 🔥", style=discord.ButtonStyle.success)
    async def rejoindre(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id in self.participants:
            return await interaction.response.send_message("ℹ️ Tu es déjà inscrit.", ephemeral=True)
        # Ajouter permissions
        for ch in self.category.channels:
            await ch.set_permissions(user, read_messages=True, send_messages=True)
        self.participants.add(user.id)
        # Mettre à jour nom catégorie
        base = self.category.name.rsplit(' - ',1)[0]
        await self.category.edit(name=f"{base} - {len(self.participants)}")
        # Ajouter bouton quitter sauf auteur
        if user.id != self.auteur.id:
            self.add_item(QuitterButton(self.category, self.participants, self.auteur))
        await interaction.response.send_message("✅ Inscrit à la sortie!", ephemeral=True)

class QuitterButton(discord.ui.Button):
    def __init__(self, category, participants, auteur):
        super().__init__(label="Finalement je ne serai pas là ❌", style=discord.ButtonStyle.danger)
        self.category = category
        self.participants = participants
        self.auteur = auteur

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        if user.id == self.auteur.id:
            return await interaction.response.send_message("❌ Tu ne peux pas quitter ta propre sortie.", ephemeral=True)
        # Retirer perms
        for ch in self.category.channels:
            await ch.set_permissions(user, overwrite=None)
        self.participants.discard(user.id)
        base = self.category.name.rsplit(' - ',1)[0]
        await self.category.edit(name=f"{base} - {len(self.participants)}")
        await interaction.response.send_message("🚫 Tu as quitté la sortie.", ephemeral=True)

class SupprimerSortieView(discord.ui.View):
    def __init__(self, category, auteur, staff_role=None):
        super().__init__(timeout=None)
        self.category = category
        self.auteur = auteur
        self.staff_role = staff_role

    @discord.ui.button(label="Sortie passée ✅", style=discord.ButtonStyle.danger)
    async def fermer(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id != self.auteur.id and (not self.staff_role or self.staff_role.id not in [r.id for r in user.roles]):
            return await interaction.response.send_message("❌ Seul l’auteur ou le staff peut fermer.", ephemeral=True)
        try:
            for ch in list(self.category.channels):
                await ch.delete()
            await self.category.delete()
            await interaction.response.send_message("✅ Sortie fermée.", ephemeral=True)
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"Supprimer: {e}")
            await interaction.response.send_message("❌ Erreur lors de la fermeture.", ephemeral=True)

class LoisirCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction, error):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("❌ Pas accès.", ephemeral=True)
        else:
            await log_erreur(self.bot, interaction.guild, f"Loisir: {error}")
            raise error

    @app_commands.command(name="proposer_sortie", description="Propose une sortie sociale ou une activité.")
    @app_commands.check(check_verified)
    async def proposer_sortie(self, interaction: discord.Interaction):
        if not salon_est_autorise("proposer_sortie", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Non autorisé.", ephemeral=True)
        try:
            await interaction.response.send_modal(SortieModal(self.bot, interaction.user))
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"Proposer: {e}")
            await interaction.response.send_message("❌ Erreur.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(LoisirCommands(bot))
