import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime
from utils.utils import (
    is_admin,
    charger_config,
    sauvegarder_config,
    log_erreur,
    is_non_verified_user,
    role_autorise
)

# Chemin du fichier stockant les demandes (en attente)
DEMANDES_PATH = "data/demandes_whitelist.json"


# Check : seuls les membres non validés peuvent demander l'accès
async def check_non_verified(interaction: discord.Interaction) -> bool:
    if await is_non_verified_user(interaction.user):
        return True
    raise app_commands.CheckFailure("Commande réservée aux membres non vérifiés.")


# Fonctions synchrones pour charger/sauvegarder les demandes
def _charger_demandes():
    if not os.path.exists(DEMANDES_PATH):
        return []
    try:
        with open(DEMANDES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _sauvegarder_demandes(data):
    os.makedirs("data", exist_ok=True)
    with open(DEMANDES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)


# === Modal pour saisir les informations personnelles lors de la demande d'accès ===
class DemandeAccesModal(discord.ui.Modal, title="Demande d'accès au serveur"):
    nom = discord.ui.TextInput(label="Nom", placeholder="Votre nom", required=True)
    prenom = discord.ui.TextInput(label="Prénom", placeholder="Votre prénom", required=True)

    def __init__(self, bot, user_id: int):
        super().__init__()
        self.bot = bot
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Délai de réponse immédiat pour éviter les timeouts
            await interaction.response.defer(ephemeral=True)

            # Récupération du cog whitelist
            cog = self.bot.get_cog("whitelist")
            if cog is None:
                await interaction.followup.send("❌ Erreur interne, le cog whitelist est introuvable.", ephemeral=True)
                return

            # Ajout / Mise à jour de la demande avec nom et prénom
            await cog.ajouter_demande(
                user_id=self.user_id,
                timestamp=datetime.utcnow().isoformat(),
                nom=self.nom.value,
                prenom=self.prenom.value
            )

            # Création de l'embed envoyé aux modérateurs
            embed = discord.Embed(
                title="📨 Nouvelle demande d'accès",
                description=(
                    f"<@{self.user_id}> a demandé à rejoindre le serveur.\n"
                    f"**Nom** : {self.nom.value}\n"
                    f"**Prénom** : {self.prenom.value}"
                ),
                color=discord.Color.blurple()
            )
            embed.set_footer(text=f"ID utilisateur : {self.user_id}")

            # Envoi de l'embed dans le salon configuré
            config = charger_config()
            salon_id = config.get("journal_validation_channel")
            if salon_id:
                salon = interaction.guild.get_channel(int(salon_id))
                if salon:
                    view = ValidationButtons(self.bot, self.user_id, self.nom.value, self.prenom.value)
                    await salon.send(embed=embed, view=view)

            await interaction.followup.send("✅ Votre demande a bien été transmise aux modérateurs.", ephemeral=True)

        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"DemandeAccesModal on_submit : {e}")
            try:
                await interaction.followup.send("❌ Une erreur est survenue pendant la demande.", ephemeral=True)
            except Exception:
                pass


# === Cog Whitelist ===
class Whitelist(commands.Cog, name="whitelist"):
    def __init__(self, bot):
        self.bot = bot
        # Lancement de la boucle de rappel
        self.rappel_demande.start()

    async def charger_demandes(self):
        return await self.bot.loop.run_in_executor(None, _charger_demandes)

    async def sauvegarder_demandes(self, data):
        await self.bot.loop.run_in_executor(None, lambda: _sauvegarder_demandes(data))

    # Ajoute ou met à jour une demande avec user_id, timestamp, nom et prénom
    async def ajouter_demande(self, user_id, timestamp, nom, prenom):
        demandes = await self.charger_demandes()
        updated = False
        for d in demandes:
            if str(user_id) == str(d["user_id"]):
                d["timestamp"] = timestamp
                d["nom"] = nom
                d["prenom"] = prenom
                updated = True
                break
        if not updated:
            demandes.append({
                "user_id": str(user_id),
                "timestamp": timestamp,
                "nom": nom,
                "prenom": prenom
            })
        await self.sauvegarder_demandes(demandes)

    async def supprimer_demande(self, user_id):
        demandes = await self.charger_demandes()
        nouvelles = [d for d in demandes if str(d["user_id"]) != str(user_id)]
        await self.sauvegarder_demandes(nouvelles)

    # Commande /demander_acces lance le modal pour saisir nom et prénom
    @app_commands.command(
        name="demander_acces",
        description="Demande à rejoindre le serveur (réservé aux nouveaux membres)"
    )
    @app_commands.check(check_non_verified)
    async def demander_acces(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(DemandeAccesModal(self.bot, interaction.user.id))
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"demander_acces : {e}")
            try:
                await interaction.response.send_message("❌ Une erreur est survenue pendant la demande.", ephemeral=True)
            except Exception:
                pass

    @app_commands.command(
        name="definir_journal_validation",
        description="Définit le salon où sont envoyées les demandes."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_journal_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        """Définit le salon où les demandes de whitelist seront envoyées."""
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)

        config = charger_config()
        config["journal_validation_channel"] = str(salon.id)
        sauvegarder_config(config)  # Sauvegarde sur disque, persiste au redémarrage
        await interaction.response.send_message(
            f"✅ Salon de journalisation défini : {salon.mention}",
            ephemeral=True
        )

    @app_commands.command(
        name="definir_salon_rappel",
        description="Définit le salon où les rappels sont envoyés."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_rappel(self, interaction: discord.Interaction, salon: discord.TextChannel):
        """Définit le salon où les rappels pour les demandes non traitées seront envoyés."""
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["salon_rappel_whitelist"] = str(salon.id)
        sauvegarder_config(config)
        await interaction.response.send_message(
            f"✅ Salon de rappel défini : {salon.mention}",
            ephemeral=True
        )

    @app_commands.command(
        name="definir_message_validation",
        description="Définit le message privé envoyé lors de l'acceptation."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_message_validation(self, interaction: discord.Interaction, message: str):
        """Définit le message privé envoyé à l'utilisateur lorsqu'il est accepté."""
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["message_validation"] = message
        sauvegarder_config(config)
        await interaction.response.send_message(
            "✅ Message de validation enregistré avec succès.",
            ephemeral=True
        )

    # Rappel périodique des demandes (affiche nom et prénom dans le rappel)
    @tasks.loop(minutes=60)
    async def rappel_demande(self):
        """Envoie périodiquement un rappel dans le salon dédié s'il y a des demandes en attente."""
        try:
            config = charger_config()
            salon_id = config.get("salon_rappel_whitelist")
            if not salon_id:
                return
            salon = self.bot.get_channel(int(salon_id))
            if not salon:
                return

            demandes = await self.charger_demandes()
            for demande in demandes:
                user = self.bot.get_user(int(demande["user_id"]))
                if user:
                    try:
                        nom = demande.get('nom', 'Inconnu')
                        prenom = demande.get('prenom', 'Inconnu')
                        await salon.send(
                            f"⏰ Rappel : {user.mention} ({nom} {prenom}) attend toujours une validation."
                        )
                    except Exception:
                        pass
        except Exception as e:
            await log_erreur(self.bot, None, f"rappel_demande : {e}")

    # Nouvelle commande pour rechercher dans la whitelist approuvée
    @app_commands.command(
        name="rechercher_whitelist",
        description="Recherche un utilisateur dans la whitelist par nom ou prénom."
    )
    async def rechercher_whitelist(self, interaction: discord.Interaction, query: str):
        """
        Commande accessible seulement aux admins ou aux membres autorisés via la commande définir_permission.
        Cherche un utilisateur validé dans la whitelist par son nom ou prénom.
        """
        if not (await is_admin(interaction.user) or role_autorise(interaction, "rechercher_whitelist")):
            return await interaction.response.send_message(
                "❌ Vous n'avez pas la permission d'utiliser cette commande.", ephemeral=True
            )
        from utils.utils import charger_whitelist
        approved = await interaction.client.loop.run_in_executor(None, charger_whitelist)
        matches = [
            entry for entry in approved
            if query.lower() in entry.get("nom", "").lower()
            or query.lower() in entry.get("prenom", "").lower()
        ]
        if not matches:
            await interaction.response.send_message(f"❌ Aucun résultat pour '{query}'.", ephemeral=True)
            return

        result_text = "\n".join(
            f"ID: {entry.get('user_id')}, Nom: {entry.get('nom')}, "
            f"Prénom: {entry.get('prenom')}, Validé le: {entry.get('validated')}"
            for entry in matches
        )
        embed = discord.Embed(
            title="Résultats de la recherche",
            description=result_text,
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# === Boutons de validation (pour les modérateurs) ===
class ValidationButtons(discord.ui.View):
    def __init__(self, bot, user_id, nom, prenom):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.nom = nom
        self.prenom = prenom

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Bouton 'Accepter' : Valide l'accès d'un utilisateur :
         - Retire le rôle 'Non vérifié'
         - Ajoute le rôle 'Membre'
         - Inscrit l'utilisateur dans la whitelist stockée
         - Supprime la demande de la liste d'attente
         - Supprime le message de demande pour éviter l'encombrement
        """
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if not user:
                await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)
                return

            # Gestion des rôles
            role_nv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
            role_membre = discord.utils.get(interaction.guild.roles, name="Membre")
            if role_nv and role_nv in user.roles:
                await user.remove_roles(role_nv)
            if role_membre and role_membre not in user.roles:
                await user.add_roles(role_membre)

            # Message de validation
            config = charger_config()
            message = config.get("message_validation", "🎉 Tu as été accepté sur le serveur ! Bienvenue !")
            try:
                await user.send(message)
            except Exception:
                pass

            # Ajoute l'utilisateur dans la whitelist approuvée avec nom et prénom
            from utils.utils import charger_whitelist, sauvegarder_whitelist
            approved = await interaction.client.loop.run_in_executor(None, charger_whitelist)
            if not any(str(user.id) == str(entry.get("user_id")) for entry in approved):
                new_entry = {
                    "user_id": str(user.id),
                    "nom": self.nom,
                    "prenom": self.prenom,
                    "validated": datetime.utcnow().isoformat()
                }
                approved.append(new_entry)
                await interaction.client.loop.run_in_executor(None, sauvegarder_whitelist, approved)

            # Supprime la demande de la liste d'attente
            cog = self.bot.get_cog("whitelist")
            if cog:
                await cog.supprimer_demande(user.id)

            # Supprime le message (embed + boutons) du salon
            try:
                await interaction.message.delete()
            except Exception:
                pass

            await interaction.followup.send("✅ Utilisateur accepté.", ephemeral=True)

        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons accepter : {e}")
            try:
                await interaction.followup.send("❌ Erreur lors de la validation.", ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Bouton 'Refuser' : Refuse l'accès d'un utilisateur :
         - Supprime la demande de la liste d'attente
         - Supprime le message de demande pour éviter l'encombrement
        """
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if not user:
                await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)
                return

            try:
                await user.send("❌ Votre demande a été refusée. Contactez un modérateur si besoin.")
            except Exception:
                pass

            cog = self.bot.get_cog("whitelist")
            if cog:
                await cog.supprimer_demande(user.id)

            # Supprime le message du salon
            try:
                await interaction.message.delete()
            except Exception:
                pass

            await interaction.followup.send("⛔ Utilisateur refusé.", ephemeral=True)

        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons refuser : {e}")
            try:
                await interaction.followup.send("❌ Erreur lors du refus.", ephemeral=True)
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(Whitelist(bot))
