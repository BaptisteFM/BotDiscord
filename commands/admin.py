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
    log_erreur
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
            # ATTENTION : utilisez les noms de commandes actuels, par exemple "cours_aide"
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

    @app_commands.command(name="definir_journal_burnout", description="Définit le salon réservé aux signalements de burnout.")
    async def definir_journal_burnout(self, interaction: discord.Interaction, salon: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            config = charger_config()
            config["journal_burnout_channel"] = str(salon.id)
            sauvegarder_config(config)
            await interaction.response.send_message(f"✅ Le salon pour les signalements de burnout a été défini : {salon.mention}", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"definir_journal_burnout: {e}")
            await interaction.response.send_message("❌ Erreur lors de la configuration du salon de burnout.", ephemeral=True)

    # ───────────── Nouvelles Fonctions Admin ─────────────

    # 1. Commande pour créer une catégorie privée accessible uniquement à un certain rôle
    @app_commands.command(name="creer_categorie_privee", description="Crée une catégorie privée visible uniquement pour un rôle spécifique.")
    async def creer_categorie_privee(self, interaction: discord.Interaction, nom_de_categorie: str, role: discord.Role):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                role: discord.PermissionOverwrite(read_messages=True)
            }
            category = await interaction.guild.create_category(nom_de_categorie, overwrites=overwrites)
            await interaction.response.send_message(f"✅ Catégorie privée `{category.name}` créée pour le rôle {role.mention}.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_categorie_privee: {e}")
            await interaction.response.send_message("❌ Erreur lors de la création de la catégorie privée.", ephemeral=True)

    # 2. Commande pour créer un message Reaction Role via modal (jusqu'à 3 associations possibles)
    class ReactionRoleModal(discord.ui.Modal, title="Création d'un Reaction Role"):
        message = discord.ui.TextInput(
            label="Message à poster",
            style=discord.TextStyle.paragraph,
            placeholder="Tapez ici le contenu du message pour le reaction role.",
            required=True
        )
        pair1 = discord.ui.TextInput(
            label="Association 1 (emoji, role)",
            style=discord.TextStyle.short,
            placeholder="Ex: 😀, @EtudiantMath",
            required=False
        )
        pair2 = discord.ui.TextInput(
            label="Association 2 (emoji, role)",
            style=discord.TextStyle.short,
            placeholder="Ex: 😎, @EtudiantPhysique",
            required=False
        )
        pair3 = discord.ui.TextInput(
            label="Association 3 (emoji, role)",
            style=discord.TextStyle.short,
            placeholder="Ex: 🎯, @EtudiantChimie",
            required=False
        )

        async def on_submit(self, modal_interaction: discord.Interaction):
            try:
                # Récupération du canal à partir de l'attribut custom 'channel_object'
                channel = modal_interaction.data.get("channel_object")
                if not channel:
                    await modal_interaction.response.send_message("❌ Canal non spécifié.", ephemeral=True)
                    return

                pairs = []
                for field in [self.pair1.value, self.pair2.value, self.pair3.value]:
                    if field and "," in field:
                        parts = field.split(",", 1)
                        emoji = parts[0].strip()
                        role_str = parts[1].strip()
                        if role_str.startswith("<@&") and role_str.endswith(">"):
                            role_id = int(role_str.strip("<@&>"))
                            pairs.append((emoji, role_id))
                msg = await channel.send(self.message.value)
                for emoji, role_id in pairs:
                    try:
                        await msg.add_reaction(emoji)
                    except Exception as e:
                        print(f"Erreur sur l'emoji {emoji} : {e}")
                mapping = load_reaction_role_mapping()
                mapping[str(msg.id)] = [{"emoji": emoji, "role_id": role_id} for emoji, role_id in pairs]
                save_reaction_role_mapping(mapping)
                await modal_interaction.response.send_message("✅ Reaction role créé avec succès.", ephemeral=True)
            except Exception as e:
                await log_erreur(self.bot, modal_interaction.guild, f"ReactionRoleModal on_submit: {e}")
                await modal_interaction.response.send_message("❌ Erreur lors de la création du Reaction Role.", ephemeral=True)

    @app_commands.command(name="creer_reaction_role", description="Crée un message Reaction Role via modal.")
    async def creer_reaction_role(self, interaction: discord.Interaction, canal: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            modal = self.ReactionRoleModal()
            modal.__dict__["channel_object"] = canal
            await interaction.response.send_modal(modal)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_reaction_role: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'ouverture du formulaire Reaction Role.", ephemeral=True)

    # 3. Commande pour supprimer les N derniers messages d'un canal
    @app_commands.command(name="clear_messages", description="Supprime les N derniers messages du canal.")
    async def clear_messages(self, interaction: discord.Interaction, nombre: int):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            if nombre < 1 or nombre > 100:
                return await interaction.response.send_message("❌ Le nombre doit être compris entre 1 et 100.", ephemeral=True)
            deleted = await interaction.channel.purge(limit=nombre)
            await interaction.response.send_message(f"✅ {len(deleted)} messages supprimés.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"clear_messages: {e}")
            await interaction.response.send_message("❌ Erreur lors de la suppression des messages.", ephemeral=True)

    # 4. Commande pour définir le canal d'annonces
    @app_commands.command(name="definir_annonce", description="Définit le canal réservé aux annonces importantes.")
    async def definir_annonce(self, interaction: discord.Interaction, salon: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            config = charger_config()
            config["annonce_channel"] = str(salon.id)
            sauvegarder_config(config)
            await interaction.response.send_message(f"✅ Le canal d'annonces a été défini : {salon.mention}", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"definir_annonce: {e}")
            await interaction.response.send_message("❌ Erreur lors de la configuration du canal d'annonces.", ephemeral=True)


async def setup_admin_commands(bot):
    await bot.add_cog(AdminCommands(bot))
