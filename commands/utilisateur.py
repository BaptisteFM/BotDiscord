import discord
from discord import app_commands
from discord.ext import commands
import random
import json
import os
from utils.utils import salon_est_autorise, get_or_create_role, charger_config, log_erreur, is_verified_user
from commands.missions import charger_liste, MISSIONS_PATH, CONSEILS_PATH


RESOURCES_PATH = "/data/ressources.json"

def load_resources() -> list[dict]:
    """Retourne la liste des ressources [{name, url}, …]."""
    if not os.path.exists(RESOURCES_PATH):
        return []
    with open(RESOURCES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_resources(resources: list[dict]) -> None:
    """Sauvegarde la liste des ressources."""
    os.makedirs(os.path.dirname(RESOURCES_PATH), exist_ok=True)
    with open(RESOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(resources, f, indent=4, ensure_ascii=False)


async def check_verified(interaction: discord.Interaction) -> bool:
    if await is_verified_user(interaction.user):
        return True
    raise app_commands.CheckFailure("Commande réservée aux membres vérifiés.")

class UtilisateurCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Vous n'avez pas accès aux commandes utilisateurs. Si vous rencontrez un problème, contactez le staff.",
                ephemeral=True
            )
        else:
            await log_erreur(self.bot, interaction.guild, f"UtilisateurCommands error: {error}")
            raise error

    async def check_salon(self, interaction: discord.Interaction, command_name: str) -> bool:
        result = salon_est_autorise(command_name, interaction.channel_id, interaction.user)
        if result is False:
            await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
            return False
        elif result == "admin_override":
            await interaction.response.send_message("⚠️ Commande exécutée dans un salon non autorisé. (Admin override)", ephemeral=True)
        return True

    @app_commands.command(name="conseil_methodo", description="Pose une question méthodo (public).")
    @app_commands.describe(question="Quelle est ta question méthodo ?")
    @app_commands.check(check_verified)
    async def conseil_methodo(self, interaction: discord.Interaction, question: str):
        if not await self.check_salon(interaction, "conseil_methodo"):
            return
        try:
            embed = discord.Embed(title="Nouvelle question méthodo", description=question, color=discord.Color.blurple())
            embed.set_footer(text=f"Posée par {interaction.user.display_name}")
            await interaction.channel.send(embed=embed)
            await interaction.followup.send("✅ Ta question a été envoyée !", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"Erreur dans /conseil_methodo : {e}")


    @app_commands.command(name="ressources", description="Liste des ressources utiles.")
    @app_commands.check(check_verified)
    async def ressources(self, interaction: discord.Interaction):
        if not await self.check_salon(interaction, "ressources"):
            return

        ressources = load_resources()
        if not ressources:
            return await interaction.response.send_message(
                "ℹ️ Il n'y a pas de ressources pour le moment, le staff va s'en charger d'ici peu !", ephemeral=True )

        embed = discord.Embed(
            title="📚 Ressources utiles",
            description="Voici la liste des ressources disponibles :",
            color=discord.Color.green()
        )
        for i, entry in enumerate(ressources):
            embed.add_field(
                name=f"{i}. {entry['name']}",
                value=entry["url"],
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


    @app_commands.command(
        name="mission_du_jour",
        description="Obtiens un mini-défi pour la journée."
    )
    @app_commands.check(check_verified)
    async def mission_du_jour(self, interaction: discord.Interaction):
        # salon_est_autorise est SYNCHRONE !
        if not salon_est_autorise("mission_du_jour", interaction.channel_id, interaction.user):
            return await interaction.response.send_message(
                "❌ Commande non autorisée ici.", ephemeral=True
            )

        try:
            missions = charger_liste(MISSIONS_PATH)
            if not missions:
                return await interaction.response.send_message(
                    "ℹ️ Aucune mission définie par l’admin.", ephemeral=True
                )
            mission = random.choice(missions)
            await interaction.response.send_message(
                f"🎯 Mission du jour : **{mission}**", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "❌ Erreur lors de la récupération de la mission.", ephemeral=True
            )
            await log_erreur(self.bot, interaction.guild, f"mission_du_jour: {e}")

    @app_commands.command(
        name="conseil_aleatoire",
        description="Donne un conseil de travail aléatoire."
    )
    @app_commands.check(check_verified)
    async def conseil_aleatoire(self, interaction: discord.Interaction):
        if not salon_est_autorise("conseil_aleatoire", interaction.channel_id, interaction.user):
            return await interaction.response.send_message(
                "❌ Commande non autorisée ici.", ephemeral=True
            )

        try:
            conseils = charger_liste(CONSEILS_PATH)
            if not conseils:
                return await interaction.response.send_message(
                    "ℹ️ Aucun conseil défini par l’admin.", ephemeral=True
                )
            conseil = random.choice(conseils)
            await interaction.response.send_message(
                f"💡 Conseil : **{conseil}**", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                "❌ Erreur lors de la récupération du conseil.", ephemeral=True
            )
            await log_erreur(self.bot, interaction.guild, f"conseil_aleatoire: {e}")


    @app_commands.command(name="cours_aide", description="Demande d'aide sur un cours via modal.")
    @app_commands.check(check_verified)
    async def cours_aide(self, interaction: discord.Interaction):
        if not await self.check_salon(interaction, "cours_aide"):
            return
        
        # Construit le nom unique de la catégorie d'aide pour cet utilisateur
        category_name = f"cours-aide-{interaction.user.name}-{interaction.user.id}".lower()
        existing_category = discord.utils.get(interaction.guild.categories, name=category_name)
        if existing_category:
            return await interaction.response.send_message(
                f"ℹ️ Vous avez déjà un espace d'aide ouvert : {existing_category.mention}. Veuillez le fermer avant de créer un nouveau.",
                ephemeral=True
            )

        class CoursAideModal(discord.ui.Modal, title="Demande d'aide sur un cours"):
            cours = discord.ui.TextInput(
                label="Cours concerné", 
                placeholder="Ex: Mathématiques, Physique, etc.", 
                required=True
            )
            details = discord.ui.TextInput(
                label="Détaillez votre problème",
                style=discord.TextStyle.paragraph,
                placeholder="Expliquez précisément ce que vous n'avez pas compris.",
                required=True
            )

            async def on_submit(self, modal_interaction: discord.Interaction):
                try:
                    await modal_interaction.response.defer()
                    user = modal_interaction.user
                    guild = modal_interaction.guild

                    # Création d'un rôle temporaire unique pour cet espace d'aide
                    temp_role = await get_or_create_role(guild, f"CoursAide-{user.name}-{user.id}")
                    await user.add_roles(temp_role)

                    config = charger_config()
                    role_aide_id = config.get("role_aide")
                    role_aide = guild.get_role(int(role_aide_id)) if role_aide_id else None

                    # Définition des permissions pour la catégorie
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        temp_role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    }
                    if role_aide:
                        overwrites[role_aide] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

                    # Création de la catégorie d'aide
                    category = await guild.create_category(category_name, overwrites=overwrites)
                    # Création des salons dans la catégorie
                    discussion_channel = await guild.create_text_channel("discussion", category=category)
                    voice_channel = await guild.create_voice_channel("support-voice", category=category)

                    # Envoi du message récapitulatif dans le salon "discussion"
                    message_content = (
                        f"🔔 {role_aide.mention if role_aide else ''} Demande d'aide créée par {user.mention} !\n"
                        f"**Cours :** {self.cours.value}\n**Détails :** {self.details.value}"
                    )
                    await discussion_channel.send(message_content)

                    # Envoi d'un embed récapitulatif avec la vue permettant de supprimer l'espace
                    description = f"**Cours :** {self.cours.value}\n**Détails :** {self.details.value}"
                    embed = discord.Embed(title="Demande d'aide sur un cours", description=description, color=discord.Color.blue())
                    embed.set_footer(text=f"Demandée par {user.display_name}")
                    view = CoursAideView(user, category, temp_role)
                    await modal_interaction.followup.send(embed=embed, view=view)
                except Exception as e:
                    await modal_interaction.followup.send("❌ Une erreur est survenue lors de la création de l'espace d'aide.", ephemeral=True)
                    await log_erreur(self.bot, guild, f"Erreur dans /cours_aide (on_submit) : {e}")

        try:
            await interaction.response.send_modal(CoursAideModal())
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"Erreur lors de l'ouverture du modal /cours_aide : {e}")
            await interaction.followup.send("❌ Erreur lors de l'ouverture du formulaire.", ephemeral=True)

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
        # Seul le demandeur peut supprimer l'espace d'aide
        if interaction.user != self.demandeur:
            return await interaction.response.send_message("❌ Seul le demandeur peut supprimer cet espace d'aide.", ephemeral=True)
        try:
            await interaction.response.defer(ephemeral=True)
            # Retirer le rôle temporaire de tous les membres
            for member in list(self.temp_role.members):
                await member.remove_roles(self.temp_role)
            # Supprimer le rôle temporaire
            await self.temp_role.delete()
            # Supprimer tous les salons dans la catégorie
            for channel in self.category.channels:
                try:
                    await channel.delete()
                except Exception as e:
                    await log_erreur(interaction.client, interaction.guild, f"Erreur lors de la suppression du salon {channel.name}: {e}")
            # Supprimer la catégorie
            await self.category.delete()
            # Supprimer le message de la vue (si possible)
            try:
                await interaction.message.delete()
            except Exception:
                pass
            await interaction.followup.send("✅ Votre espace d'aide a été fermé avec succès.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la suppression : {e}", ephemeral=True)
    

async def setup_user_commands(bot):
    await bot.add_cog(UtilisateurCommands(bot))
