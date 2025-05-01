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

class DemandeAccesModal(discord.ui.Modal, title="Demande d'accès au serveur"):
    nom = discord.ui.TextInput(label="Nom", placeholder="Votre nom", required=True)
    prenom = discord.ui.TextInput(label="Prénom", placeholder="Votre prénom", required=True)

    def __init__(self, bot, user_id: int):
        super().__init__()
        self.bot = bot
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            cog = self.bot.get_cog("whitelist")
            if cog is None:
                await interaction.followup.send("❌ Erreur interne : cog whitelist introuvable.", ephemeral=True)
                return

            # Enregistrer la demande
            await cog.ajouter_demande(
                user_id=self.user_id,
                timestamp=datetime.utcnow().isoformat(),
                nom=self.nom.value,
                prenom=self.prenom.value
            )

            # Envoyer au salon de validation
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
            salon_id = cfg.get("journal_validation_channel")
            if salon_id:
                salon = interaction.guild.get_channel(int(salon_id))
                if salon:
                    view = ValidationButtons(self.bot, self.user_id, self.nom.value, self.prenom.value)
                    await salon.send(embed=embed, view=view)

            await interaction.followup.send("✅ Votre demande a été transmise aux modérateurs.", ephemeral=True)

        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"DemandeAccesModal on_submit : {e}")
            try:
                await interaction.followup.send("❌ Une erreur est survenue pendant la demande.", ephemeral=True)
            except:
                pass

class Whitelist(commands.Cog, name="whitelist"):
    def __init__(self, bot):
        self.bot = bot
        self.rappel_demande.start()

    async def charger_demandes(self):
        return await self.bot.loop.run_in_executor(None, _charger_demandes)

    async def sauvegarder_demandes(self, data):
        await self.bot.loop.run_in_executor(None, lambda: _sauvegarder_demandes(data))

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

    @app_commands.command(
        name="demander_acces",
        description="Demande à rejoindre le serveur (réservé aux nouveaux membres)"
    )
    @app_commands.check(is_non_verified_user)
    async def demander_acces(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(DemandeAccesModal(self.bot, interaction.user.id))
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"demander_acces : {e}")
            try:
                await interaction.response.send_message("❌ Une erreur est survenue pendant la demande.", ephemeral=True)
            except:
                pass

    @app_commands.command(
        name="definir_journal_validation",
        description="Définit le salon où sont envoyées les demandes."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_journal_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        cfg = charger_config()
        cfg["journal_validation_channel"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon de validation défini : {salon.mention}", ephemeral=True)

    @app_commands.command(
        name="definir_salon_rappel",
        description="Définit le salon où les rappels sont envoyés."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_rappel(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        cfg = charger_config()
        cfg["salon_rappel_whitelist"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon de rappel défini : {salon.mention}", ephemeral=True)

    @app_commands.command(
        name="definir_message_validation",
        description="Définit le message privé envoyé lors de l'acceptation."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_message_validation(self, interaction: discord.Interaction, message: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        cfg = charger_config()
        cfg["message_validation"] = message
        sauvegarder_config(cfg)
        await interaction.response.send_message("✅ Message de validation enregistré.", ephemeral=True)

    @tasks.loop(minutes=60)
    async def rappel_demande(self):
        try:
            cfg = charger_config()
            salon_id = cfg.get("salon_rappel_whitelist")
            if not salon_id:
                return
            salon = self.bot.get_channel(int(salon_id))
            if not salon:
                return
            demandes = await self.charger_demandes()
            for d in demandes:
                user = self.bot.get_user(int(d["user_id"]))
                if user:
                    nom = d.get("nom", "Inconnu")
                    prenom = d.get("prenom", "Inconnu")
                    await salon.send(f"⏰ Rappel : {user.mention} ({nom} {prenom}) attend validation.")
        except Exception as e:
            await log_erreur(self.bot, None, f"rappel_demande : {e}")

    @app_commands.command(
        name="rechercher_whitelist",
        description="Recherche un utilisateur dans la whitelist par nom ou prénom."
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
            return await interaction.response.send_message(f"❌ Aucun résultat pour «{query}».", ephemeral=True)
        texte = "\n".join(
            f"ID:{m['user_id']} • {m['nom']} {m['prenom']} (validé le {m['validated']})"
            for m in matches
        )
        embed = discord.Embed(title="Résultats", description=texte, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="retirer_whitelist",
        description="Retire un utilisateur de la whitelist et réinitialise son statut."
    )
    @app_commands.default_permissions(administrator=True)
    async def retirer_whitelist(self, interaction: discord.Interaction, utilisateur: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        from utils.utils import charger_whitelist, sauvegarder_whitelist
        approved = await interaction.client.loop.run_in_executor(None, charger_whitelist)
        entry = next((e for e in approved if e["user_id"] == str(utilisateur.id)), None)
        if entry:
            approved.remove(entry)
            await interaction.client.loop.run_in_executor(None, sauvegarder_whitelist, approved)
        # Remise à jour des rôles
        role_nv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
        role_m = discord.utils.get(interaction.guild.roles, name="Membre")
        if role_m in utilisateur.roles:
            await utilisateur.remove_roles(role_m)
        if role_nv not in utilisateur.roles:
            await utilisateur.add_roles(role_nv)
        await interaction.response.send_message(
            "✅ Utilisateur retiré de la whitelist et statut réinitialisé.", ephemeral=True
        )

class ValidationButtons(discord.ui.View):
    def __init__(self, bot, user_id, nom, prenom):
        super().__init__(timeout=None)
        self.bot, self.user_id, self.nom, self.prenom = bot, user_id, nom, prenom

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if not user:
                return await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)
            # Retirer rôle Non vérifié, ajouter rôle Membre
            role_nv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
            role_m = discord.utils.get(interaction.guild.roles, name="Membre")
            if role_nv in user.roles:
                await user.remove_roles(role_nv)
            if role_m not in user.roles:
                await user.add_roles(role_m)
            # Envoyer message privé de validation
            cfg = charger_config()
            try:
                await user.send(cfg.get("message_validation", "🎉 Vous avez été accepté(e) sur le serveur !"))
            except:
                pass
            # Ajouter à la whitelist
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
            # Supprimer la demande
            await self.bot.get_cog("whitelist").supprimer_demande(user.id)
            # Supprimer le message de demande
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.followup.send("✅ Utilisateur accepté.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons accepter : {e}")
            try:
                await interaction.followup.send("❌ Erreur lors de la validation.", ephemeral=True)
            except:
                pass

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if user:
                try:
                    await user.send("❌ Votre demande a été refusée. Contactez un modérateur si besoin.")
                except:
                    pass
            await self.bot.get_cog("whitelist").supprimer_demande(self.user_id)
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.followup.send("⛔ Utilisateur refusé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons refuser : {e}")
            try:
                await interaction.followup.send("❌ Erreur lors du refus.", ephemeral=True)
            except:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
