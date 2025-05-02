import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import json
import os
from datetime import datetime
from utils.utils import (
    is_admin,
    charger_config,
    sauvegarder_config,
    log_erreur,
    role_autorise
)

# --- Chemins et locks ---
DEMANDES_PATH = "data/demandes_whitelist.json"
WL_PATH = "data/whitelist.json"
demandes_lock = asyncio.Lock()
whitelist_lock = asyncio.Lock()

# --- Fonctions utilitaires JSON ---
def _load_json(path: str):
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        # Log corruption
        print(f"[WHITELIST] Erreur chargement JSON {path}: {e}")
        return []

def _save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[WHITELIST] Erreur écriture JSON {path}: {e}")

async def load_demandes():
    async with demandes_lock:
        return await asyncio.get_event_loop().run_in_executor(None, _load_json, DEMANDES_PATH)

async def save_demandes(data):
    async with demandes_lock:
        await asyncio.get_event_loop().run_in_executor(None, _save_json, DEMANDES_PATH, data)

async def load_whitelist():
    async with whitelist_lock:
        return await asyncio.get_event_loop().run_in_executor(None, _load_json, WL_PATH)

async def save_whitelist(data):
    async with whitelist_lock:
        await asyncio.get_event_loop().run_in_executor(None, _save_json, WL_PATH, data)

# --- DM sécurisé ---
async def safe_send_dm(user: discord.User, content: str):
    try:
        dm = user.dm_channel or await user.create_dm()
        return await dm.send(content)
    except Exception as e:
        await log_erreur(None, None, f"safe_send_dm vers {user.id} a échoué: {e}")
        return None

# --- Vue persistante pour bouton d'accès ---
class RequestAccessView(discord.ui.View, persistent=True):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Demander l'accès", style=discord.ButtonStyle.primary, custom_id="whitelist_btn_demande_acces")
    async def demander(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DemandeAccesModal(self.bot))

# --- Modal de demande d'accès ---
class DemandeAccesModal(discord.ui.Modal, title="Demande d'accès au serveur"):
    prenom = discord.ui.TextInput(label="Prénom", placeholder="Ton prénom", max_length=50)
    nom = discord.ui.TextInput(label="Nom", placeholder="Ton nom", max_length=50)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        # enregistrement
        demandes = await load_demandes()
        entry = {"user_id": user.id, "prenom": self.prenom.value, "nom": self.nom.value, "timestamp": datetime.utcnow().isoformat()}
        demandes = [d for d in demandes if d.get("user_id") != user.id] + [entry]
        await save_demandes(demandes)

        # envoi salon validation
        cfg = charger_config()
        vid = cfg.get("journal_validation_channel")
        guild = interaction.guild
        mention = ''
        if cfg.get("role_admin_id"): mention += f"<@&{cfg['role_admin_id']}> "
        if cfg.get("role_staff_id"): mention += f"<@&{cfg['role_staff_id']}>"
        embed = discord.Embed(
            title="📨 Nouvelle demande d'accès",
            description=f"**Prénom** : {self.prenom.value}\n**Nom** : {self.nom.value}",
            color=discord.Color.blurple()
        ).set_footer(text=f"ID : {user.id}")
        if vid and guild:
            ch = guild.get_channel(int(vid))
            if ch:
                await ch.send(content=mention, embed=embed, view=ValidationView(self.bot, user.id, self.prenom.value, self.nom.value))
            else:
                await safe_send_dm(user, "⚠️ Salon de validation non trouvé.")
        else:
            await safe_send_dm(user, "⚠️ Aucun salon de validation configuré.")

        await interaction.response.send_message("✅ Ta demande a été envoyée.", ephemeral=True)

# --- Vue de validation ---
class ValidationView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, prenom: str, nom: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.prenom = prenom
        self.nom = nom

    async def _get_roles(self, guild: discord.Guild):
        cfg = charger_config()
        rv = None
        rm = None
        if cfg.get("role_non_verifie_id"):
            rv = guild.get_role(int(cfg["role_non_verifie_id"]))
        if cfg.get("role_membre_id"):
            rm = guild.get_role(int(cfg["role_membre_id"]))
        return rv or discord.utils.get(guild.roles, name="Non vérifié"), rm or discord.utils.get(guild.roles, name="Membre")

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        if not member:
            return await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)
        rv, rm = await self._get_roles(guild)
        try:
            if rv and rv in member.roles: await member.remove_roles(rv)
            if rm:
                await member.add_roles(rm)
                print(f"[WHITELIST] Rôle {rm.name} ajouté à {member.display_name}")
            else:
                await log_erreur(self.bot, guild, "Rôle membre non défini.")
        except discord.Forbidden:
            await log_erreur(self.bot, guild, f"Permissions insuffisantes pour gérer les rôles de {member.id}")
        except Exception as e:
            await log_erreur(self.bot, guild, f"Erreur ajout rôle: {e}")

        # DM bienvenue
        msg_val = charger_config().get("message_validation", "🎉 Bienvenue !")
        await safe_send_dm(member, msg_val)

        # ajout whitelist
        wl = await load_whitelist()
        if not any(e.get("user_id") == member.id for e in wl):
            wl.append({"user_id": member.id, "prenom": self.prenom, "nom": self.nom, "validated": datetime.utcnow().isoformat()})
            await save_whitelist(wl)

        # suppression demande
        demandes = await load_demandes()
        demandes = [d for d in demandes if d.get("user_id") != member.id]
        await save_demandes(demandes)

        # édition message
        msg = interaction.message
        embed = msg.embeds[0]
        embed.color = discord.Color.green()
        embed.add_field(name="Statut", value=f"✅ Accepté par {interaction.user.mention}", inline=False)
        for c in self.children: c.disabled = True
        await msg.edit(content=msg.content, embed=embed, view=self)
        await interaction.followup.send("✅ Utilisateur accepté.", ephemeral=True)

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        # DM refus
        user = self.bot.get_user(self.user_id)
        if user: await safe_send_dm(user, "❌ Ta demande a été refusée.")
        # suppression demande
        demandes = await load_demandes()
        demandes = [d for d in demandes if d.get("user_id") != self.user_id]
        await save_demandes(demandes)

        # édition message
        msg = interaction.message
        embed = msg.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name="Statut", value=f"❌ Refusé par {interaction.user.mention}", inline=False)
        for c in self.children: c.disabled = True
        await msg.edit(content=msg.content, embed=embed, view=self)
        await interaction.followup.send("⛔ Utilisateur refusé.", ephemeral=True)

# --- Cog principal ---
class Whitelist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Enregistrer vue persistante
        self.bot.add_view(RequestAccessView(bot))
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    # publier bouton
    @app_commands.command(name="publier_demande_acces", description="Publier le bouton de demande d'accès")
    @app_commands.default_permissions(administrator=True)
    async def publier_demande_acces(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        embed = discord.Embed(title="Demande d'accès", description="Clique sur le bouton pour demander l'accès.", color=discord.Color.blurple())
        await salon.send(embed=embed, view=RequestAccessView(self.bot))
        await interaction.response.send_message(f"✅ Bouton publié dans {salon.mention}.", ephemeral=True)

    # définir salon validation
    @app_commands.command(name="definir_salon_validation", description="Définir salon validation")
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["journal_validation_channel"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon validation : {salon.mention}.", ephemeral=True)

    # définir salon rappel
    @app_commands.command(name="definir_salon_rappel", description="Définir salon rappel")
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_rappel(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["salon_rappel_whitelist"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon rappel : {salon.mention}.", ephemeral=True)

    # définir rôles
    @app_commands.command(name="definir_role_admin", description="Définir rôle admin pour pings")
    @app_commands.default_permissions(administrator=True)
    async def definir_role_admin(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["role_admin_id"] = str(role.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Rôle admin : {role.mention}.", ephemeral=True)

    @app_commands.command(name="definir_role_staff", description="Définir rôle staff pour pings")
    @app_commands.default_permissions(administrator=True)
    async def definir_role_staff(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["role_staff_id"] = str(role.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Rôle staff : {role.mention}.", ephemeral=True)

    @app_commands.command(name="definir_role_membre", description="Définir rôle des membres validés")
    @app_commands.default_permissions(administrator=True)
    async def definir_role_membre(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["role_membre_id"] = str(role.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Rôle membre : {role.mention}.", ephemeral=True)

    @app_commands.command(name="definir_role_non_verifie", description="Définir rôle des non vérifiés")
    @app_commands.default_permissions(administrator=True)
    async def definir_role_non_verifie(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["role_non_verifie_id"] = str(role.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Rôle non vérifié : {role.mention}.", ephemeral=True)

    @app_commands.command(name="verifier_config_whitelist", description="Vérifier configuration whitelist")
    @app_commands.default_permissions(administrator=True)
    async def verifier_config_whitelist(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        champs = {
            "Salon validation": cfg.get("journal_validation_channel"),
            "Salon rappel": cfg.get("salon_rappel_whitelist"),
            "Rôle admin": cfg.get("role_admin_id"),
            "Rôle staff": cfg.get("role_staff_id"),
            "Rôle membre": cfg.get("role_membre_id"),
            "Rôle non vérifié": cfg.get("role_non_verifie_id"),
        }
        desc = ''
        for nom, val in champs.items():
            if val:
                if 'Salon' in nom:
                    desc += f"✅ **{nom}** : <#{val}>\n"
                else:
                    desc += f"✅ **{nom}** : <@&{val}>\n"
            else:
                desc += f"❌ **{nom}** : non défini\n"
        embed = discord.Embed(title="📋 Config Whitelist", description=desc, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # commandes utilitaires : lister, rechercher, retirer
    @app_commands.command(name="lister_whitelist", description="Liste des membres whitelistés")
    @app_commands.default_permissions(administrator=True)
    async def lister_whitelist(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        wl = await load_whitelist()
        if not wl:
            return await interaction.response.send_message("ℹ️ Whitelist vide.", ephemeral=True)
        lines = [f"{e['prenom']} {e['nom']} — <@{e['user_id']}> (validé: {e['validated'][:10]})" for e in wl]
        await interaction.response.send_message(embed=discord.Embed(title="Whitelist", description="\n".join(lines), color=discord.Color.green()), ephemeral=True)

    @app_commands.command(name="rechercher_whitelist", description="Rechercher dans la whitelist")
    async def rechercher_whitelist(self, interaction: discord.Interaction, query: str):
        if not (await is_admin(interaction.user) or role_autorise(interaction, "rechercher_whitelist")):
            return await interaction.response.send_message("❌ Pas la permission.", ephemeral=True)
        wl = await load_whitelist()
        matches = [e for e in wl if query.lower() in e['prenom'].lower() or query.lower() in e['nom'].lower()]
        if not matches:
            return await interaction.response.send_message(f"❌ Aucun résultat pour '{query}'.", ephemeral=True)
        lines = [f"{e['prenom']} {e['nom']} — <@{e['user_id']}>" for e in matches]
        await interaction.response.send_message(embed=discord.Embed(title="Résultats", description="\n".join(lines), color=discord.Color.green()), ephemeral=True)

    @app_commands.command(name="retirer_whitelist", description="Retire un utilisateur de la whitelist")
    @app_commands.default_permissions(administrator=True)
    async def retirer_whitelist(self, interaction: discord.Interaction, member: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        wl = await load_whitelist()
        entry = next((e for e in wl if e['user_id'] == member.id), None)
        if not entry:
            return await interaction.response.send_message("ℹ️ Utilisateur non whitelisté.", ephemeral=True)
        wl.remove(entry)
        await save_whitelist(wl)
        rv, rm = await ValidationView._get_roles(self, interaction.guild)
        if rm in member.roles: await member.remove_roles(rm)
        if rv not in member.roles: await member.add_roles(rv)
        await interaction.response.send_message(f"✅ {member.mention} retiré.", ephemeral=True)

    @app_commands.command(name="definir_message_validation", description="Définir le message privé envoyé après validation")
    @app_commands.default_permissions(administrator=True)
    async def definir_message_validation(self, interaction: discord.Interaction, message: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["message_validation"] = message
        sauvegarder_config(cfg)
        await interaction.response.send_message("✅ Message de validation mis à jour.", ephemeral=True)

    # rappel périodique
    @tasks.loop(hours=1)
    async def reminder_loop(self):
        cfg = charger_config()
        rid = cfg.get("salon_rappel_whitelist")
        if not rid:
            return
        ch = self.bot.get_channel(int(rid))
        if not ch:
            return
        demandes = await load_demandes()
        for d in demandes:
            user = self.bot.get_user(d['user_id'])
            if user:
                await ch.send(f"⏰ Rappel : {user.mention} ({d['prenom']} {d['nom']}) attend toujours une validation.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
