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

# --- Checks ---
async def check_non_verified(interaction: discord.Interaction) -> bool:
    if await is_non_verified_user(interaction.user):
        return True
    raise app_commands.CheckFailure("❌ Commande réservée aux membres non vérifiés.")

async def check_verified(interaction: discord.Interaction) -> bool:
    if await is_non_verified_user(interaction.user):
        raise app_commands.CheckFailure("❌ Commande réservée aux membres validés.")
    return True

# --- Fonctions utilitaires ---
def _charger_demandes():
    if not os.path.exists(DEMANDES_PATH):
        return []
    try:
        with open(DEMANDES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Whitelist] Erreur chargement demandes: {e}")
        return []

def _sauvegarder_demandes(data):
    os.makedirs(os.path.dirname(DEMANDES_PATH), exist_ok=True)
    with open(DEMANDES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# --- Modal de demande d'accès ---
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
            cog = self.bot.get_cog('whitelist')  # type: ignore
            if cog is None:
                await interaction.followup.send("❌ Cog whitelist introuvable.", ephemeral=True)
                return
            # Enregistrer
            ts = datetime.utcnow().isoformat()
            await cog.ajouter_demande(self.user_id, ts, self.nom.value, self.prenom.value)
            # Notifier staff
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
            if chan_id and interaction.guild:
                chan = interaction.guild.get_channel(int(chan_id))
                if isinstance(chan, discord.TextChannel):
                    view = ValidationButtons(self.bot, self.user_id, self.nom.value, self.prenom.value)
                    await chan.send(embed=embed, view=view)
            await interaction.followup.send("✅ Votre demande a été transmise.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"Modal.on_submit: {e}")
            try:
                await interaction.followup.send("❌ Erreur lors de la demande.", ephemeral=True)
            except:
                pass

# --- Cog principal ---
class Whitelist(commands.Cog, name="whitelist"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rappel_demande.start()

    # --- Gestion des demandes JSON ---
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
        rest = [d for d in demandes if d['user_id'] != str(user_id)]
        await self.sauvegarder_demandes(rest)

    # --- Commande slash /demander (accessible aux non vérifiés) ---
    @app_commands.command(name="demander", description="Demande d'accès au serveur")
    @app_commands.check(check_non_verified)
    async def demander(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(DemandeAccesModal(self.bot, interaction.user.id))
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"demander: {e}")
            try:
                await interaction.response.send_message("❌ Erreur, réessayez.", ephemeral=True)
            except:
                pass

    # Alias /demander_acces
    @app_commands.command(name="demander_acces", description="Alias: demander")
    @app_commands.check(check_non_verified)
    async def demander_acces(self, interaction: discord.Interaction):
        await self.demander.callback(self, interaction)  # type: ignore

    # --- Commandes admin (vérifiés seulement) ---
    @app_commands.command(name="definir_journal_validation", description="Salon de réception des demandes")
    @app_commands.check(check_verified)
    @app_commands.default_permissions(administrator=True)
    async def definir_journal_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg['journal_validation_channel'] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Journal: {salon.mention}", ephemeral=True)

    @app_commands.command(name="definir_salon_rappel", description="Salon pour rappels")
    @app_commands.check(check_verified)
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_rappel(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg['salon_rappel_whitelist'] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Rappel: {salon.mention}", ephemeral=True)

    @app_commands.command(name="definir_message_validation", description="Message privé sur acceptation")
    @app_commands.check(check_verified)
    @app_commands.default_permissions(administrator=True)
    async def definir_message_validation(self, interaction: discord.Interaction, message: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg['message_validation'] = message
        sauvegarder_config(cfg)
        await interaction.response.send_message("✅ Message mis à jour.", ephemeral=True)

    @app_commands.command(name="rechercher_whitelist", description="Recherche un utilisateur validé")
    @app_commands.check(check_verified)
    async def rechercher_whitelist(self, interaction: discord.Interaction, query: str):
        if not (await is_admin(interaction.user) or role_autorise(interaction, 'rechercher_whitelist')):
            return await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
        from utils.utils import charger_whitelist
        wl = await interaction.client.loop.run_in_executor(None, charger_whitelist)
        filt = [e for e in wl if query.lower() in e.get('nom','').lower() or query.lower() in e.get('prenom','').lower()]
        if not filt:
            return await interaction.response.send_message(f"❌ Aucun résultat pour {query}.", ephemeral=True)
        desc = '\n'.join(f"{e['user_id']}: {e['nom']} {e['prenom']} validé le {e['validated']}" for e in filt)
        embed = discord.Embed(title='Résultats', description=desc, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="retirer_whitelist", description="Retire un utilisateur validé")
    @app_commands.check(check_verified)
    @app_commands.default_permissions(administrator=True)
    async def retirer_whitelist(self, interaction: discord.Interaction, utilisateur: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        from utils.utils import charger_whitelist, sauvegarder_whitelist
        wl = await interaction.client.loop.run_in_executor(None, charger_whitelist)
        entry = next((e for e in wl if e['user_id']==str(utilisateur.id)), None)
        if entry:
            wl.remove(entry)
            await interaction.client.loop.run_in_executor(None, sauvegarder_whitelist, wl)
        # Rôles
        r_nv = discord.utils.get(interaction.guild.roles, name='Non vérifié')
        r_m = discord.utils.get(interaction.guild.roles, name='Membre')
        if r_m and r_m in utilisateur.roles: await utilisateur.remove_roles(r_m)
        if r_nv and r_nv not in utilisateur.roles: await utilisateur.add_roles(r_nv)
        await interaction.response.send_message(
            f"✅ {utilisateur.mention} retiré et statut réinitialisé." if entry else
            f"ℹ️ Statut de {utilisateur.mention} réinitialisé.", ephemeral=True)

    # --- Tâche de rappel ---
    @tasks.loop(minutes=60)
    async def rappel_demande(self):
        try:
            cfg = charger_config()
            chan = self.bot.get_channel(int(cfg.get('salon_rappel_whitelist', 0)))
            if not chan: return
            for d in await self.charger_demandes():
                user = self.bot.get_user(int(d['user_id']))
                if user:
                    await chan.send(f"⏰ Rappel: {user.mention} ({d['nom']} {d['prenom']}) en attente.")
        except Exception as e:
            await log_erreur(self.bot, None, f"rappel_demande: {e}")

# --- Boutons de validation ---
class ValidationButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, nom: str, prenom: str):
        super().__init__(timeout=None)
        self.bot, self.user_id, self.nom, self.prenom = bot, user_id, nom, prenom

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if user:
                nv = discord.utils.get(interaction.guild.roles, name='Non vérifié')
                mb = discord.utils.get(interaction.guild.roles, name='Membre')
                if nv in user.roles: await user.remove_roles(nv)
                if mb not in user.roles: await user.add_roles(mb)
                cfg = charger_config()
                try: await user.send(cfg.get('message_validation','🎉 Bienvenue !'))
                except: pass
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

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
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
