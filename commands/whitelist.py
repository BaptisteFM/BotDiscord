import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
from datetime import datetime
from utils.utils import (
    is_admin,
    is_non_verified_user,
    charger_config,
    sauvegarder_config,
    log_erreur,
    role_autorise
)

# Fichier de stockage des demandes
DEMANDES_PATH = "data/demandes_whitelist.json"

# --- Fonctions utilitaires internes ---
def _charger_demandes():
    """Charge la liste des demandes depuis le fichier JSON."""
    if not os.path.exists(DEMANDES_PATH):
        return []
    try:
        with open(DEMANDES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        # En cas d'erreur, log et retourne liste vide
        print(f"[whitelist] Erreur chargement demandes: {e}")
        return []

def _sauvegarder_demandes(data):
    """Sauvegarde la liste des demandes dans le fichier JSON."""
    os.makedirs(os.path.dirname(DEMANDES_PATH), exist_ok=True)
    with open(DEMANDES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- Check global: seuls validés peuvent exécuter toutes les commandes sauf /demander_acces ---
async def global_command_check(interaction: discord.Interaction) -> bool:
    # Toujours autoriser /demander_acces pour les non vérifiés
    if interaction.command.name == 'demander_acces':
        return True
    # Bloquer tous les autres si non vérifié
    if await is_non_verified_user(interaction.user):
        raise app_commands.CheckFailure("❌ Commande réservée aux membres vérifiés.")
    return True

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
            cog: Whitelist = self.bot.get_cog('whitelist')  # type: ignore
            if cog is None:
                await interaction.followup.send("❌ Erreur interne: cog whitelist introuvable.", ephemeral=True)
                return
            # Enregistrer la demande
            timestamp = datetime.utcnow().isoformat()
            await cog.ajouter_demande(self.user_id, timestamp, self.nom.value, self.prenom.value)
            # Notifier le staff
            embed = discord.Embed(
                title="📨 Nouvelle demande d'accès",
                description=(
                    f"<@{self.user_id}> a demandé l'accès.\n"
                    f"**Nom**: {self.nom.value}\n"
                    f"**Prénom**: {self.prenom.value}"
                ),
                color=discord.Color.blurple()
            )
            embed.set_footer(text=f"ID utilisateur: {self.user_id}")
            cfg = charger_config()
            chan_id = cfg.get('journal_validation_channel')
            if chan_id:
                chan = interaction.guild.get_channel(int(chan_id)) if interaction.guild else None
                if isinstance(chan, discord.TextChannel):
                    view = ValidationButtons(self.bot, self.user_id, self.nom.value, self.prenom.value)
                    await chan.send(embed=embed, view=view)
            await interaction.followup.send("✅ Votre demande a été transmise.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"Modal.on_submit: {e}")
            try:
                await interaction.followup.send("❌ Erreur lors de l'envoi de la demande.", ephemeral=True)
            except:
                pass

class Whitelist(commands.Cog, name="whitelist"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Ajout du check global
        bot.tree.add_check(global_command_check)
        # Démarrage des tâches
        self.rappel_demande.start()

    # --- Gestion JSON ---
    async def charger_demandes(self):
        return await self.bot.loop.run_in_executor(None, _charger_demandes)

    async def sauvegarder_demandes(self, data):
        await self.bot.loop.run_in_executor(None, lambda: _sauvegarder_demandes(data))

    async def ajouter_demande(self, user_id: int, timestamp: str, nom: str, prenom: str):
        demandes = await self.charger_demandes()
        for d in demandes:
            if d['user_id'] == str(user_id):
                d.update({'timestamp': timestamp, 'nom': nom, 'prenom': prenom})
                break
        else:
            demandes.append({'user_id': str(user_id), 'timestamp': timestamp, 'nom': nom, 'prenom': prenom})
        await self.sauvegarder_demandes(demandes)

    async def supprimer_demande(self, user_id: int):
        demandes = await self.charger_demandes()
        filt = [d for d in demandes if d['user_id'] != str(user_id)]
        await self.sauvegarder_demandes(filt)

    # --- Commandes utilisateur ---
    @app_commands.command(
        name="demander_acces",
        description="Demande à rejoindre le serveur."
    )
    async def demander_acces(self, interaction: discord.Interaction):
        # check_global autorise seulement si non vérifié
        try:
            await interaction.response.send_modal(DemandeAccesModal(self.bot, interaction.user.id))
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"demander_acces: {e}")
            try:
                await interaction.response.send_message("❌ Erreur, réessayez.", ephemeral=True)
            except:
                pass

    # --- Commandes admin ---
    @app_commands.command(
        name="definir_journal_validation",
        description="Définit le salon de réception des demandes."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_journal_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg['journal_validation_channel'] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon validation: {salon.mention}", ephemeral=True)

    @app_commands.command(
        name="definir_salon_rappel",
        description="Définit le salon pour rappels de demandes."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_rappel(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg['salon_rappel_whitelist'] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon rappel: {salon.mention}", ephemeral=True)

    @app_commands.command(
        name="definir_message_validation",
        description="Message privé envoyé à l'acceptation."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_message_validation(self, interaction: discord.Interaction, message: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg['message_validation'] = message
        sauvegarder_config(cfg)
        await interaction.response.send_message("✅ Message validation mis à jour.", ephemeral=True)

    @app_commands.command(
        name="rechercher_whitelist",
        description="Recherche un utilisateur validé."
    )
    async def rechercher_whitelist(self, interaction: discord.Interaction, query: str):
        if not (await is_admin(interaction.user) or role_autorise(interaction, 'rechercher_whitelist')):
            return await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
        from utils.utils import charger_whitelist
        wl = await interaction.client.loop.run_in_executor(None, charger_whitelist)
        filt = [e for e in wl if query.lower() in e.get('nom','').lower() or query.lower() in e.get('prenom','').lower()]
        if not filt:
            return await interaction.response.send_message(f"❌ Aucun résultat pour {query}.", ephemeral=True)
        desc = '\n'.join(f"{e['user_id']}: {e['nom']} {e['prenom']} validé le {e['validated']}" for e in filt)
        await interaction.response.send_message(embed=discord.Embed(title='Résultats', description=desc, color=discord.Color.green()), ephemeral=True)

    @app_commands.command(
        name="retirer_whitelist",
        description="Retire un utilisateur validé et remet son statut."
    )
    @app_commands.default_permissions(administrator=True)
    async def retirer_whitelist(self, interaction: discord.Interaction, utilisateur: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé admins.", ephemeral=True)
        from utils.utils import charger_whitelist, sauvegarder_whitelist
        wl = await interaction.client.loop.run_in_executor(None, charger_whitelist)
        entry = next((e for e in wl if e['user_id']==str(utilisateur.id)), None)
        if entry:
            wl.remove(entry)
            await interaction.client.loop.run_in_executor(None, sauvegarder_whitelist, wl)
        # Rôles
        r_nv = discord.utils.get(interaction.guild.roles, name='Non vérifié')
        r_m = discord.utils.get(interaction.guild.roles, name='Membre')
        if r_m and r_m in utilisateur.roles:
            await utilisateur.remove_roles(r_m)
        if r_nv and r_nv not in utilisateur.roles:
            await utilisateur.add_roles(r_nv)
        await interaction.response.send_message(
            "✅ Utilisateur retiré et statut réinitialisé." if entry else "ℹ️ Vérification réinitialisée.",
            ephemeral=True
        )

    # --- Rappel périodique ---
    @tasks.loop(minutes=60)
    async def rappel_demande(self):
        try:
            cfg = charger_config()
            chan_id = cfg.get('salon_rappel_whitelist')
            if not chan_id:
                return
            chan = self.bot.get_channel(int(chan_id))
            if not chan:
                return
            for d in await self.charger_demandes():
                user = self.bot.get_user(int(d['user_id']))
                if user:
                    await chan.send(f"⏰ Rappel: {user.mention} ({d.get('nom')},{d.get('prenom')}) en attente.")
        except Exception as e:
            await log_erreur(self.bot, None, f"rappel_demande: {e}")

# --- Boutons de validation pour le staff ---
class ValidationButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, nom: str, prenom: str):
        super().__init__(timeout=None)
        self.bot, self.user_id, self.nom, self.prenom = bot, user_id, nom, prenom

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success, custom_id="accept_whitelist")
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if user:
                r_nv = discord.utils.get(interaction.guild.roles, name='Non vérifié')
                r_m = discord.utils.get(interaction.guild.roles, name='Membre')
                if r_nv in user.roles: await user.remove_roles(r_nv)
                if r_m not in user.roles: await user.add_roles(r_m)
                # DM de bienvenue
                cfg = charger_config()
                try: await user.send(cfg.get('message_validation','🎉 Bienvenue !'))
                except: pass
                # Ajout fichier
                from utils.utils import charger_whitelist, sauvegarder_whitelist
                wl = await interaction.client.loop.run_in_executor(None, charger_whitelist)
                if not any(e['user_id']==str(user.id) for e in wl):
                    wl.append({'user_id':str(user.id),'nom':self.nom,'prenom':self.prenom,'validated':datetime.utcnow().isoformat()})
                    await interaction.client.loop.run_in_executor(None, sauvegarder_whitelist, wl)
                await self.bot.get_cog('whitelist').supprimer_demande(user.id)
                try: await interaction.message.delete()
                except: pass
                await interaction.followup.send('✅ Utilisateur accepté.', ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons accepter: {e}")
            try: await interaction.followup.send('❌ Erreur validation.', ephemeral=True)
            except: pass

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger, custom_id="deny_whitelist")
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if user:
                try: await user.send('❌ Demande refusée.')
                except: pass
            await self.bot.get_cog('whitelist').supprimer_demande(self.user_id)
            try: await interaction.message.delete()
            except: pass
            await interaction.followup.send('⛔ Utilisateur refusé.', ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons refuser: {e}")
            try: await interaction.followup.send('❌ Erreur refus.', ephemeral=True)
            except: pass

async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
