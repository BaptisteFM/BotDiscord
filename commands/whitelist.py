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

# --- chemins et locks ---
DEMANDES_PATH = "data/demandes_whitelist.json"
WL_PATH       = "data/whitelist.json"
demandes_lock = asyncio.Lock()
whitelist_lock = asyncio.Lock()

def _load_json(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

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

# --- envoi de DM protégé ---
async def safe_send_dm(user: discord.User, content: str):
    try:
        dm = user.dm_channel or await user.create_dm()
        return await dm.send(content)
    except Exception as e:
        # logger pour Render
        await log_erreur(None, None, f"safe_send_dm to {user.id} failed: {e}")
        return None

# --- Modal de demande d’accès ---
class AccessRequestModal(discord.ui.Modal, title="Demande d'accès au serveur"):
    prenom = discord.ui.TextInput(label="Prénom", placeholder="Ton prénom", max_length=50)
    nom    = discord.ui.TextInput(label="Nom", placeholder="Ton nom", max_length=50)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        # enregistrement de la demande
        demandes = await load_demandes()
        entry = {"user_id": user.id, "prenom": self.prenom.value, "nom": self.nom.value, "timestamp": datetime.utcnow().isoformat()}
        # remplace si existante
        demandes = [d for d in demandes if d["user_id"] != user.id] + [entry]
        await save_demandes(demandes)

        # envoi vers salon de validation
        cfg = charger_config()
        vid = cfg.get("journal_validation_channel")
        channel = interaction.guild.get_channel(int(vid)) if vid else None
        embed = discord.Embed(
            title="📨 Nouvelle demande d'accès",
            description=(
                f"{user.mention} souhaite rejoindre.\n"
                f"**Prénom** : {self.prenom.value}\n"
                f"**Nom**    : {self.nom.value}"
            ),
            color=discord.Color.blurple()
        ).set_footer(text=f"ID : {user.id}")
        view = ValidationView(self.bot, user.id, self.prenom.value, self.nom.value)
        if channel:
            await channel.send(embed=embed, view=view)
        else:
            await safe_send_dm(user, "⚠️ Votre demande a été enregistrée, mais aucun salon de validation n'est configuré.")

        await interaction.response.send_message(
            "✅ Votre demande a bien été envoyée aux modérateurs.", ephemeral=True
        )

# --- Vue de validation pour les admins ---
class ValidationView(discord.ui.View):
    def __init__(self, bot, user_id, prenom, nom):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.prenom = prenom
        self.nom = nom

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accept(self, button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        if not member:
            return await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)
        # rôles
        rv = discord.utils.get(guild.roles, name="Non vérifié")
        rm = discord.utils.get(guild.roles, name="Membre")
        if rv and rv in member.roles:
            await member.remove_roles(rv)
        if rm and rm not in member.roles:
            await member.add_roles(rm)
        # DM de bienvenue
        cfg = charger_config()
        msg_val = cfg.get("message_validation", "🎉 Bienvenue sur le serveur !")
        await safe_send_dm(member, msg_val)

        # ajout à la whitelist
        wl = await load_whitelist()
        if not any(e["user_id"] == member.id for e in wl):
            wl.append({
                "user_id": member.id,
                "prenom": self.prenom,
                "nom": self.nom,
                "validated": datetime.utcnow().isoformat()
            })
            await save_whitelist(wl)

        # suppression de la demande
        demandes = await load_demandes()
        demandes = [d for d in demandes if d["user_id"] != member.id]
        await save_demandes(demandes)

        await interaction.followup.send("✅ Utilisateur accepté et notifié.", ephemeral=True)

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def reject(self, button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        # DM de refus
        user = self.bot.get_user(self.user_id)
        if user:
            await safe_send_dm(user, "❌ Votre demande a été refusée. Contactez un modérateur si besoin.")
        # suppression de la demande
        demandes = await load_demandes()
        demandes = [d for d in demandes if d["user_id"] != self.user_id]
        await save_demandes(demandes)
        await interaction.followup.send("⛔ Utilisateur refusé.", ephemeral=True)

# --- Cog principale ---
class Whitelist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    # slash pour demander l'accès
    @app_commands.command(name="request_access", description="Demander l'accès au serveur")
    async def request_access(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AccessRequestModal(self.bot))

    # admin : config salon validation
    @app_commands.command(name="set_validation_channel", description="Définir le salon de validation")
    @app_commands.default_permissions(administrator=True)
    async def set_validation_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["journal_validation_channel"] = str(channel.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon de validation défini : {channel.mention}", ephemeral=True)

    # admin : lister la whitelist
    @app_commands.command(name="list_whitelist", description="Afficher tous les membres whitelistés")
    @app_commands.default_permissions(administrator=True)
    async def list_whitelist(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        wl = await load_whitelist()
        if not wl:
            return await interaction.response.send_message("ℹ️ La whitelist est vide.", ephemeral=True)
        lines = [f"{e['prenom']} {e['nom']} — <@{e['user_id']}> (validé : {e['validated'][:10]})" for e in wl]
        embed = discord.Embed(title="Whitelist", description="\n".join(lines), color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # admin : rechercher
    @app_commands.command(name="search_whitelist", description="Rechercher dans la whitelist")
    async def search_whitelist(self, interaction: discord.Interaction, query: str):
        if not (await is_admin(interaction.user) or role_autorise(interaction, "search_whitelist")):
            return await interaction.response.send_message("❌ Pas la permission.", ephemeral=True)
        wl = await load_whitelist()
        matches = [e for e in wl if query.lower() in e["prenom"].lower() or query.lower() in e["nom"].lower()]
        if not matches:
            return await interaction.response.send_message(f"❌ Aucun résultat pour `{query}`.", ephemeral=True)
        lines = [f"{e['prenom']} {e['nom']} — <@{e['user_id']}> (validé : {e['validated'][:10]})" for e in matches]
        embed = discord.Embed(title="Résultats", description="\n".join(lines), color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # admin : retirer
    @app_commands.command(name="remove_whitelist", description="Retirer un utilisateur de la whitelist")
    @app_commands.default_permissions(administrator=True)
    async def remove_whitelist(self, interaction: discord.Interaction, member: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        wl = await load_whitelist()
        entry = next((e for e in wl if e["user_id"] == member.id), None)
        if not entry:
            return await interaction.response.send_message("ℹ️ L'utilisateur n'est pas whitelisté.", ephemeral=True)
        wl.remove(entry)
        await save_whitelist(wl)
        # rôles
        rv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
        rm = discord.utils.get(interaction.guild.roles, name="Membre")
        if rm in member.roles:
            await member.remove_roles(rm)
        if rv not in member.roles:
            await member.add_roles(rv)
        await interaction.response.send_message(f"✅ {member.mention} retiré de la whitelist.", ephemeral=True)

    # rappel périodique des demandes
    @tasks.loop(hours=1)
    async def reminder_loop(self):
        cfg = charger_config()
        rid = cfg.get("salon_rappel_whitelist")
        if not rid:
            return
        channel = self.bot.get_channel(int(rid))
        if not channel:
            return
        demandes = await load_demandes()
        for d in demandes:
            user = self.bot.get_user(d["user_id"])
            if user:
                await channel.send(
                    f"⏰ Rappel : {user.mention} "
                    f"({d['prenom']} {d['nom']}) attend toujours une validation."
                )

async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
