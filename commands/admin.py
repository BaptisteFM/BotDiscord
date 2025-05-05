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
    log_erreur,
    charger_permissions,
    sauvegarder_permissions
)
import json
import os
import asyncio
from datetime import datetime


RESOURCES_PATH = "/data/ressources.json"

def load_resources() -> list[dict]:
    if not os.path.exists(RESOURCES_PATH):
        return []
    with open(RESOURCES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_resources(resources: list[dict]) -> None:
    os.makedirs(os.path.dirname(RESOURCES_PATH), exist_ok=True)
    with open(RESOURCES_PATH, "w", encoding="utf-8") as f:
        json.dump(resources, f, indent=4, ensure_ascii=False)



class AdminCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reaction_role_messages = load_reaction_role_mapping()

    @app_commands.command(name="definir_salon", description="Définir le salon autorisé pour une commande.")
    @app_commands.default_permissions(administrator=True)
    async def definir_salon(self, interaction: discord.Interaction, nom_commande: str, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        definir_salon_autorise(nom_commande, salon.id)
        await interaction.response.send_message(f"✅ Salon défini pour `{nom_commande}` : {salon.mention}", ephemeral=True)

    @definir_salon.autocomplete("nom_commande")
    async def autocomplete_command_names(self, interaction: discord.Interaction, current: str):
        try:
            all_commands = [cmd.name for cmd in self.bot.tree.get_commands()]
            suggestions = [app_commands.Choice(name=cmd, value=cmd) for cmd in all_commands if current.lower() in cmd.lower()]
            return suggestions[:25]
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"autocomplete_command_names\n{e}")
            return []

    @app_commands.command(name="definir_redirection", description="Rediriger un type de message vers un salon.")
    @app_commands.default_permissions(administrator=True)
    async def definir_redirection(self, interaction: discord.Interaction, redirection_type: str, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        definir_redirection(redirection_type, salon.id)
        await interaction.response.send_message(f"✅ Redirection `{redirection_type}` → {salon.mention}", ephemeral=True)


    @app_commands.command(name="definir_config", description="Définir une option de configuration générique.")
    @app_commands.default_permissions(administrator=True)
    async def definir_config(self, interaction: discord.Interaction, option: str, valeur: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        definir_option_config(option, valeur)
        await interaction.response.send_message(f"✅ Option `{option}` définie à `{valeur}`", ephemeral=True)


    @app_commands.command(name="definir_log_erreurs", description="Définit le salon de logs d’erreurs techniques.")
    @app_commands.default_permissions(administrator=True)
    async def definir_log_erreurs(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["log_erreurs_channel"] = str(salon.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Salon de logs défini : {salon.mention}", ephemeral=True)


    @app_commands.command(name="creer_role", description="Crée un rôle s’il n’existe pas déjà.")
    @app_commands.default_permissions(administrator=True)
    async def creer_role(self, interaction: discord.Interaction, nom_du_role: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        try:
            role = await get_or_create_role(interaction.guild, nom_du_role)
            await interaction.response.send_message(f"✅ Rôle prêt : `{role.name}`", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_role\n{e}")
            await interaction.response.send_message("❌ Erreur lors de la création du rôle.", ephemeral=True)


    @app_commands.command(name="creer_categorie", description="Crée une catégorie si elle n’existe pas déjà.")
    @app_commands.default_permissions(administrator=True)
    async def creer_categorie(self, interaction: discord.Interaction, nom_de_categorie: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        try:
            category = await get_or_create_category(interaction.guild, nom_de_categorie)
            await interaction.response.send_message(f"✅ Catégorie créée : `{category.name}`", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_categorie\n{e}")
            await interaction.response.send_message("❌ Erreur lors de la création de la catégorie.", ephemeral=True)


    @app_commands.command(
        name="creer_categorie_privee",
        description="Crée une catégorie privée pour un rôle donné, avec emoji en option."
    )
    @app_commands.describe(
        nom_de_categorie="Nom de la catégorie à créer (vous pouvez inclure un emoji)",
        role="Rôle qui aura accès à cette catégorie"
    )
    @app_commands.default_permissions(administrator=True)
    async def creer_categorie_privee(self, interaction: discord.Interaction, nom_de_categorie: str, role: discord.Role):
        try:
            if not await is_admin(interaction.user):
                return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                role: discord.PermissionOverwrite(read_messages=True)
            }
            category = await interaction.guild.create_category(name=nom_de_categorie, overwrites=overwrites)
            await interaction.response.send_message(
                f"✅ Catégorie privée **{category.name}** créée avec accès pour {role.mention}.",
                ephemeral=True
            )
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_categorie_privee: {e}")
            await interaction.response.send_message(
                "❌ Erreur lors de la création de la catégorie privée.",
                ephemeral=True
            )


    @app_commands.command(name="creer_salon", description="Crée un salon texte ou vocal dans une catégorie existante.")
    @app_commands.describe(nom_salon="Nom du nouveau salon", type_salon="Type de salon : texte ou vocal", categorie="Sélectionne la catégorie existante")
    @app_commands.default_permissions(administrator=True)
    async def creer_salon(self, interaction: discord.Interaction, nom_salon: str, type_salon: str, categorie: discord.CategoryChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        try:
            if type_salon.lower() == "texte":
                await interaction.guild.create_text_channel(nom_salon, category=categorie)
            elif type_salon.lower() == "vocal":
                await interaction.guild.create_voice_channel(nom_salon, category=categorie)
            else:
                return await interaction.response.send_message("❌ Type de salon invalide. Choisis 'texte' ou 'vocal'.", ephemeral=True)
            await interaction.response.send_message(f"✅ Salon `{nom_salon}` créé dans la catégorie `{categorie.name}`.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"creer_salon: {e}")
            await interaction.response.send_message("❌ Erreur lors de la création du salon.", ephemeral=True)


    @app_commands.command(name="definir_role_aide", description="Définit le rôle ping pour aider les étudiants.")
    @app_commands.default_permissions(administrator=True)
    async def definir_role_aide(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être administrateur.", ephemeral=True)
        definir_option_config("role_aide", str(role.id))
        await interaction.response.send_message(f"✅ Rôle d’aide défini : {role.mention}", ephemeral=True)
  

    @app_commands.command(name="envoyer_message", description="Envoie un message formaté dans un salon via modal.")
    @app_commands.default_permissions(administrator=True)
    async def envoyer_message(self, interaction: discord.Interaction, channel: discord.TextChannel):
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


    @app_commands.command(name="definir_journal_burnout", description="Définit le salon réservé aux signalements de burnout.")
    @app_commands.default_permissions(administrator=True)
    async def definir_journal_burnout(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["journal_burnout_channel"] = str(salon.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Le salon pour les signalements de burnout a été défini : {salon.mention}", ephemeral=True)


    @app_commands.command(name="definir_role_utilisateur", description="Définit le rôle qui permet d'accéder aux commandes utilisateurs et support.")
    @app_commands.default_permissions(administrator=True)
    async def definir_role_utilisateur(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["role_acces_utilisateur"] = str(role.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Rôle d'accès utilisateur défini : {role.mention}", ephemeral=True)


    @app_commands.command(name="definir_permission", description="Définit la permission d'accès pour une commande admin.")
    @app_commands.default_permissions(administrator=True)
    async def definir_permission(self, interaction: discord.Interaction, commande: str, role: discord.Role):
        permissions = charger_permissions()
        current = permissions.get(commande, [])
        if str(role.id) not in current:
            current.append(str(role.id))
        permissions[commande] = current
        sauvegarder_permissions(permissions)
        await interaction.response.send_message(f"✅ Permission définie pour la commande `{commande}` avec le rôle {role.mention}.", ephemeral=True)


    @definir_permission.autocomplete("commande")
    async def autocomplete_command_permission(self, interaction: discord.Interaction, current: str):
        commands_list = [
            "definir_salon", "definir_redirection", "definir_config", "definir_log_erreurs",
            "creer_role", "creer_categorie", "creer_salon", "definir_role_aide",
            "envoyer_message", "definir_journal_burnout", "definir_permission",
            "lister_commandes_admin", "creer_reaction_role", "clear_messages", "definir_annonce",
            "creer_promo", "assigner_eleve", "signaler_inactif", "creer_binome", "statistiques_serveur",
            "generer_rapport_hebdo", "lock_salon", "purger_role",
            "activer_mode_examen", "desactiver_mode_examen", "maintenance_on", "maintenance_off",
            "forcer_validation"
        ]
        suggestions = [app_commands.Choice(name=cmd, value=cmd) for cmd in commands_list if current.lower() in cmd.lower()]
        return suggestions[:25]

    @app_commands.command(name="lister_commandes_admin", description="Liste les commandes admin et leurs permissions actuelles.")
    @app_commands.default_permissions(administrator=True)
    async def lister_commandes_admin(self, interaction: discord.Interaction):
        permissions = charger_permissions()
        embed = discord.Embed(title="Commandes Admin", color=discord.Color.blue())
        if not permissions:
            embed.description = "Aucune permission définie."
        else:
            for cmd, roles in permissions.items():
                role_mentions = []
                for role_id in roles:
                    role = interaction.guild.get_role(int(role_id))
                    if role:
                        role_mentions.append(role.mention)
                embed.add_field(name=cmd, value=", ".join(role_mentions) if role_mentions else "Aucun rôle", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
  

    @app_commands.command(name="creer_reaction_role", description="Crée ou ajoute un reaction role (simple et fiable)")
    @app_commands.default_permissions(administrator=True)
    async def creer_reaction_role(
        self, interaction: discord.Interaction,
        canal: discord.TextChannel,
        emoji: str,
        role: discord.Role,
        message_id: str = None
    ):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)

        if message_id:
            # Ajout à un message existant
            try:
                msg = await canal.fetch_message(int(message_id))
                await msg.add_reaction(emoji)

                mapping = load_reaction_role_mapping()
                mapping.setdefault(str(msg.id), []).append({"emoji": emoji, "role_id": role.id})
                save_reaction_role_mapping(mapping)

                return await interaction.response.send_message("✅ Reaction role ajouté au message existant !", ephemeral=True)
            except Exception as e:
                await log_erreur(self.bot, interaction.guild, f"Ajout RR à message existant : {e}")
                return await interaction.response.send_message("❌ Erreur lors de l'ajout du reaction role.", ephemeral=True)

        # Sinon, création via modal
        class ReactionRoleModal(discord.ui.Modal, title="Message du Reaction Role"):
            contenu = discord.ui.TextInput(
                label="Contenu du message à poster",
                style=discord.TextStyle.paragraph,
                placeholder="Tape ici ton message reaction role",
                required=True
            )

            async def on_submit(self_inner, modal_interaction: discord.Interaction):
                try:
                    msg = await canal.send(self_inner.contenu.value)
                    await msg.add_reaction(emoji)

                    mapping = load_reaction_role_mapping()
                    mapping[str(msg.id)] = [{"emoji": emoji, "role_id": role.id}]
                    save_reaction_role_mapping(mapping)

                    await modal_interaction.response.send_message("✅ Reaction role créé avec succès !", ephemeral=True)
                except Exception as e:
                    await log_erreur(self.bot, interaction.guild, f"Modal RR creation : {e}")
                    await modal_interaction.response.send_message("❌ Erreur lors de la création du reaction role.", ephemeral=True)

        await interaction.response.send_modal(ReactionRoleModal())



    @app_commands.command(name="clear_messages", description="Supprime les N derniers messages du canal.")
    @app_commands.default_permissions(administrator=True)
    async def clear_messages(self, interaction: discord.Interaction, nombre: int):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        if nombre < 1 or nombre > 100:
            return await interaction.response.send_message("❌ Le nombre doit être compris entre 1 et 100.", ephemeral=True)
        deleted = await interaction.channel.purge(limit=nombre)
        await interaction.response.send_message(f"✅ {len(deleted)} messages supprimés.", ephemeral=True)


    @app_commands.command(name="definir_annonce", description="Définit le canal réservé aux annonces importantes.")
    @app_commands.default_permissions(administrator=True)
    async def definir_annonce(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["annonce_channel"] = str(salon.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Le canal d'annonces a été défini : {salon.mention}", ephemeral=True)


    @app_commands.command(name="creer_promo", description="Crée une promo en générant un rôle et une catégorie privée dédiée.")
    @app_commands.default_permissions(administrator=True)
    async def creer_promo(self, interaction: discord.Interaction, nom_promo: str):
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


    @app_commands.command(name="assigner_eleve", description="Assigne un élève à une promo en lui attribuant le rôle correspondant.")
    @app_commands.default_permissions(administrator=True)
    async def assigner_eleve(self, interaction: discord.Interaction, utilisateur: discord.Member, nom_promo: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        promo_role_name = f"Promo {nom_promo}"
        promo_role = discord.utils.get(interaction.guild.roles, name=promo_role_name)
        if not promo_role:
            return await interaction.response.send_message("❌ Le rôle de promo n'existe pas. Créez la promo d'abord.", ephemeral=True)
        if promo_role not in utilisateur.roles:
            await utilisateur.add_roles(promo_role)
        await interaction.response.send_message(f"✅ {utilisateur.mention} a été ajouté(e) à la promo {nom_promo}.", ephemeral=True)


    @app_commands.command(name="signaler_inactif", description="Signale un élève inactif en lui attribuant le rôle 'Inactif'.")
    @app_commands.default_permissions(administrator=True)
    async def signaler_inactif(self, interaction: discord.Interaction, utilisateur: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        role_inactif = discord.utils.get(interaction.guild.roles, name="Inactif")
        if not role_inactif:
            role_inactif = await get_or_create_role(interaction.guild, "Inactif")
        if role_inactif not in utilisateur.roles:
            await utilisateur.add_roles(role_inactif)
        await interaction.response.send_message(f"✅ {utilisateur.mention} a été signalé(e) comme inactif(ve).", ephemeral=True)


    @app_commands.command(name="creer_binome", description="Crée une catégorie privée partagée pour deux élèves.")
    @app_commands.default_permissions(administrator=True)
    async def creer_binome(self, interaction: discord.Interaction, utilisateur1: discord.Member, utilisateur2: discord.Member):
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


    @app_commands.command(name="statistiques_serveur", description="Affiche quelques statistiques du serveur.")
    @app_commands.default_permissions(administrator=True)
    async def statistiques_serveur(self, interaction: discord.Interaction):
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


    @app_commands.command(name="generer_rapport_hebdo", description="Génère un rapport hebdomadaire sur le serveur.")
    @app_commands.default_permissions(administrator=True)
    async def generer_rapport_hebdo(self, interaction: discord.Interaction):
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


    @app_commands.command(name="lock_salon", description="Verrouille un salon pour un temps donné (en minutes).")
    @app_commands.default_permissions(administrator=True)
    async def lock_salon(self, interaction: discord.Interaction, salon: discord.TextChannel, duree: int):
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


    @app_commands.command(name="purger_role", description="Retire un rôle de tous les membres du serveur.")
    @app_commands.default_permissions(administrator=True)
    async def purger_role(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        compteur = 0
        for member in role.members:
            await member.remove_roles(role)
            compteur += 1
        await interaction.response.send_message(f"✅ Le rôle {role.mention} a été retiré de {compteur} membres.", ephemeral=True)


    @app_commands.command(name="activer_mode_examen", description="Active le mode examen en cachant certains salons.")
    @app_commands.default_permissions(administrator=True)
    async def activer_mode_examen(self, interaction: discord.Interaction, salons: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        salons_a_garder = [s.strip() for s in salons.split(",")]
        for channel in interaction.guild.text_channels:
            if str(channel.id) not in salons_a_garder and channel.name not in salons_a_garder:
                await channel.set_permissions(interaction.guild.default_role, read_messages=False)
        await interaction.response.send_message("✅ Mode examen activé.", ephemeral=True)
   

    @app_commands.command(name="desactiver_mode_examen", description="Désactive le mode examen et rétablit l'accès aux salons.")
    @app_commands.default_permissions(administrator=True)
    async def desactiver_mode_examen(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        for channel in interaction.guild.text_channels:
            await channel.set_permissions(interaction.guild.default_role, read_messages=True)
        await interaction.response.send_message("✅ Mode examen désactivé.", ephemeral=True)


    @app_commands.command(name="maintenance_on", description="Active le mode maintenance sur le serveur.")
    @app_commands.default_permissions(administrator=True)
    async def maintenance_on(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["maintenance"] = True
        sauvegarder_config(config)
        await interaction.response.send_message("✅ Mode maintenance activé. Seuls les admins pourront utiliser le bot.", ephemeral=True)
 

    @app_commands.command(name="maintenance_off", description="Désactive le mode maintenance sur le serveur.")
    @app_commands.default_permissions(administrator=True)
    async def maintenance_off(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["maintenance"] = False
        sauvegarder_config(config)
        await interaction.response.send_message("✅ Mode maintenance désactivé.", ephemeral=True)


    @app_commands.command(name="forcer_validation", description="Envoie un message de validation des règles à un utilisateur.")
    @app_commands.default_permissions(administrator=True)
    async def forcer_validation(self, interaction: discord.Interaction, utilisateur: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        embed = discord.Embed(
            title="Validation du règlement",
            description="Veuillez lire et accepter les règles du serveur pour accéder à l'intégralité du serveur.",
            color=discord.Color.blurple()
        )
        view = self.ValidationView(utilisateur)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


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


    # ───── Définir le salon de redirection pour la commande /proposer_sortie ─────
    @app_commands.command(name="definir_salon_sortie", description="Définit le salon où sont envoyées les propositions de sorties.")
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_sortie(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["sortie_channel"] = str(salon.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Salon des sorties défini : {salon.mention}", ephemeral=True)


    # ───── Définir le rôle à ping pour la commande /proposer_sortie ─────
    @app_commands.command(name="definir_role_sortie", description="Définit le rôle qui sera ping pour les propositions de sorties.")
    @app_commands.default_permissions(administrator=True)
    async def definir_role_sortie(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["role_sortie"] = str(role.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Rôle pour les sorties défini : {role.mention}", ephemeral=True)
    
    # ───── Définir le rôle staff sortie qui peut fermer les sorties ─────
    @app_commands.command(name="definir_role_staff_sortie", description="Définit le rôle staff qui peut fermer les sorties.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(role="Rôle staff qui peut fermer les sorties, et qui sera staff des sorties.")
    async def definir_role_staff_sortie(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["role_staff_sortie"] = str(role.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Rôle staff pour les sorties défini : {role.mention}", ephemeral=True)
    
    # ───── Voir ressources ───────────────────────────────────────────────
    @app_commands.command(
        name="voir_ressources",
        description="(Admin) Affiche la liste des ressources configurées."
    )
    @app_commands.default_permissions(administrator=True)
    async def voir_ressources(self, interaction: discord.Interaction):
        ressources = load_resources()
        if not ressources:
            return await interaction.response.send_message(
                "ℹ️ Aucune ressource enregistrée.", ephemeral=True
            )

        texte = "\n".join(f"{i}. {e['name']} — {e['url']}" for i, e in enumerate(ressources))
        embed = discord.Embed(
            title="🔧 Ressources (admin)",
            description=texte,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ───── Ajoute une ressource ────────────────────────────────
    @app_commands.command(
        name="ajouter_ressource",
        description="(Admin) Ajoute une ressource pour la commande /ressources."
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        name="Titre de la ressource",
        url="URL ou lien markdown pour la ressource"
    )
    async def ajouter_ressource(
        self,
        interaction: discord.Interaction,
        name: str,
        url: str
    ):
        ressources = load_resources()
        ressources.append({"name": name, "url": url})
        save_resources(ressources)
        await interaction.response.send_message(
            f"✅ Ressource ajoutée : **{name}**", ephemeral=True
        )

    # ───── Supprimer une ressource ────────────────────────────────────
    @app_commands.command(
        name="supprimer_ressource",
        description="(Admin) Supprime la ressource d’index donné (0-based)."
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        index="Index de la ressource tel que listé par /voir_ressources"
    )
    async def supprimer_ressource(
        self,
        interaction: discord.Interaction,
        index: int
    ):
        ressources = load_resources()
        if index < 0 or index >= len(ressources):
            return await interaction.response.send_message(
                "❌ Index invalide.", ephemeral=True
            )
        removed = ressources.pop(index)
        save_resources(ressources)
        await interaction.response.send_message(
            f"✅ Ressource supprimée : **{removed['name']}**", ephemeral=True
        )




async def setup_admin_commands(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))
