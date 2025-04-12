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
    save_reaction_role_mapping
)

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reaction_role_messages = load_reaction_role_mapping()

    @app_commands.command(name="definir_salon", description="Définir le salon autorisé pour une commande existante.")
    @app_commands.describe(nom_commande="Choisis une commande existante", salon="Salon autorisé")
    async def definir_salon(self, interaction: discord.Interaction, nom_commande: str, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        definir_salon_autorise(nom_commande, salon.id)
        await interaction.response.send_message(
            f"✅ La commande `{nom_commande}` est désormais accessible uniquement dans {salon.mention}.", ephemeral=True
        )

    @definir_salon.autocomplete("nom_commande")
    async def autocomplete_command_names(self, interaction: discord.Interaction, current: str):
        all_commands = [cmd.name for cmd in self.bot.tree.get_commands()]
        suggestions = [app_commands.Choice(name=cmd, value=cmd) for cmd in all_commands if current.lower() in cmd.lower()]
        return suggestions[:25]

    @app_commands.command(name="definir_redirection", description="Définir la redirection d'un type de message.")
    @app_commands.describe(redirection_type="Ex: burnout, aide", salon="Salon vers lequel rediriger")
    async def definir_redirection(self, interaction: discord.Interaction, redirection_type: str, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        definir_redirection(redirection_type, salon.id)
        await interaction.response.send_message(
            f"✅ Redirection pour `{redirection_type}` définie sur {salon.mention}.", ephemeral=True
        )

    @app_commands.command(name="definir_config", description="Définir une option de configuration générique.")
    @app_commands.describe(option="Nom de l'option", valeur="Valeur de l'option (ex: ID d'un salon)")
    async def definir_config(self, interaction: discord.Interaction, option: str, valeur: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        definir_option_config(option, valeur)
        await interaction.response.send_message(
            f"✅ L'option **{option}** a été mise à jour avec la valeur `{valeur}`.", ephemeral=True
        )

    @app_commands.command(name="creer_role", description="Crée un rôle s’il n’existe pas déjà.")
    @app_commands.describe(nom_du_role="Nom du rôle à créer")
    async def creer_role(self, interaction: discord.Interaction, nom_du_role: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        role = await get_or_create_role(interaction.guild, nom_du_role)
        await interaction.response.send_message(f"✅ Le rôle `{role.name}` est prêt à être utilisé.", ephemeral=True)

    @app_commands.command(name="creer_categorie", description="Crée une catégorie si elle n’existe pas déjà.")
    @app_commands.describe(nom_de_categorie="Nom de la catégorie à créer")
    async def creer_categorie(self, interaction: discord.Interaction, nom_de_categorie: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        category = await get_or_create_category(interaction.guild, nom_de_categorie)
        await interaction.response.send_message(f"✅ La catégorie `{category.name}` est prête à l'emploi.", ephemeral=True)

    @app_commands.command(name="creer_salon", description="Crée un salon texte ou vocal dans une catégorie.")
    @app_commands.describe(nom_salon="Nom du salon à créer", type_salon="texte ou vocal", categorie="Nom de la catégorie cible")
    async def creer_salon(self, interaction: discord.Interaction, nom_salon: str, type_salon: str, categorie: str):
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

    @app_commands.command(name="definir_role_aide", description="Définit le rôle à ping pour les demandes d'aide.")
    @app_commands.describe(role="Rôle à ping pour aider les étudiants")
    async def definir_role_aide(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        from utils.utils import charger_config, sauvegarder_config
        config = charger_config()
        config["role_aide"] = str(role.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Le rôle {role.mention} est défini pour les aides.", ephemeral=True)

    @app_commands.command(name="envoyer_message", description="Envoie un message formaté via modal dans un salon.")
    @app_commands.describe(channel="Salon dans lequel envoyer le message")
    async def envoyer_message(self, interaction: discord.Interaction, channel: discord.TextChannel):
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
                await modal_interaction.response.defer(ephemeral=True)
                await channel.send(self.message_contenu.value)
                await modal_interaction.followup.send("✅ Message envoyé.", ephemeral=True)

        await interaction.response.send_modal(EnvoyerMessageModal())

    @app_commands.command(name="programmer_message", description="Programme un message hebdomadaire via modal.")
    @app_commands.describe(channel="Salon dans lequel envoyer le message")
    async def programmer_message(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)

        class ProgrammerMessageModal(discord.ui.Modal, title="Programmer un message récurrent"):
            message_contenu = discord.ui.TextInput(
                label="Contenu du message",
                style=discord.TextStyle.paragraph,
                placeholder="Tapez ici votre message à envoyer chaque semaine.",
                required=True
            )

            async def on_submit(modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(ephemeral=True)
                contenu = self.message_contenu.value
                await modal_interaction.followup.send("✅ Message programmé pour chaque semaine.", ephemeral=True)
                self.bot.loop.create_task(self.schedule_recurring_message(channel, contenu))

        await interaction.response.send_modal(ProgrammerMessageModal())

    async def schedule_recurring_message(self, channel: discord.TextChannel, contenu: str):
        while True:
            await channel.send(contenu)
            await asyncio.sleep(7 * 24 * 3600)

async def setup_admin_commands(bot):
    await bot.add_cog(AdminCommands(bot))
