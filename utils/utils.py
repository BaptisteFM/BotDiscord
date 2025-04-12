import discord
import json
import os

# Chemins vers les fichiers JSON de configuration
CONFIG_PATH = "data/config.json"
REACTION_ROLE_PATH = "data/reaction_roles.json"
SALONS_AUTORISES_PATH = "data/salons_autorises.json"
WHITELIST_PATH = "data/whitelist.json"

# ========== Chargement & Sauvegarde de la configuration ==========
def charger_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_config(data):
    os.makedirs("data", exist_ok=True)  # Crée le dossier s'il n'existe pas
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
        salon_autorise = data.get(nom_commande)
        if salon_autorise is None:
            return True
        if int(channel_id) == int(salon_autorise):
            return True
        if user and getattr(user, "guild_permissions", None) and user.guild_permissions.administrator:
            return "admin_override"
        return False
    return True

# ========== Gestion des redirections ==========
def definir_redirection(redirection_type: str, salon_id: int):
    config = charger_config()
    config["redirections"] = config.get("redirections", {})
    config["redirections"][redirection_type] = str(salon_id)
    sauvegarder_config(config)

def get_redirection(redirection_type: str) -> str | None:
    config = charger_config()
    return config.get("redirections", {}).get(redirection_type)

# ========== Gestion des options diverses ==========
def definir_option_config(option: str, valeur: str):
    config = charger_config()
    config[option] = valeur
    sauvegarder_config(config)

# ========== Gestion Reaction Roles persistants ==========
def load_reaction_role_mapping() -> dict:
    if not os.path.exists(REACTION_ROLE_PATH):
        return {}
    with open(REACTION_ROLE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_reaction_role_mapping(data: dict):
    with open(REACTION_ROLE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# ========== Gestion de la whitelist ==========
def charger_whitelist() -> list:
    if not os.path.exists(WHITELIST_PATH):
        return []
    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_whitelist(whitelist: list):
    os.makedirs("data", exist_ok=True)
    with open(WHITELIST_PATH, "w", encoding="utf-8") as f:
        json.dump(whitelist, f, indent=4)

# ========== Logs d’erreurs dans un salon Discord ==========
async def log_erreur(bot: discord.Client, guild: discord.Guild, message: str):
    try:
        print(f"[ERREUR BOT] {message}")  # Affichage console pour debugging

        config = charger_config()
        log_channel_id = config.get("log_erreurs_channel")
        if not log_channel_id:
            print("[LOG] Aucun salon de logs défini.")
            return

        log_channel = guild.get_channel(int(log_channel_id))
        if not log_channel:
            print(f"[LOG] Salon ID {log_channel_id} introuvable sur le serveur.")
            return

        embed = discord.Embed(title="❌ Erreur détectée", description=message, color=discord.Color.red())
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"[ERREUR LORS DU LOG] {e}")
