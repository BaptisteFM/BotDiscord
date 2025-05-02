# utils.py
import discord
import json
import os

# Tous les fichiers JSON dans /data pour persistance sur Render
CONFIG_PATH               = "/data/config.json"
REACTION_ROLE_PATH        = "/data/reaction_roles.json"
SALONS_AUTORISES_PATH     = "/data/salons_autorises.json"
WHITELIST_PATH            = "/data/whitelist.json"
PERMISSIONS_PATH          = "/data/permissions.json"

# ========== Chargement & Sauvegarde de la configuration ==========
def charger_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_config(data):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# ========== Vérification des droits d'administrateur ==========
async def is_admin(user: discord.User | discord.Member) -> bool:
    return getattr(user, "guild_permissions", None) and user.guild_permissions.administrator

# ========== Gestion des rôles ==========
async def get_or_create_role(guild: discord.Guild, role_name: str) -> discord.Role:
    role = discord.utils.get(guild.roles, name=role_name)
    if role:
        return role
    try:
        return await guild.create_role(name=role_name, reason="Création automatique via bot")
    except Exception as e:
        raise RuntimeError(f"Erreur lors de la création du rôle '{role_name}' : {e}")

# ========== Gestion des catégories ==========
async def get_or_create_category(guild: discord.Guild, category_name: str) -> discord.CategoryChannel:
    existing = discord.utils.get(guild.categories, name=category_name)
    if existing:
        return existing
    try:
        return await guild.create_category(name=category_name)
    except Exception as e:
        raise RuntimeError(f"Erreur lors de la création de la catégorie '{category_name}' : {e}")

# ========== Gestion des salons autorisés ==========
def definir_salon_autorise(nom_commande: str, salon_id: int):
    os.makedirs(os.path.dirname(SALONS_AUTORISES_PATH), exist_ok=True)
    if not os.path.exists(SALONS_AUTORISES_PATH):
        data = {}
    else:
        with open(SALONS_AUTORISES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    data[nom_commande] = salon_id
    with open(SALONS_AUTORISES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def salon_est_autorise(nom_commande: str, channel_id: int, user: discord.User | discord.Member = None):
    if os.path.exists(SALONS_AUTORISES_PATH):
        with open(SALONS_AUTORISES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        allowed = data.get(nom_commande)
        if allowed is None or int(channel_id) == int(allowed):
            return True
        if user and getattr(user, "guild_permissions", None) and user.guild_permissions.administrator:
            return "admin_override"
        return False
    return True

# ========== Gestion des redirections ==========
def definir_redirection(redirection_type: str, salon_id: int):
    cfg = charger_config()
    cfg["redirections"] = cfg.get("redirections", {})
    cfg["redirections"][redirection_type] = str(salon_id)
    sauvegarder_config(cfg)

def get_redirection(redirection_type: str) -> str | None:
    cfg = charger_config()
    return cfg.get("redirections", {}).get(redirection_type)

# ========== Gestion des options diverses ==========
def definir_option_config(option: str, valeur: str):
    cfg = charger_config()
    cfg[option] = valeur
    sauvegarder_config(cfg)

# ========== Gestion Reaction Roles persistants ==========
def load_reaction_role_mapping() -> dict:
    if not os.path.exists(REACTION_ROLE_PATH):
        return {}
    with open(REACTION_ROLE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_reaction_role_mapping(data: dict):
    os.makedirs(os.path.dirname(REACTION_ROLE_PATH), exist_ok=True)
    with open(REACTION_ROLE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# ========== Gestion de la whitelist ==========
def charger_whitelist() -> list:
    if not os.path.exists(WHITELIST_PATH):
        return []
    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_whitelist(whitelist: list):
    os.makedirs(os.path.dirname(WHITELIST_PATH), exist_ok=True)
    with open(WHITELIST_PATH, "w", encoding="utf-8") as f:
        json.dump(whitelist, f, indent=4)

# ========== Logs d’erreurs dans un salon Discord ==========
async def log_erreur(bot: discord.Client, guild: discord.Guild, message: str):
    try:
        print(f"[ERREUR BOT] {message}")
        cfg = charger_config()
        log_channel_id = cfg.get("log_erreurs_channel")
        if not log_channel_id:
            print("[LOG] Aucun salon de logs défini.")
            return
        channel = guild.get_channel(int(log_channel_id))
        if not channel:
            print(f"[LOG] Salon ID {log_channel_id} introuvable.")
            return
        embed = discord.Embed(title="❌ Erreur détectée", description=message, color=discord.Color.red())
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[ERREUR LORS DU LOG] {e}")

# ========== Gestion des permissions ==========
def charger_permissions() -> dict:
    if not os.path.exists(PERMISSIONS_PATH):
        return {}
    with open(PERMISSIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_permissions(permissions: dict):
    os.makedirs(os.path.dirname(PERMISSIONS_PATH), exist_ok=True)
    with open(PERMISSIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(permissions, f, indent=4)

def role_autorise(interaction: discord.Interaction, commande: str) -> bool:
    if not os.path.exists(PERMISSIONS_PATH):
        return False
    with open(PERMISSIONS_PATH, "r", encoding="utf-8") as f:
        perms = json.load(f)
    autorises = perms.get(commande, [])
    return any(str(role.id) in autorises for role in interaction.user.roles)

# ========== Vérification du statut de membre ==========
async def is_verified_user(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    cfg = charger_config()
    role_id = cfg.get("role_acces_utilisateur")
    if role_id:
        role = member.guild.get_role(int(role_id))
        return role in member.roles
    return False

async def is_non_verified_user(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return False
    non_verified = discord.utils.get(member.guild.roles, name="Non vérifié")
    return non_verified in member.roles if non_verified else False
