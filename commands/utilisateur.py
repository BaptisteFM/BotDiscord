import discord
from discord import app_commands
from discord.ext import commands
import random
from utils.utils import (
    salon_est_autorise, get_or_create_role, get_or_create_category, charger_config
)

class UtilisateurCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conseils = [
            "🧠 Répète tes cours à haute voix comme si tu les expliquais à quelqu’un.",
            "⏱️ Utilise la méthode Pomodoro pour gérer ton temps de travail.",
            "📚 Teste-toi sur des QCM plutôt que de relire passivement.",
            "📝 Fais des fiches synthétiques par thème plutôt que par ordre de cours.",
            "🤝 Échange avec tes camarades – enseigner est la meilleure façon d'apprendre."
        ]

    async def check_salon(self, interaction: discord.Interaction, command_name: str) -> bool:
        result = salon_est_autorise(command_name, interaction.channel_id, interaction.user)
        if result is False:
            await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
            return False
        elif result == "admin_override":
            await interaction.response.send_message("⚠️ Commande exécutée dans un salon non autorisé. (Admin override)", ephemeral=True)
        return True

    async def log_error(self, guild: discord.Guild, commande: str, erreur: Exception):
        config = charger_config()
        salon_log_id = config.get("log_erreurs_channel")
        if not salon_log_id:
            return
        salon_log = guild.get_channel(int(salon_log_id))
        if salon_log:
            embed = discord.Embed(
                title=f"❌ Erreur dans la commande : `{commande}`",
                description=f"```{str(erreur)}```",
                color=discord.Color.red()
            )
            await salon_log.send(embed=embed)

    @app_commands.command(name="conseil_methodo", description="Pose une question méthodo (public).")
    @app_commands.describe(question="Quelle est ta question méthodo ?")
    async def conseil_methodo(self, interaction: discord.Interaction, question: str):
        if not await self.check_salon(interaction, "conseil_methodo"):
            return
        try:
            embed = discord.Embed(title="Nouvelle question méthodo", description=question, color=discord.Color.blurple())
            embed.set_footer(text=f"Posée par {interaction.user.display_name}")
            await interaction.channel.send(embed=embed)
            await interaction.followup.send("✅ Ta question a été envoyée !", ephemeral=True)
        except Exception as e:
            await self.log_error(interaction.guild, "conseil_methodo", e)

    @app_commands.command(name="conseil_aleatoire", description="Donne un conseil de travail aléatoire.")
    async def conseil_aleatoire(self, interaction: discord.Interaction):
        if not await self.check_salon(interaction, "conseil_aleatoire"):
            return
        try:
            conseil = random.choice(self.conseils)
            await interaction.response.send_message(f"💡 Conseil : **{conseil}**", ephemeral=True)
        except Exception as e:
            await self.log_error(interaction.guild, "conseil_aleatoire", e)

    @app_commands.command(name="ressources", description="Liste des ressources utiles.")
    async def ressources(self, interaction: discord.Interaction):
        if not await self.check_salon(interaction, "ressources"):
            return
        try:
            embed = discord.Embed(
                title="Ressources utiles",
                description="Voici quelques liens et documents qui pourraient t'aider :",
                color=discord.Color.green()
            )
            embed.add_field(name="🔗 Fiches Méthodo", value="[Accéder](https://exemple.com/fiches)", inline=False)
            embed.add_field(name="📝 Tableur de planning", value="[Google Sheets](https://docs.google.com)", inline=False)
            embed.add_field(name="🎧 Podcast Motivation", value="[Podcast X](https://podcast.com)", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await self.log_error(interaction.guild, "ressources", e)

    @app_commands.command(name="mission_du_jour", description="Obtiens un mini-défi pour la journée.")
    async def mission_du_jour(self, interaction: discord.Interaction):
        if not await self.check_salon(interaction, "mission_du_jour"):
            return
        try:
            missions = [
                "📵 Évite les réseaux sociaux jusqu'à 20h.",
                "🧘‍♂️ Fais 5 min de respiration avant de réviser.",
                "📖 Relis 2 fiches avant le coucher.",
                "💌 Envoie un message d'encouragement à un camarade.",
                "🧹 Range ton espace de travail pour gagner en clarté."
            ]
            await interaction.response.send_message(f"🎯 Mission du jour : **{random.choice(missions)}**", ephemeral=True)
        except Exception as e:
            await self.log_error(interaction.guild, "mission_du_jour", e)

    @app_commands.command(name="checkin", description="Exprime ton humeur avec un emoji.")
    @app_commands.describe(humeur="Ex: 😀, 😞, 😴, etc.")
    async def checkin(self, interaction: discord.Interaction, humeur: str):
        if not await self.check_salon(interaction, "checkin"):
            return
        try:
            await interaction.response.send_message(f"📌 Humeur enregistrée : {humeur}", ephemeral=True)
        except Exception as e:
            await self.log_error(interaction.guild, "checkin", e)

    @app_commands.command(name="cours_aide", description="Demande d'aide sur un cours via modal.")
    async def cours_aide(self, interaction: discord.Interaction):
        if not await self.check_salon(interaction, "cours_aide"):
            return

        class CoursAideModal(discord.ui.Modal, title="Demande d'aide sur un cours"):
            cours = discord.ui.TextInput(label="Cours concerné", placeholder="Ex : Mathématiques, Physique, etc.", required=True)
            details = discord.ui.TextInput(
                label="Détaillez votre problème",
                style=discord.TextStyle.paragraph,
                placeholder="Expliquez précisément ce que vous n'avez pas compris.",
                required=True
            )

            async def on_submit(modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(thinking=False, ephemeral=True)
                try:
                    user = modal_interaction.user
                    guild = modal_interaction.guild

                    temp_role = await get_or_create_role(guild, f"CoursAide-{user.name}-{user.id}")
                    await user.add_roles(temp_role)

                    config = charger_config()
                    role_aide_id = config.get("role_aide")
                    role_aide = guild.get_role(int(role_aide_id)) if role_aide_id else None

                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        temp_role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    }
                    if role_aide:
                        overwrites[role_aide] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

                    category = await guild.create_category(f"cours-aide-{user.name}-{user.id}".lower(), overwrites=overwrites)
                    discussion_channel = await guild.create_text_channel("discussion", category=category)
                    await guild.create_voice_channel("support-voice", category=category)

                    if role_aide:
                        await discussion_channel.send(f"🔔 {role_aide.mention} une demande d'aide a été créée par {user.mention} !")

                    description = f"**Cours :** {self.cours.value}\n**Détails :** {self.details.value}"
                    embed = discord.Embed(title="Demande d'aide sur un cours", description=description, color=discord.Color.blue())
                    embed.set_footer(text=f"Demandée par {user.display_name}")
                    view = CoursAideView(user, category, temp_role)
                    await modal_interaction.followup.send(embed=embed, view=view, ephemeral=True)

                except Exception as e:
                    await modal_interaction.followup.send("❌ Une erreur est survenue lors de la création de l'espace d'aide.", ephemeral=True)
                    await UtilisateurCommands.log_error(self, guild, "cours_aide", e)

        await interaction.response.send_modal(CoursAideModal())

class CoursAideView(discord.ui.View):
    def __init__(self, demandeur: discord.Member, category: discord.CategoryChannel, temp_role: discord.Role):
        super().__init__(timeout=None)
        self.demandeur = demandeur
        self.category = category
        self.temp_role = temp_role

    @discord.ui.button(label="J'ai aussi ce problème", style=discord.ButtonStyle.primary, custom_id="btn_probleme")
    async def probleme_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.temp_role not in interaction.user.roles:
            await interaction.user.add_roles(self.temp_role)
            await interaction.response.send_message("✅ Vous avez rejoint cette demande d'aide.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ Vous êtes déjà associé à cette demande.", ephemeral=True)

    @discord.ui.button(label="Supprimer la demande", style=discord.ButtonStyle.danger, custom_id="btn_supprimer")
    async def supprimer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.demandeur:
            return await interaction.response.send_message("❌ Seul le demandeur peut supprimer cette demande.", ephemeral=True)
        try:
            await self.category.delete()
            await self.demandeur.remove_roles(self.temp_role)
            await interaction.response.send_message("✅ Demande supprimée ; la catégorie privée et le rôle temporaire ont été retirés.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la suppression : {e}", ephemeral=True)

# ───────────── SETUP ─────────────
async def setup_user_commands(bot):
    await bot.add_cog(UtilisateurCommands(bot))
