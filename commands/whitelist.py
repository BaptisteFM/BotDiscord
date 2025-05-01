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

# --- Chemins et verrous ---
DEMANDES_PATH = "data/demandes_whitelist.json"
WL_PATH       = "data/whitelist.json"
demandes_lock = asyncio.Lock()
whitelist_lock = asyncio.Lock()

# Fonctions utilitaires synchrones
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

# Fonctions asynchrones pour JSON
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

# Envoi de DM protégé
async def safe_send_dm(user: discord.User, content: str):
    try:
        dm = user.dm_channel or await user.create_dm()
        return await dm.send(content)
    except Exception as e:
        # logger pour Render
        await log_erreur(None, None, f"safe_send_dm vers {user.id} a échoué : {e}")
        return None

# --- Modal de demande d'accès ---
class DemandeAccesModal(discord.ui.Modal, title="Demande d'accès au serveur"):
    prenom = discord.ui.TextInput(label="Prénom", placeholder="Ton prénom", max_length=50)
    nom    = discord.ui.TextInput(label="Nom", placeholder="Ton nom", max_length=50)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        # Enregistrement de la demande
        demandes = await load_demandes()
        entry = {"user_id": user.id, "prenom": self.prenom.value, "nom": self.nom.value, "timestamp": datetime.utcnow().isoformat()}
        demandes = [d for d in demandes if d.get("user_id") != user.id] + [entry]
        await save_demandes(demandes)

        # Envoi vers salon de validation
        cfg = charger_config()
        vid = cfg.get("journal_validation_channel")
        guild = interaction.guild
        embed = discord.Embed(
            title="📨 Nouvelle demande d'accès",
            description=(
                f"{user.mention} souhaite rejoindre.\n"
                f"**Prénom** : {self.prenom.value}\n"
                f"**Nom**    : {self.nom.value}"
            ),
            color=discord.Color.blurple()
        ).set_footer(text=f"ID : {user.id}")
        if vid and guild:
            target = guild.get_channel(int(vid))
            if target:
                view = ValidationView(self.bot, user.id, self.prenom.value, self.nom.value)
                await target.send(embed=embed, view=view)
            else:
                await safe_send_dm(user, "⚠️ Salon de validation non trouvé.")
        else:
            await safe_send_dm(user, "⚠️ Aucun salon de validation configuré.")

        await interaction.response.send_message("✅ Ta demande a bien été envoyée aux modérateurs.", ephemeral=True)

# --- Vue pour publier le bouton de demande d'accès ---
class RequestAccessView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Demander l'accès", style=discord.ButtonStyle.primary, custom_id="btn_demande_acces")
    async def demander(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DemandeAccesModal(self.bot))

# --- Vue de validation pour les admins ---
class ValidationView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, prenom: str, nom: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.prenom = prenom
        self.nom = nom

    async def _get_roles(self, guild: discord.Guild):
        cfg = charger_config()
        # IDs en config ou noms par défaut
        rid_nv = cfg.get("role_non_verifie_id")
        rid_m  = cfg.get("role_membre_id")
        role_nv = guild.get_role(int(rid_nv)) if rid_nv else discord.utils.get(guild.roles, name="Non vérifié")
        role_m  = guild.get_role(int(rid_m))  if rid_m  else discord.utils.get(guild.roles, name="Membre")
        return role_nv, role_m

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        if not member:
            return await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)
        # Récupération des rôles
        role_nv, role_m = await self._get_roles(guild)
        # Assignation
        if role_nv and role_nv in member.roles:
            await member.remove_roles(role_nv)
        if role_m and role_m not in member.roles:
            await member.add_roles(role_m)
        # DM de bienvenue
        cfg = charger_config()
        msg_val = cfg.get("message_validation", "🎉 Bienvenue sur le serveur !")
        await safe_send_dm(member, msg_val)
        # Ajout à la whitelist
        wl = await load_whitelist()
        if not any(e.get("user_id") == member.id for e in wl):
            wl.append({
                "user_id": member.id,
                "prenom": self.prenom,
                "nom": self.nom,
                "validated": datetime.utcnow().isoformat()
            })
            await save_whitelist(wl)
        # Suppression de la demande
        demandes = await load_demandes()
        demandes = [d for d in demandes if d.get("user_id") != member.id]
        await save_demandes(demandes)
        await interaction.followup.send("✅ Utilisateur accepté et notifié.", ephemeral=True)

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        # DM de refus
        user = self.bot.get_user(self.user_id)
        if user:
            await safe_send_dm(user, "❌ Ta demande a été refusée. Contacte un modérateur si besoin.")
        # Suppression de la demande
        demandes = await load_demandes()
        demandes = [d for d in demandes if d.get("user_id") != self.user_id]
        await save_demandes(demandes)
        await interaction.followup.send("⛔ Utilisateur refusé.", ephemeral=True)

# --- Cog principal ---
class Whitelist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Enregistrer la vue persistante pour le bouton
        self.bot.add_view(RequestAccessView(bot))
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    # Admin : publier le message de demande d'accès
    @app_commands.command(name="publier_demande_acces", description="Publier le bouton de demande d'accès au serveur")
    @app_commands.default_permissions(administrator=True)
    async def publier_demande_acces(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        embed = discord.Embed(
            title="Demande d'accès",
            description="Clique sur le bouton ci-dessous pour demander l'accès au serveur.",
            color=discord.Color.blurple()
        )
        await salon.send(embed=embed, view=RequestAccessView(self.bot))
        await interaction.response.send_message(f"✅ Message publié dans {salon.mention}.", ephemeral=True)

    # Slash pour demander l'accès (fallback)
    @app_commands.command(name="demande_acces", description="Ouvre le formulaire de demande d'accès")
    async def commande_demande_acces(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DemandeAccesModal(self.bot))

    # Admin : définir salon validation
    @app_commands.command(name="definir_salon_validation", description="Définir le salon de validation")
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        cfg = charger_config()
        cfg["journal_validation_channel"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon de validation défini : {salon.mention}", ephemeral=True)

    # Admin : définir salon rappel
    @app_commands.command(name="definir_salon_rappel", description="Définir le salon pour rappels de demandes")
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_rappel(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        cfg = charger_config()
        cfg["salon_rappel_whitelist"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon de rappel défini : {salon.mention}", ephemeral=True)

    # Admin : définir rôles
    @app_commands.command(name="definir_role_non_verifie", description="Définir le rôle des non vérifiés")
    @app_commands.default_permissions(administrator=True)
    async def definir_role_non_verifie(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        cfg = charger_config()
        cfg["role_non_verifie_id"] = str(role.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Rôle non vérifié défini : {role.mention}", ephemeral=True)

    @app_commands.command(name="definir_role_membre", description="Définir le rôle des membres validés")
    @app_commands.default_permissions(administrator=True)
    async def definir_role_membre(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        cfg = charger_config()
        cfg["role_membre_id"] = str(role.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Rôle membre défini : {role.mention}", ephemeral=True)

    # Admin : lister whitelist
    @app_commands.command(name="lister_whitelist", description="Afficher tous les membres whitelistés")
    @app_commands.default_permissions(administrator=True)
    async def lister_whitelist(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        wl = await load_whitelist()
        if not wl:
            return await interaction.response.send_message("ℹ️ La whitelist est vide.", ephemeral=True)
        lignes = [f"{e['prenom']} {e['nom']} — <@{e['user_id']}> (validé : {e['validated'][:10]})" for e in wl]
        embed = discord.Embed(title="Whitelist", description="\n".join(lignes), color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Admin : rechercher whitelist
    @app_commands.command(name="rechercher_whitelist", description="Rechercher dans la whitelist")
    async def rechercher_whitelist(self, interaction: discord.Interaction, query: str):
        if not (await is_admin(interaction.user) or role_autorise(interaction, "rechercher_whitelist")):
            return await interaction.response.send_message("❌ Pas la permission.", ephemeral=True)
        wl = await load_whitelist()
        matches = [e for e in wl if query.lower() in e['prenom'].lower() or query.lower() in e['nom'].lower()]
        if not matches:
            return await interaction.response.send_message(f"❌ Aucun résultat pour `{query}`.", ephemeral=True)
        lignes = [f"{e['prenom']} {e['nom']} — <@{e['user_id']}>" for e in matches]
        embed = discord.Embed(title="Résultats", description="\n".join(lignes), color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Admin : retirer whitelist
    @app_commands.command(name="retirer_whitelist", description="Retirer un utilisateur de la whitelist")
    @app_commands.default_permissions(administrator=True)
    async def retirer_whitelist(self, interaction: discord.Interaction, membre: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        wl = await load_whitelist()
        entry = next((e for e in wl if e['user_id'] == membre.id), None)
        if not entry:
            return await interaction.response.send_message("ℹ️ L'utilisateur n'est pas whitelisté.", ephemeral=True)
        wl.remove(entry)
        await save_whitelist(wl)
        # Gestion des rôles
        guild = interaction.guild
        cfg = charger_config()
        rv = guild.get_role(int(cfg.get("role_non_verifie_id"))) if cfg.get("role_non_verifie_id") else discord.utils.get(guild.roles, name="Non vérifié")
        rm = guild.get_role(int(cfg.get("role_membre_id"))) if cfg.get("role_membre_id") else discord.utils.get(guild.roles, name="Membre")
        if rm and rm in membre.roles:
            await membre.remove_roles(rm)
        if rv and rv not in membre.roles:
            await membre.add_roles(rv)
        await interaction.response.send_message(f"✅ {membre.mention} retiré de la whitelist.", ephemeral=True)

    # Rappel périodique des demandes
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
            user = self.bot.get_user(d['user_id'])
            if user:
                await channel.send(f"⏰ Rappel : {user.mention} ({d['prenom']} {d['nom']}) attend toujours une validation.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
