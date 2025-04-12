import discord
import asyncio
from discord import app_commands
from discord.ext import commands
from utils.utils import (
    is_admin,
    definir_salon_autorise,
    get_or_create_role,
    get_or_create_category,
    definir_redirection,
    definir_option_config
)

class AdminCommands(commands.Cog):
    # ===================================================================
    # INITIALISATION DU COG : on définit self.bot et on charge le mapping persistant des messages réaction rôle.
    # ===================================================================
    def __init__(self, bot):
        self.bot = bot
        # Charger le mapping persistant des messages Reaction Rôle depuis /DISK
        from utils.utils import load_reaction_role_mapping
        self.reaction_role_messages = load_reaction_role_mapping()

    # ───────────── /definir_salon ─────────────
    @app_commands.command(name="definir_salon", description="Définir le salon autorisé pour une commande existante.")
    @app_commands.describe(nom_commande="Choisis une commande existante", salon="Salon autorisé")
    async def definir_salon(self, interaction: discord.Interaction, nom_commande: str, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        definir_salon_autorise(nom_commande, salon.id)
        await interaction.response.send_message(
            f"✅ La commande `{nom_commande}` est désormais accessible **uniquement** dans {salon.mention}.",
            ephemeral=True
        )

    @definir_salon.autocomplete("nom_commande")
    async def autocomplete_command_names(self, interaction: discord.Interaction, current: str):
        # On récupère toutes les commandes disponibles
        all_commands = [cmd.name for cmd in self.bot.tree.get_commands()]
        # On filtre en fonction de ce que l'utilisateur tape
        suggestions = [app_commands.Choice(name=cmd, value=cmd) for cmd in all_commands if current.lower() in cmd.lower()]
        return suggestions[:25]  # Limite imposée par Discord


    # ───────────── /definir_redirection ─────────────
    @app_commands.command(name="definir_redirection", description="Définir la redirection d'un type de message.")
    @app_commands.describe(redirection_type="Ex: burnout, aide", salon="Salon vers lequel rediriger")
    async def definir_redirection(self, interaction: discord.Interaction, redirection_type: str, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        # Enregistre la redirection dans la config sous la clé "redirections"
        definir_redirection(redirection_type, salon.id)
        await interaction.response.send_message(
            f"✅ Redirection pour `{redirection_type}` définie sur {salon.mention}.",
            ephemeral=True
        )

    # ───────────── /definir_config ─────────────
    @app_commands.command(name="definir_config", description="Définir une option de configuration générique.")
    @app_commands.describe(option="Nom de l'option", valeur="Valeur de l'option (ex: ID d'un salon)")
    async def definir_config(self, interaction: discord.Interaction, option: str, valeur: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        definir_option_config(option, valeur)
        await interaction.response.send_message(
            f"✅ L'option **{option}** a été mise à jour avec la valeur `{valeur}`.",
            ephemeral=True
        )

    # ───────────── /creer_role ─────────────
    @app_commands.command(name="creer_role", description="Crée un rôle s’il n’existe pas déjà.")
    @app_commands.describe(nom_du_role="Nom du rôle à créer")
    async def creer_role(self, interaction: discord.Interaction, nom_du_role: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        role = await get_or_create_role(interaction.guild, nom_du_role)
        await interaction.response.send_message(f"✅ Le rôle `{role.name}` est prêt à être utilisé.", ephemeral=True)

    # ───────────── /creer_categorie ─────────────
    @app_commands.command(name="creer_categorie", description="Crée une catégorie si elle n’existe pas déjà.")
    @app_commands.describe(nom_de_categorie="Nom de la catégorie à créer")
    async def creer_categorie(self, interaction: discord.Interaction, nom_de_categorie: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        category = await get_or_create_category(interaction.guild, nom_de_categorie)
        await interaction.response.send_message(f"✅ La catégorie `{category.name}` est prête à l'emploi.", ephemeral=True)

    # ───────────── /creer_salon ─────────────
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
            f"✅ Le salon `{nom_salon}` ({type_salon}) a été créé dans la catégorie `{categorie}`.",
            ephemeral=True
        )

    # ===================================================================
    # Commande: /creer_roles_reaction_multiples
    # Description: Envoie un message via modal avec réactions pour attribution automatique de rôles.
    # ===================================================================
    @app_commands.command(name="creer_roles_reaction_multiples", description="Crée un message de rôles par réactions via Modal.")
    async def creer_roles_reaction_multiples(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        
        # Modal pour saisir le message et la liste emoji=NomDuRôle
        class ReactionRoleModal(discord.ui.Modal, title="Créer un message de rôles par réactions"):
            message = discord.ui.TextInput(
                label="Message à afficher",
                style=discord.TextStyle.paragraph,
                placeholder="Tapez ici le message qui sera affiché avec les réactions.",
                required=True
            )
            lignes = discord.ui.TextInput(
                label="Emoji=NomDuRôle (une ligne par paire)",
                style=discord.TextStyle.paragraph,
                placeholder="Exemple:\n🔥=Motivé\n📚=En révision\n💤=Fatigué",
                required=True
            )
            async def on_submit(modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(ephemeral=True)
                try:
                    # Envoyer le message dans le salon où la commande a été initiée
                    msg = await interaction.channel.send(self.message.value)
                    mapping = {}
                    # Pour chaque ligne, extraire l'emoji et le nom du rôle
                    for ligne in self.lignes.value.split("\n"):
                        if "=" in ligne:
                            emoji, role_name = ligne.strip().split("=")
                            role = await get_or_create_role(interaction.guild, role_name.strip())
                            mapping[emoji.strip()] = role.id
                            # Ajouter la réaction correspondante
                            await msg.add_reaction(emoji.strip())
                    # Charger le mapping existant, y ajouter celui-ci et sauvegarder
                    from utils.utils import load_reaction_role_mapping, save_reaction_role_mapping
                    persistent_mapping = load_reaction_role_mapping()
                    persistent_mapping[str(msg.id)] = mapping
                    save_reaction_role_mapping(persistent_mapping)
                    # Mettre à jour le mapping en mémoire du cog
                    self.bot.get_cog("AdminCommands").reaction_role_messages = persistent_mapping
                    await modal_interaction.followup.send("✅ Message et réactions créés avec succès !", ephemeral=True)
                except Exception as e:
                    await modal_interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)
        
        await interaction.response.send_modal(ReactionRoleModal())

    # ===================================================================
    # Listener: Attribution de rôle lors de l'ajout d'une réaction
    # ===================================================================
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        msg_id = str(payload.message_id)
        # Charger le mapping depuis le fichier persistant (au cas où il a été modifié récemment)
        from utils.utils import load_reaction_role_mapping
        self.reaction_role_messages = load_reaction_role_mapping()
        if msg_id in self.reaction_role_messages:
            guild = self.bot.get_guild(payload.guild_id)
            if guild is None:
                return
            mapping = self.reaction_role_messages[msg_id]
            emoji_str = str(payload.emoji)
            if emoji_str in mapping:
                role_id = int(mapping[emoji_str])
                role = guild.get_role(role_id)
                if role is None:
                    return
                member = guild.get_member(payload.user_id)
                if member is None:
                    return
                if role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Réaction ajoutée sur message réaction rôle.")
                    except Exception as e:
                        print(f"Erreur lors de l'ajout du rôle : {e}")

    # ===================================================================
    # Listener: Suppression de rôle lors du retrait d'une réaction
    # ===================================================================
    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        msg_id = str(payload.message_id)
        from utils.utils import load_reaction_role_mapping
        self.reaction_role_messages = load_reaction_role_mapping()
        if msg_id in self.reaction_role_messages:
            guild = self.bot.get_guild(payload.guild_id)
            if guild is None:
                return
            mapping = self.reaction_role_messages[msg_id]
            emoji_str = str(payload.emoji)
            if emoji_str in mapping:
                role_id = int(mapping[emoji_str])
                role = guild.get_role(role_id)
                if role is None:
                    return
                member = guild.get_member(payload.user_id)
                if member is None:
                    return
                if role in member.roles:
                    try:
                        await member.remove_roles(role, reason="Réaction retirée sur message réaction rôle.")
                    except Exception as e:
                        print(f"Erreur lors du retrait du rôle : {e}")

    # ───────────── /definir_role_aide ─────────────
    @app_commands.command(name="definir_role_aide", description="Définit le rôle à ping pour les demandes d'aide.")
    @app_commands.describe(role="Rôle à ping pour aider les étudiants")
    async def definir_role_aide(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        # Enregistre l'ID du rôle dans la config sous l'option "role_aide"
        from utils.utils import charger_config, sauvegarder_config
        config = charger_config()
        config["role_aide"] = str(role.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Le rôle {role.mention} a été défini pour être pingé dans les demandes d'aide.", ephemeral=True)

    # ───────────── /envoyer_message ─────────────
    @app_commands.command(name="envoyer_message", description="Envoie un message formaté via modal dans un salon spécifié.")
    @app_commands.describe(channel="Salon dans lequel envoyer le message")
    async def envoyer_message(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        class EnvoyerMessageModal(discord.ui.Modal, title="Envoyer un message"):
            message_contenu = discord.ui.TextInput(
                label="Contenu du message",
                style=discord.TextStyle.paragraph,
                placeholder="Tapez ici votre message, avec sa mise en forme (retours à la ligne, gras, etc.)",
                required=True
            )
            async def on_submit(modal_interaction: discord.Interaction):
                await channel.send(self.message_contenu.value)
                await modal_interaction.response.send_message("✅ Message envoyé.", ephemeral=True)
        await interaction.response.send_modal(EnvoyerMessageModal())

    # ───────────── /programmer_message ─────────────
    @app_commands.command(name="programmer_message", description="Programme l'envoi récurrent d'un message (hebdomadaire) via modal.")
    @app_commands.describe(channel="Salon dans lequel envoyer le message récurrent")
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
                contenu = self.message_contenu.value
                await modal_interaction.response.send_message("✅ Le message programmé a été créé, il sera envoyé chaque semaine.", ephemeral=True)
                self.bot.loop.create_task(self.schedule_recurring_message(channel, contenu))
        await interaction.response.send_modal(ProgrammerMessageModal())

    async def schedule_recurring_message(self, channel: discord.TextChannel, contenu: str):
        while True:
            await channel.send(contenu)
            await asyncio.sleep(7 * 24 * 3600)

async def setup_admin_commands(bot):
    await bot.add_cog(AdminCommands(bot))
