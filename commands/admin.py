import discord
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
    charger_config,
    sauvegarder_config,
    log_erreur  # ✅ Fonction centralisée de log
)

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reaction_role_messages = load_reaction_role_mapping()

    # ───────────── Définir salon autorisé ─────────────
    @app_commands.command(name="definir_salon", description="Définir le salon autorisé pour une commande.")
    async def definir_salon(self, interaction: discord.Interaction, nom_commande: str, salon: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            definir_salon_autorise(nom_commande, salon.id)
            await interaction.response.send_message(f"✅ Salon défini pour `{nom_commande}` : {salon.mention}", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"definir_salon\n{e}")
            await interaction.response.send_message("❌ Erreur lors de la définition du salon.", ephemeral=True)

    @definir_salon.autocomplete("nom_commande")
    async def autocomplete_command_names(self, interaction: discord.Interaction, current: str):
        try:
            all_commands = [cmd.name for cmd in self.bot.tree.get_commands()]
            suggestions = [app_commands.Choice(name=cmd, value=cmd) for cmd in all_commands if current.lower() in cmd.lower()]
            return suggestions[:25]
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"autocomplete_command_names\n{e}")
            return []

    # ───────────── Redirections / Configs / Logs ─────────────
    @app_commands.command(name="definir_redirection", description="Rediriger un type de message vers un salon.")
    async def definir_redirection(self, interaction: discord.Interaction, redirection_type: str, salon: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            definir_redirection(redirection_type, salon.id)
            await interaction.response.send_message(f"✅ Redirection `{redirection_type}` → {salon.mention}", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"definir_redirection\n{e}")
            await interaction.response.send_message("❌ Erreur lors de la redirection.", ephemeral=True)

    @app_commands.command(name="definir_config", description="Définir une option de configuration générique.")
    async def definir_config(self, interaction: discord.Interaction, option: str, valeur: str):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            definir_option_config(option, valeur)
            await interaction.response.send_message(f"✅ Option `{option}` définie à `{valeur}`", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"definir_config\n{e}")
            await interaction.response.send_message("❌ Erreur lors de la configuration.", ephemeral=True)

    @app_commands.command(name="definir_log_erreurs", description="Définit le salon de logs d’erreurs techniques.")
    async def definir_log_erreurs(self, interaction: discord.Interaction, salon: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            config = charger_config()
            config["log_erreurs_channel"] = str(salon.id)
            sauvegarder_config(config)
            await interaction.response.send_message(f"✅ Salon de logs défini : {salon.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("❌ Erreur lors de la configuration du salon de logs.", ephemeral=True)

    # ───────────── Création de rôles / catégories / salons ─────────────
    @app_commands.command(name="creer_role", description="Crée un rôle s’il n’existe pas déjà.")
    async def creer_role(self, interaction: discord.Interaction, nom_du_role: str):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            role = await get_or_create_role(interaction.guild, nom_du_role)
            await interaction.response.send_message(f"✅ Rôle prêt : `{role.name}`", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_role\n{e}")
            await interaction.response.send_message("❌ Erreur lors de la création du rôle.", ephemeral=True)

    @app_commands.command(name="creer_categorie", description="Crée une catégorie si elle n’existe pas déjà.")
    async def creer_categorie(self, interaction: discord.Interaction, nom_de_categorie: str):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            category = await get_or_create_category(interaction.guild, nom_de_categorie)
            await interaction.response.send_message(f"✅ Catégorie créée : `{category.name}`", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_categorie\n{e}")
            await interaction.response.send_message("❌ Erreur lors de la création de la catégorie.", ephemeral=True)

    @app_commands.command(name="creer_salon", description="Crée un salon texte ou vocal dans une catégorie.")
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
                return await interaction.response.send_message("❌ Type invalide (texte ou vocal)", ephemeral=True)
            await interaction.response.send_message(f"✅ Salon `{nom_salon}` créé dans `{categorie}`", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_salon\n{e}")
            await interaction.response.send_message("❌ Erreur lors de la création du salon.", ephemeral=True)

    # ───────────── Commande pour définir le rôle d’aide ─────────────
    @app_commands.command(name="definir_role_aide", description="Définit le rôle ping pour aider les étudiants.")
    async def definir_role_aide(self, interaction: discord.Interaction, role: discord.Role):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            definir_option_config("role_aide", str(role.id))
            await interaction.response.send_message(f"✅ Rôle d’aide défini : {role.mention}", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"definir_role_aide\n{e}")
            await interaction.response.send_message("❌ Erreur lors de la configuration du rôle.", ephemeral=True)

    # ───────────── Modal : envoyer un message formaté ─────────────
    @app_commands.command(name="envoyer_message", description="Envoie un message formaté dans un salon via modal.")
    async def envoyer_message(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)

            class Modal(discord.ui.Modal, title="Envoi de message"):
                contenu = discord.ui.TextInput(
                    label="Contenu du message",
                    style=discord.TextStyle.paragraph,
                    placeholder="Tape ton message ici...",
                    required=True
                )

                async def on_submit(self_inner, modal_interaction: discord.Interaction):
                    try:
                        await modal_interaction.response.defer(ephemeral=True)
                        await channel.send(self_inner.contenu.value)
                        await modal_interaction.followup.send("✅ Message envoyé !", ephemeral=True)
                    except Exception as e:
                        await log_erreur(self.bot, interaction.guild, f"envoyer_message (on_submit)\n{e}")
                        await modal_interaction.followup.send("❌ Erreur lors de l’envoi.", ephemeral=True)

            await interaction.response.send_modal(Modal())

        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"envoyer_message\n{e}")
            await interaction.response.send_message("❌ Erreur lors de l’ouverture du modal.", ephemeral=True)

# ───────────── Ajout du Cog ─────────────
async def setup_admin_commands(bot):
    await bot.add_cog(AdminCommands(bot))
