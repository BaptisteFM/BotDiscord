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
import json
import os
import asyncio
from datetime import datetime, timedelta

class AdminCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reaction_role_messages = load_reaction_role_mapping()

    # ───────────── Commande : Définir salon autorisé ─────────────
    @app_commands.command(name="definir_salon", description="Définir le salon autorisé pour une commande.")
    async def definir_salon(self, interaction: discord.Interaction, nom_commande: str, salon: discord.TextChannel):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
            # Utilisez les noms de commande actuels, ex : "cours_aide" et non "besoin_d_aide"
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

    # ───────────── Commande : Rediriger un type de message ─────────────
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

    # ───────────── Commande : Définir une option de configuration ─────────────
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

    # ───────────── Commande : Définir le salon de logs d'erreurs ─────────────
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

    # ───────────── Commande : Créer un rôle ─────────────
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

    # ───────────── Commande : Créer une catégorie ─────────────
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


    # ───────────── Commande : Créer un salon ─────────────
    @app_commands.command(name="creer_salon", description="Crée un salon texte ou vocal dans une catégorie existante.")
    @app_commands.describe(nom_salon="Nom du nouveau salon", type_salon="Type de salon : texte ou vocal", categorie="Catégorie existante (copie-colle le nom)")
    async def creer_salon(self, interaction: discord.Interaction, nom_salon: str, type_salon: str, categorie: str):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)

            # Cherche une catégorie existante
            category = discord.utils.get(interaction.guild.categories, name=categorie)
            if not category:
                return await interaction.response.send_message("❌ Cette catégorie n'existe pas. Vérifie l'orthographe exacte.", ephemeral=True)

            # Crée le salon
            if type_salon.lower() == "texte":
                await interaction.guild.create_text_channel(nom_salon, category=category)
            elif type_salon.lower() == "vocal":
                await interaction.guild.create_voice_channel(nom_salon, category=category)
            else:
                return await interaction.response.send_message("❌ Type de salon invalide. Choisis 'texte' ou 'vocal'.", ephemeral=True)

            await interaction.response.send_message(f"✅ Salon `{nom_salon}` créé dans la catégorie `{categorie}`.", ephemeral=True)

        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_salon: {e}")
            await interaction.response.send_message("❌ Erreur lors de la création du salon.", ephemeral=True)


    # ───────────── Commande : Définir le rôle d’aide ─────────────
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

    # ───────────── Commande : Envoyer un message formaté via modal ─────────────
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

    # ───────────── Commande : Définir le salon pour le journal burnout ─────────────
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

    # ───────────── Nouvelles Fonctions Administratives ─────────────

    # ───────────── Commande : Créer une catégorie privée ─────────────
    @app_commands.command(name="creer_categorie_privee", description="Crée une catégorie privée pour un rôle donné, avec emoji en option.")
    @app_commands.describe(nom_de_categorie="Nom de la catégorie à créer (tu peux inclure un emoji)", role="Rôle qui aura accès")
    async def creer_categorie_privee(self, interaction: discord.Interaction, nom_de_categorie: str, role: discord.Role):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)

            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                role: discord.PermissionOverwrite(read_messages=True)
            }

            category = await interaction.guild.create_category(name=nom_de_categorie, overwrites=overwrites)
            await interaction.response.send_message(f"✅ Catégorie privée `{category.name}` créée avec accès pour {role.mention}.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_categorie_privee: {e}")
            await interaction.response.send_message("❌ Erreur lors de la création de la catégorie privée.", ephemeral=True)


    # 2. Créer un message Reaction Role via modal (jusqu'à 3 associations)
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
                # Récupération du canal fourni via un attribut custom "channel_object"
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
            # Utilisez l'attribut custom pour transmettre l'objet canal
            modal.__dict__["channel_object"] = canal
            await interaction.response.send_modal(modal)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_reaction_role: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'ouverture du formulaire Reaction Role.", ephemeral=True)

    # 3. Supprimer les N derniers messages d'un canal
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

    # 4. Définir le canal d'annonces
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

    # 5. Système de whitelist : ajouter un utilisateur
    @app_commands.command(name="ajouter_whitelist", description="Ajoute un utilisateur à la whitelist d'accès au serveur.")
    async def ajouter_whitelist(self, interaction: discord.Interaction, utilisateur: discord.Member):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            whitelist = self.charger_whitelist()
            if utilisateur.id not in whitelist:
                whitelist.append(utilisateur.id)
                self.sauvegarder_whitelist(whitelist)
                await interaction.response.send_message(f"✅ {utilisateur.mention} a été ajouté à la whitelist.", ephemeral=True)
            else:
                await interaction.response.send_message("ℹ️ Cet utilisateur est déjà dans la whitelist.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ajouter_whitelist: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'ajout à la whitelist.", ephemeral=True)

    # 6. Système de whitelist : retirer un utilisateur
    @app_commands.command(name="retirer_whitelist", description="Retire un utilisateur de la whitelist d'accès au serveur.")
    async def retirer_whitelist(self, interaction: discord.Interaction, utilisateur: discord.Member):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            whitelist = self.charger_whitelist()
            if utilisateur.id in whitelist:
                whitelist.remove(utilisateur.id)
                self.sauvegarder_whitelist(whitelist)
                await interaction.response.send_message(f"✅ {utilisateur.mention} a été retiré de la whitelist.", ephemeral=True)
            else:
                await interaction.response.send_message("ℹ️ Cet utilisateur n'est pas dans la whitelist.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"retirer_whitelist: {e}")
            await interaction.response.send_message("❌ Erreur lors de la suppression de la whitelist.", ephemeral=True)

    # 7. Commande : Valider un nouvel utilisateur (retire "Non vérifié" et ajoute "Membre")
    @app_commands.command(name="valider_utilisateur", description="Valide un nouvel utilisateur en modifiant ses rôles.")
    async def valider_utilisateur(self, interaction: discord.Interaction, utilisateur: discord.Member):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            role_non_verifie = discord.utils.get(interaction.guild.roles, name="Non vérifié")
            role_membre = discord.utils.get(interaction.guild.roles, name="Membre")
            if role_non_verifie and role_non_verifie in utilisateur.roles:
                await utilisateur.remove_roles(role_non_verifie)
            if role_membre and role_membre not in utilisateur.roles:
                await utilisateur.add_roles(role_membre)
            await interaction.response.send_message(f"✅ {utilisateur.mention} a été validé(e).", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"valider_utilisateur: {e}")
            await interaction.response.send_message("❌ Erreur lors de la validation de l'utilisateur.", ephemeral=True)

    # 8. Commande : Créer une promo (crée un rôle et une catégorie privée avec plusieurs salons)
    @app_commands.command(name="creer_promo", description="Crée une promo en générant un rôle et une catégorie privée dédiée.")
    async def creer_promo(self, interaction: discord.Interaction, nom_promo: str):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            promo_role_name = f"Promo {nom_promo}"
            promo_role = await get_or_create_role(interaction.guild, promo_role_name)
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                promo_role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            category_name = f"Promo {nom_promo}"
            category = await interaction.guild.create_category(category_name, overwrites=overwrites)
            await interaction.guild.create_text_channel("annonces", category=category)
            await interaction.guild.create_text_channel("discussion", category=category)
            await interaction.guild.create_text_channel("ressources", category=category)
            await interaction.response.send_message(f"✅ Promo '{nom_promo}' créée avec rôle et catégorie privée.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_promo: {e}")
            await interaction.response.send_message("❌ Erreur lors de la création de la promo.", ephemeral=True)

    # 9. Commande : Assigner un élève à une promo
    @app_commands.command(name="assigner_eleve", description="Assigne un élève à une promo en lui attribuant le rôle correspondant.")
    async def assigner_eleve(self, interaction: discord.Interaction, utilisateur: discord.Member, nom_promo: str):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            promo_role_name = f"Promo {nom_promo}"
            promo_role = discord.utils.get(interaction.guild.roles, name=promo_role_name)
            if not promo_role:
                return await interaction.response.send_message("❌ Le rôle de promo n'existe pas. Créez la promo d'abord.", ephemeral=True)
            if promo_role not in utilisateur.roles:
                await utilisateur.add_roles(promo_role)
            await interaction.response.send_message(f"✅ {utilisateur.mention} a été ajouté(e) à la promo {nom_promo}.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"assigner_eleve: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'assignation de l'élève.", ephemeral=True)

    # 10. Commande : Signaler un élève inactif (ajoute le rôle "Inactif")
    @app_commands.command(name="signaler_inactif", description="Signale un élève inactif en lui attribuant le rôle 'Inactif'.")
    async def signaler_inactif(self, interaction: discord.Interaction, utilisateur: discord.Member):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            role_inactif = discord.utils.get(interaction.guild.roles, name="Inactif")
            if not role_inactif:
                role_inactif = await get_or_create_role(interaction.guild, "Inactif")
            if role_inactif not in utilisateur.roles:
                await utilisateur.add_roles(role_inactif)
            await interaction.response.send_message(f"✅ {utilisateur.mention} a été signalé(e) comme inactif(ve).", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"signaler_inactif: {e}")
            await interaction.response.send_message("❌ Erreur lors du signalement d'inactivité.", ephemeral=True)

    # 11. Commande : Créer un binôme ou tutorat privé pour deux élèves
    @app_commands.command(name="creer_binome", description="Crée une catégorie privée partagée pour deux élèves.")
    async def creer_binome(self, interaction: discord.Interaction, utilisateur1: discord.Member, utilisateur2: discord.Member):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                utilisateur1: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                utilisateur2: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            category_name = f"Binome-{utilisateur1.display_name}-{utilisateur2.display_name}"
            category = await interaction.guild.create_category(category_name, overwrites=overwrites)
            await interaction.guild.create_text_channel("discussion", category=category)
            await interaction.guild.create_voice_channel("voix", category=category)
            await interaction.response.send_message(f"✅ Catégorie créée pour {utilisateur1.mention} et {utilisateur2.mention}.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_binome: {e}")
            await interaction.response.send_message("❌ Erreur lors de la création du binôme.", ephemeral=True)

    # 12. Commande : Afficher des statistiques rapides du serveur
    @app_commands.command(name="statistiques_serveur", description="Affiche quelques statistiques du serveur.")
    async def statistiques_serveur(self, interaction: discord.Interaction):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            guild = interaction.guild
            total_members = guild.member_count
            total_channels = len(guild.channels)
            total_roles = len(guild.roles)
            embed = discord.Embed(title="Statistiques du serveur", color=discord.Color.gold())
            embed.add_field(name="Membres totaux", value=str(total_members), inline=True)
            embed.add_field(name="Salons", value=str(total_channels), inline=True)
            embed.add_field(name="Rôles", value=str(total_roles), inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"statistiques_serveur: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'affichage des statistiques.", ephemeral=True)

    # 13. Commande : Générer un rapport hebdomadaire (rapport actuel)
    @app_commands.command(name="generer_rapport_hebdo", description="Génère un rapport hebdomadaire sur le serveur.")
    async def generer_rapport_hebdo(self, interaction: discord.Interaction):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            guild = interaction.guild
            date_now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            embed = discord.Embed(
                title="Rapport Hebdomadaire",
                description=f"Rapport généré le {date_now}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Membres totaux", value=str(guild.member_count), inline=True)
            embed.add_field(name="Nombre de salons", value=str(len(guild.channels)), inline=True)
            embed.add_field(name="Nombre de rôles", value=str(len(guild.roles)), inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"generer_rapport_hebdo: {e}")
            await interaction.response.send_message("❌ Erreur lors de la génération du rapport.", ephemeral=True)

    # 14. Commande : Verrouiller temporairement un salon pour un certain temps (en minutes)
    @app_commands.command(name="lock_salon", description="Verrouille un salon pour un temps donné (en minutes).")
    async def lock_salon(self, interaction: discord.Interaction, salon: discord.TextChannel, duree: int):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            overwrite = salon.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            await salon.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await interaction.response.send_message(f"🔒 Salon {salon.mention} verrouillé pour {duree} minutes.", ephemeral=True)
            await asyncio.sleep(duree * 60)
            overwrite.send_messages = None
            await salon.set_permissions(interaction.guild.default_role, overwrite=overwrite)
            await interaction.followup.send(f"🔓 Salon {salon.mention} déverrouillé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"lock_salon: {e}")
            await interaction.response.send_message("❌ Erreur lors du verrouillage du salon.", ephemeral=True)

    # 15. Commande : Purger (retirer) un rôle de tous les membres du serveur
    @app_commands.command(name="purger_role", description="Retire un rôle de tous les membres du serveur.")
    async def purger_role(self, interaction: discord.Interaction, role: discord.Role):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            compteur = 0
            for member in role.members:
                await member.remove_roles(role)
                compteur += 1
            await interaction.response.send_message(f"✅ Le rôle {role.mention} a été retiré de {compteur} membres.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"purger_role: {e}")
            await interaction.response.send_message("❌ Erreur lors de la purge du rôle.", ephemeral=True)

    # 16. Commande : Activer/Désactiver le mode examen
    @app_commands.command(name="activer_mode_examen", description="Active le mode examen en cachant certains salons.")
    async def activer_mode_examen(self, interaction: discord.Interaction, salons: str):
        """
        salons: une chaîne séparée par des virgules contenant les IDs ou noms des salons à laisser accessibles.
        Les autres seront cachés pour le rôle par défaut.
        """
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            salons_a_garder = [s.strip() for s in salons.split(",")]
            for channel in interaction.guild.text_channels:
                if str(channel.id) not in salons_a_garder and channel.name not in salons_a_garder:
                    await channel.set_permissions(interaction.guild.default_role, read_messages=False)
            await interaction.response.send_message("✅ Mode examen activé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"activer_mode_examen: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'activation du mode examen.", ephemeral=True)

    @app_commands.command(name="desactiver_mode_examen", description="Désactive le mode examen et rétablit l'accès aux salons.")
    async def desactiver_mode_examen(self, interaction: discord.Interaction):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            for channel in interaction.guild.text_channels:
                await channel.set_permissions(interaction.guild.default_role, read_messages=True)
            await interaction.response.send_message("✅ Mode examen désactivé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"desactiver_mode_examen: {e}")
            await interaction.response.send_message("❌ Erreur lors de la désactivation du mode examen.", ephemeral=True)

    # 17. Commande : Activer/Désactiver le mode maintenance
    @app_commands.command(name="maintenance_on", description="Active le mode maintenance sur le serveur.")
    async def maintenance_on(self, interaction: discord.Interaction):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            config = charger_config()
            config["maintenance"] = True
            sauvegarder_config(config)
            await interaction.response.send_message("✅ Mode maintenance activé. Seuls les admins pourront utiliser le bot.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"maintenance_on: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'activation du mode maintenance.", ephemeral=True)

    @app_commands.command(name="maintenance_off", description="Désactive le mode maintenance sur le serveur.")
    async def maintenance_off(self, interaction: discord.Interaction):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            config = charger_config()
            config["maintenance"] = False
            sauvegarder_config(config)
            await interaction.response.send_message("✅ Mode maintenance désactivé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"maintenance_off: {e}")
            await interaction.response.send_message("❌ Erreur lors de la désactivation du mode maintenance.", ephemeral=True)

    # 18. Commande : Forcer la validation d'un utilisateur (message avec bouton de validation)
    class ValidationModal(discord.ui.Modal, title="Validation des Règles"):
        def __init__(self, utilisateur: discord.Member):
            super().__init__()
            self.utilisateur = utilisateur

        async def on_submit(self, modal_interaction: discord.Interaction):
            pass  # Pas nécessaire ici

    class ValidationView(discord.ui.View):
        def __init__(self, utilisateur: discord.Member):
            super().__init__(timeout=None)
            self.utilisateur = utilisateur

        @discord.ui.button(label="J'accepte le règlement", style=discord.ButtonStyle.success)
        async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
            role_non_verifie = discord.utils.get(interaction.guild.roles, name="Non vérifié")
            role_membre = discord.utils.get(interaction.guild.roles, name="Membre")
            try:
                if role_non_verifie and role_non_verifie in self.utilisateur.roles:
                    await self.utilisateur.remove_roles(role_non_verifie)
                if role_membre and role_membre not in self.utilisateur.roles:
                    await self.utilisateur.add_roles(role_membre)
                await interaction.response.send_message("✅ Validation réussie. Bienvenue !", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message("❌ Erreur lors de la validation.", ephemeral=True)
                await log_erreur(interaction.client, interaction.guild, f"forcer_validation: {e}")

    @app_commands.command(name="forcer_validation", description="Envoie un message de validation des règles à un utilisateur.")
    async def forcer_validation(self, interaction: discord.Interaction, utilisateur: discord.Member):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            embed = discord.Embed(
                title="Validation du règlement",
                description="Veuillez lire et accepter les règles du serveur pour accéder à l'intégralité du serveur.",
                color=discord.Color.blurple()
            )
            view = self.ValidationView(utilisateur)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"forcer_validation: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'envoi du message de validation.", ephemeral=True)

    # ---- Utilitaires internes pour whitelist et autres données ----
    WHITELIST_PATH = "data/whitelist.json"

    def charger_whitelist(self):
        if not os.path.exists(self.WHITELIST_PATH):
            return []
        with open(self.WHITELIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def sauvegarder_whitelist(self, whitelist):
        os.makedirs("data", exist_ok=True)
        with open(self.WHITELIST_PATH, "w", encoding="utf-8") as f:
            json.dump(whitelist, f, indent=4)

    # 19. Commande : Activer le mode examen (masquer certains salons)
    @app_commands.command(name="activer_mode_examen", description="Active le mode examen en cachant certains salons.")
    async def activer_mode_examen(self, interaction: discord.Interaction, salons: str):
        """
        salons: une chaîne séparée par des virgules contenant les IDs ou noms des salons à laisser accessibles.
        """
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            salons_a_garder = [s.strip() for s in salons.split(",")]
            for channel in interaction.guild.text_channels:
                if str(channel.id) not in salons_a_garder and channel.name not in salons_a_garder:
                    await channel.set_permissions(interaction.guild.default_role, read_messages=False)
            await interaction.response.send_message("✅ Mode examen activé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"activer_mode_examen: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'activation du mode examen.", ephemeral=True)

    @app_commands.command(name="desactiver_mode_examen", description="Désactive le mode examen et rétablit l'accès aux salons.")
    async def desactiver_mode_examen(self, interaction: discord.Interaction):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            for channel in interaction.guild.text_channels:
                await channel.set_permissions(interaction.guild.default_role, read_messages=True)
            await interaction.response.send_message("✅ Mode examen désactivé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"desactiver_mode_examen: {e}")
            await interaction.response.send_message("❌ Erreur lors de la désactivation du mode examen.", ephemeral=True)

    # 20. Commande : Activer/Désactiver le mode maintenance
    @app_commands.command(name="maintenance_on", description="Active le mode maintenance sur le serveur.")
    async def maintenance_on(self, interaction: discord.Interaction):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            config = charger_config()
            config["maintenance"] = True
            sauvegarder_config(config)
            await interaction.response.send_message("✅ Mode maintenance activé. Seuls les admins pourront utiliser le bot.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"maintenance_on: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'activation du mode maintenance.", ephemeral=True)

    @app_commands.command(name="maintenance_off", description="Désactive le mode maintenance sur le serveur.")
    async def maintenance_off(self, interaction: discord.Interaction):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            config = charger_config()
            config["maintenance"] = False
            sauvegarder_config(config)
            await interaction.response.send_message("✅ Mode maintenance désactivé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"maintenance_off: {e}")
            await interaction.response.send_message("❌ Erreur lors de la désactivation du mode maintenance.", ephemeral=True)

async def setup_admin_commands(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))
