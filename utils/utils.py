import json
import os
import discord

# Dossier persistant sur Render
DISK_PATH = "/DISK"

# Fichier de config principal (pour les salons autorisés et options personnalisables)
CONFIG_PATH = os.path.join(DISK_PATH, "config.json")

# Fichier pour stocker la liste des rôles créés
ROLES_PATH = os.path.join(DISK_PATH, "roles.json")

# ------------------------------------------------------
# Initialisation minimale des fichiers si inexistants
if not os.path.exists(DISK_PATH):
    os.makedirs(DISK_PATH)

if not os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "w") as f:
        json.dump({"salons_autorises": {}, "redirections": {}}, f, indent=4)

if not os.path.exists(ROLES_PATH):
    with open(ROLES_PATH, "w") as f:
        json.dump({}, f, indent=4)

# ------------------------------------------------------
def charger_config():
    """Charge la configuration depuis config.json."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def sauvegarder_config(data):
    """Sauvegarde la configuration dans config.json."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)

# ------------------------------------------------------
async def is_admin(member: discord.Member) -> bool:
    """Retourne True si le membre est administrateur."""
    return member.guild_permissions.administrator

def salon_est_autorise(command_name: str, channel_id: int) -> bool:
    """Vérifie que la commande est exécutée dans le salon autorisé dans la config."""
    config = charger_config()
    salons_autorises = config.get("salons_autorises", {})
    salon_id_autorise = salons_autorises.get(command_name)
    return str(channel_id) == str(salon_id_autorise)

def definir_salon_autorise(command_name: str, channel_id: int):
    """Définit le salon autorisé pour une commande donnée."""
    config = charger_config()
    if "salons_autorises" not in config:
        config["salons_autorises"] = {}
    config["salons_autorises"][command_name] = str(channel_id)
    sauvegarder_config(config)

# ------------------------------------------------------
def definir_option_config(option: str, value: str):
    """Définit une option générique (ex: redirection) dans la config."""
    config = charger_config()
    config[option] = value
    sauvegarder_config(config)

def definir_redirection(redirection_type: str, channel_id: int):
    """Définit la redirection d'un type de message (ex: 'burnout') dans la config."""
    config = charger_config()
    if "redirections" not in config:
        config["redirections"] = {}
    config["redirections"][redirection_type] = str(channel_id)
    sauvegarder_config(config)

def get_redirection(redirection_type: str) -> str:
    """Retourne l'ID du salon défini pour une redirection donnée."""
    config = charger_config()
    return config.get("redirections", {}).get(redirection_type)

# ------------------------------------------------------
def enregistrer_role(role_id: int, role_name: str):
    """Enregistre un rôle créé dans roles.json."""
    with open(ROLES_PATH, "r") as f:
        data = json.load(f)
    data[str(role_id)] = role_name
    with open(ROLES_PATH, "w") as f:
        json.dump(data, f, indent=4)

async def get_or_create_role(guild: discord.Guild, role_name: str) -> discord.Role:
    """Retourne un rôle existant ou le crée et l'enregistre."""
    role = discord.utils.get(guild.roles, name=role_name)
    if role is None:
        role = await guild.create_role(name=role_name)
        enregistrer_role(role.id, role.name)
    return role

async def get_or_create_category(guild: discord.Guild, category_name: str) -> discord.CategoryChannel:
    """Retourne une catégorie existante ou la crée."""
    category = discord.utils.get(guild.categories, name=category_name)
    if category is None:
        category = await guild.create_category(category_name)
    return category

# ===============================
# Gestion de la persistance du mapping Reaction Rôle
# ===============================

RR_MAPPING_PATH = os.path.join(DISK_PATH, "reaction_role_mapping.json")

def load_reaction_role_mapping():
    """Charge le mapping des messages de réaction rôle depuis le disque persistant."""
    if not os.path.exists(RR_MAPPING_PATH):
        with open(RR_MAPPING_PATH, "w") as f:
            json.dump({}, f, indent=4)
    with open(RR_MAPPING_PATH, "r") as f:
        return json.load(f)

def save_reaction_role_mapping(mapping):
    """Sauvegarde le mapping des messages de réaction rôle dans le disque persistant."""
    with open(RR_MAPPING_PATH, "w") as f:
        json.dump(mapping, f, indent=4)
