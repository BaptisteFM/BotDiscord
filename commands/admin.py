import discord
import asyncio
from discord import app_commands
from discord.ext import commands
from utils.utils import (
    is_admin,
    salon_est_autorise,
    definir_salon_autorise,
    get_or_create_role,
    get_or_create_category,
    definir_redirection,
    definir_option_config,
    load_reaction_role_mapping,
    save_reaction_role_mapping,
    charger_config
)

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reaction_role_messages = load_reaction_role_mapping()

    async def log_erreur(self, interaction: discord.Interaction, error: Exception):
        try:
            config = charger_config()
            channel_id = config.get("log_erreurs_channel")
            if channel_id:
                channel = interaction.guild.get_channel(int(channel_id))
                if channel:
                    embed = discord.Embed(
                        title="⚠️ Erreur dans une commande",
                        description=f"**Commande :** `{interaction.command.name}`\n"
                                    f"**Utilisateur :** {interaction.user.mention}\n"
                                    f"**Erreur :** ```{str(error)}```",
                        color=discord.Color.red()
                    )
                    await channel.send(embed=embed)
        except:
            pass

    @app_commands.command(name="definir_salon", description="Définir le salon autorisé pour une commande existante.")
    @app_commands.describe(nom_commande="Choisis une commande existante", salon="Salon autorisé")
    async def definir_salon(self, interaction: discord.Interaction, nom_commande: str, salon: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            definir_salon_autorise(nom_commande, salon.id)
            await interaction.response.send_message(
                f"✅ La commande `{nom_commande}` est désormais accessible uniquement dans {salon.mention}.", ephemeral=True
            )
        except Exception as e:
            await self.log_erreur(interaction, e)
            await interaction.response.send_message("❌ Erreur lors de la définition du salon.", ephemeral=True)

    @definir_salon.autocomplete("nom_commande")
    async def autocomplete_command_names(self, interaction: discord.Interaction, current: str):
        all_commands = [cmd.name for cmd in self.bot.tree.get_commands()]
        suggestions = [app_commands.Choice(name=cmd, value=cmd) for cmd in all_commands if current.lower() in cmd.lower()]
        return suggestions[:25]

    @app_commands.command(name="definir_redirection", description="Définir la redirection d'un type de message.")
    @app_commands.describe(redirection_type="Ex: burnout, aide", salon="Salon vers lequel rediriger")
    async def definir_redirection(self, interaction: discord.Interaction, redirection_type: str, salon: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            definir_redirection(redirection_type, salon.id)
            await interaction.response.send_message(
                f"✅ Redirection pour `{redirection_type}` définie sur {salon.mention}.", ephemeral=True
            )
        except Exception as e:
            await self.log_erreur(interaction, e)
            await interaction.response.send_message("❌ Erreur lors de la redirection.", ephemeral=True)

    @app_commands.command(name="definir_config", description="Définir une option de configuration générique.")
    @app_commands.describe(option="Nom de l'option", valeur="Valeur de l'option (ex: ID d'un salon)")
    async def definir_config(self, interaction: discord.Interaction, option: str, valeur: str):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            definir_option_config(option, valeur)
            await interaction.response.send_message(
                f"✅ L'option **{option}** a été mise à jour avec la valeur `{valeur}`.", ephemeral=True
            )
        except Exception as e:
            await self.log_erreur(interaction, e)
            await interaction.response.send_message("❌ Erreur lors de la configuration.", ephemeral=True)

    @app_commands.command(name="creer_role", description="Crée un rôle s’il n’existe pas déjà.")
    @app_commands.describe(nom_du_role="Nom du rôle à créer")
    async def creer_role(self, interaction: discord.Interaction, nom_du_role: str):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            role = await get_or_create_role(interaction.guild, nom_du_role)
            await interaction.response.send_message(f"✅ Le rôle `{role.name}` est prêt à être utilisé.", ephemeral=True)
        except Exception as e:
            await self.log_erreur(interaction, e)
            await interaction.response.send_message("❌ Erreur lors de la création du rôle.", ephemeral=True)

    @app_commands.command(name="creer_categorie", description="Crée une catégorie si elle n’existe pas déjà.")
    @app_commands.describe(nom_de_categorie="Nom de la catégorie à créer")
    async def creer_categorie(self, interaction: discord.Interaction, nom_de_categorie: str):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            category = await get_or_create_category(interaction.guild, nom_de_categorie)
            await interaction.response.send_message(f"✅ La catégorie `{category.name}` est prête à l'emploi.", ephemeral=True)
        except Exception as e:
            await self.log_erreur(interaction, e)
            await interaction.response.send_message("❌ Erreur lors de la création de la catégorie.", ephemeral=True)

    @app_commands.command(name="creer_salon", description="Crée un salon texte ou vocal dans une catégorie.")
    @app_commands.describe(nom_salon="Nom du salon à créer", type_salon="texte ou vocal", categorie="Nom de la catégorie cible")
    async def creer_salon(self, interaction: discord.Interaction, nom_salon: str, type_salon: str, categorie: str):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            category = await get_or_create_category(interaction.guild, categorie)
            if type_salon.lower() == "texte":
                await interaction.guild.create_text_channel(nom_salon, category=category)
            elif type_salon.lower() == "vocal":
                await interaction.guild.create_voice_channel(nom_salon, category=category)
            else:
                return await interaction.response.send_message("❌ Type de salon invalide (texte ou vocal).", ephemeral=True)
            await interaction.response.send_message(
                f"✅ Le salon `{nom_salon}` ({type_salon}) a été créé dans la catégorie `{categorie}`.", ephemeral=True
            )
        except Exception as e:
            await self.log_erreur(interaction, e)
            await interaction.response.send_message("❌ Erreur lors de la création du salon.", ephemeral=True)

    @app_commands.command(name="definir_role_aide", description="Définit le rôle à ping pour les demandes d'aide.")
    @app_commands.describe(role="Rôle à ping pour aider les étudiants")
    async def definir_role_aide(self, interaction: discord.Interaction, role: discord.Role):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            config = charger_config()
            config["role_aide"] = str(role.id)
            definir_option_config("role_aide", str(role.id))
            await interaction.response.send_message(f"✅ Le rôle {role.mention} est défini pour les aides.", ephemeral=True)
        except Exception as e:
            await self.log_erreur(interaction, e)
            await interaction.response.send_message("❌ Erreur lors de la définition du rôle d'aide.", ephemeral=True)

    @app_commands.command(name="envoyer_message", description="Envoie un message formaté via modal dans un salon.")
    @app_commands.describe(channel="Salon dans lequel envoyer le message")
    async def envoyer_message(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)

            class EnvoyerMessageModal(discord.ui.Modal, title="Envoyer un message"):
                message_contenu = discord.ui.TextInput(
                    label="Contenu du message",
                    style=discord.TextStyle.paragraph,
                    placeholder="Tapez ici votre message avec mise en forme",
                    required=True
                )

                async def on_submit(modal_interaction: discord.Interaction):
                    try:
                        await modal_interaction.response.defer(ephemeral=True)
                        await channel.send(self.message_contenu.value)
                        await modal_interaction.followup.send("✅ Message envoyé.", ephemeral=True)
                    except Exception as e:
                        await self.log_erreur(modal_interaction, e)
                        await modal_interaction.followup.send("❌ Erreur lors de l'envoi du message.", ephemeral=True)

            await interaction.response.send_modal(EnvoyerMessageModal())
        except Exception as e:
            await self.log_erreur(interaction, e)
            await interaction.response.send_message("❌ Erreur lors de l'ouverture du modal.", ephemeral=True)

    @app_commands.command(name="definir_log_erreurs", description="Définit le salon de logs d’erreurs techniques.")
    @app_commands.describe(salon="Salon où envoyer les erreurs (réservé aux admins)")
    async def definir_log_erreurs(self, interaction: discord.Interaction, salon: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            definir_option_config("log_erreurs_channel", str(salon.id))
            await interaction.response.send_message(f"✅ Salon de logs d’erreurs défini : {salon.mention}", ephemeral=True)
        except Exception as e:
            await self.log_erreur(interaction, e)
            await interaction.response.send_message("❌ Erreur lors de la configuration du salon de logs.", ephemeral=True)


async def setup_admin_commands(bot):
    await bot.add_cog(AdminCommands(bot))
