import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime
from utils.utils import (
    is_admin,
    is_non_verified_user,
    charger_config,
    sauvegarder_config,
    log_erreur,
    role_autorise
)

# Chemin du fichier stockant les demandes (en attente)
DEMANDES_PATH = "data/demandes_whitelist.json"

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

# ——— Modal de saisie nom/prénom —————————————————————————————
class DemandeAccesModal(discord.ui.Modal, title="Demande d'accès au serveur"):
    nom = discord.ui.TextInput(label="Nom", placeholder="Votre nom", required=True)
    prenom = discord.ui.TextInput(label="Prénom", placeholder="Votre prénom", required=True)

    def __init__(self, bot: commands.Bot, user_id: int):
        super().__init__()
        self.bot = bot
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            cog = self.bot.get_cog("whitelist")
            if cog is None:
                await interaction.followup.send("❌ Cog whitelist introuvable.", ephemeral=True)
                return

            # Enregistrement
            await cog.ajouter_demande(
                user_id=self.user_id,
                timestamp=datetime.utcnow().isoformat(),
                nom=self.nom.value,
                prenom=self.prenom.value
            )

            # Notification staff
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

            cfg = charger_config()
            chan_id = cfg.get("journal_validation_channel")
            if chan_id:
                chan = interaction.guild.get_channel(int(chan_id))
                if chan:
                    view = ValidationButtons(self.bot, self.user_id, self.nom.value, self.prenom.value)
                    await chan.send(embed=embed, view=view)

            await interaction.followup.send("✅ Votre demande a été transmise aux modérateurs.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"Modal on_submit: {e}")
            try:
                await interaction.followup.send("❌ Erreur lors de la demande.", ephemeral=True)
            except:
                pass

# ——— View du bouton “Demander accès” —————————————————————————
class DemandeAccesButtonView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Demander accès", style=discord.ButtonStyle.primary, custom_id="demande_acces_btn")
    async def demander_acces(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Vérification
            if not await is_non_verified_user(interaction.user):
                return await interaction.response.send_message(
                    "🛑 Vous êtes déjà vérifié(e).", ephemeral=True
                )
            # Ouvre le modal
            await interaction.response.send_modal(DemandeAccesModal(self.bot, interaction.user.id))
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ButtonView error: {e}")
            try:
                await interaction.response.send_message("❌ Erreur interne, réessayez plus tard.", ephemeral=True)
            except:
                pass

# ——— Le cog principal —————————————————————————————————————
class Whitelist(commands.Cog, name="whitelist"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # On démarre la boucle de rappel
        self.rappel_demande.start()

    # Chargement/sauvegarde JSON
    async def charger_demandes(self):
        return await self.bot.loop.run_in_executor(None, _charger_demandes)

    async def sauvegarder_demandes(self, data):
        await self.bot.loop.run_in_executor(None, lambda: _sauvegarder_demandes(data))

    # Ajout et suppression de demande
    async def ajouter_demande(self, user_id, timestamp, nom, prenom):
        demandes = await self.charger_demandes()
        for d in demandes:
            if str(d["user_id"]) == str(user_id):
                d.update({"timestamp": timestamp, "nom": nom, "prenom": prenom})
                break
        else:
            demandes.append({
                "user_id": str(user_id),
                "timestamp": timestamp,
                "nom": nom,
                "prenom": prenom
            })
        await self.sauvegarder_demandes(demandes)

    async def supprimer_demande(self, user_id):
        demandes = await self.charger_demandes()
        restantes = [d for d in demandes if d["user_id"] != str(user_id)]
        await self.sauvegarder_demandes(restantes)

    # — Commandes admin ——————————————————————————————————
    @app_commands.command(
        name="creer_message_demande",
        description="Publie le message avec le bouton pour demander l'accès."
    )
    @app_commands.default_permissions(administrator=True)
    async def creer_message_demande(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)

        embed = discord.Embed(
            title="📥 Demande d'accès",
            description="Cliquez sur **Demander accès** pour remplir le formulaire.",
            color=discord.Color.blue()
        )
        view = DemandeAccesButtonView(self.bot)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(
        name="definir_journal_validation",
        description="Choisit le salon de réception des demandes."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_journal_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["journal_validation_channel"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Journal défini sur {salon.mention}", ephemeral=True)

    @app_commands.command(
        name="definir_salon_rappel",
        description="Choisit le salon pour les rappels de demandes en attente."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_rappel(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["salon_rappel_whitelist"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon de rappel défini sur {salon.mention}", ephemeral=True)

    @app_commands.command(
        name="definir_message_validation",
        description="Message privé envoyé au membre lors de l'acceptation."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_message_validation(self, interaction: discord.Interaction, message: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["message_validation"] = message
        sauvegarder_config(cfg)
        await interaction.response.send_message("✅ Message de validation mis à jour.", ephemeral=True)

    @app_commands.command(
        name="retirer_whitelist",
        description="Retire un membre de la whitelist et remet son rôle Non vérifié."
    )
    @app_commands.default_permissions(administrator=True)
    async def retirer_whitelist(self, interaction: discord.Interaction, utilisateur: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)

        from utils.utils import charger_whitelist, sauvegarder_whitelist
        approved = await interaction.client.loop.run_in_executor(None, charger_whitelist)
        found = next((e for e in approved if e["user_id"] == str(utilisateur.id)), None)
        if found:
            approved.remove(found)
            await interaction.client.loop.run_in_executor(None, sauvegarder_whitelist, approved)

        # Mise à jour des rôles quoi qu'il arrive
        role_m = discord.utils.get(interaction.guild.roles, name="Membre")
        role_nv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
        if role_m in utilisateur.roles:
            await utilisateur.remove_roles(role_m)
        if role_nv not in utilisateur.roles:
            await utilisateur.add_roles(role_nv)

        msg = (
            f"✅ {utilisateur.mention} retiré de la whitelist et rôle réinitialisé."
            if found else
            f"ℹ️ {utilisateur.mention} n'était pas en whitelist, rôle réinitialisé."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    # — Boucle de rappel toutes les heures —————————————————————
    @tasks.loop(minutes=60)
    async def rappel_demande(self):
        try:
            cfg = charger_config()
            chan = self.bot.get_channel(int(cfg.get("salon_rappel_whitelist", 0)))
            if not chan:
                return
            for d in await self.charger_demandes():
                user = self.bot.get_user(int(d["user_id"]))
                if user:
                    await chan.send(f"⏰ Rappel : {user.mention} ({d['nom']} {d['prenom']}) en attente.")
        except Exception as e:
            await log_erreur(self.bot, None, f"rappel_demande: {e}")

    # — Recherche dans whitelist —————————————————————————————
    @app_commands.command(
        name="rechercher_whitelist",
        description="Recherche un utilisateur dans la whitelist."
    )
    async def rechercher_whitelist(self, interaction: discord.Interaction, query: str):
        if not (await is_admin(interaction.user) or role_autorise(interaction, "rechercher_whitelist")):
            return await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)

        from utils.utils import charger_whitelist
        approved = await interaction.client.loop.run_in_executor(None, charger_whitelist)
        matches = [
            e for e in approved
            if query.lower() in e.get("nom", "").lower() or query.lower() in e.get("prenom", "").lower()
        ]
        if not matches:
            return await interaction.response.send_message(f"❌ Aucun résultat pour « {query} ».", ephemeral=True)

        texte = "\n".join(
            f"ID:{m['user_id']} • {m['nom']} {m['prenom']} validé le {m['validated']}"
            for m in matches
        )
        embed = discord.Embed(title="Résultats", description=texte, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ——— ValidationButtons (pour staff) ———————————————————————————
class ValidationButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id, nom, prenom):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.nom = nom
        self.prenom = prenom

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success, custom_id="valider_btn")
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if not user:
                return await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)

            nv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
            mb = discord.utils.get(interaction.guild.roles, name="Membre")
            if nv in user.roles:
                await user.remove_roles(nv)
            if mb not in user.roles:
                await user.add_roles(mb)

            cfg = charger_config()
            try:
                await user.send(cfg.get("message_validation", "🎉 Bienvenue !"))
            except:
                pass

            from utils.utils import charger_whitelist, sauvegarder_whitelist
            wl = await interaction.client.loop.run_in_executor(None, charger_whitelist)
            if not any(e["user_id"] == str(user.id) for e in wl):
                wl.append({
                    "user_id": str(user.id),
                    "nom": self.nom,
                    "prenom": self.prenom,
                    "validated": datetime.utcnow().isoformat()
                })
                await interaction.client.loop.run_in_executor(None, sauvegarder_whitelist, wl)

            await self.bot.get_cog("whitelist").supprimer_demande(user.id)
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.followup.send("✅ Utilisateur accepté.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons accepter: {e}")
            try:
                await interaction.followup.send("❌ Erreur lors de la validation.", ephemeral=True)
            except:
                pass

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger, custom_id="refuser_btn")
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if user:
                try:
                    await user.send("❌ Votre demande a été refusée.")
                except:
                    pass
            await self.bot.get_cog("whitelist").supprimer_demande(self.user_id)
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.followup.send("⛔ Utilisateur refusé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons refuser: {e}")
            try:
                await interaction.followup.send("❌ Erreur lors du refus.", ephemeral=True)
            except:
                pass

# ——— Setup du cog + enregistrement persistant du bouton —————————
async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
    # Enregistrement persistant de la view "DemandeAccesButtonView"
    bot.add_view(DemandeAccesButtonView(bot))
