import json
import os
import discord

# Dossier persistant sur Render
DISK_PATH = "/data"

# Fichiers de configuration
CONFIG_PATH = os.path.join(DISK_PATH, "config.json")
ROLES_PATH = os.path.join(DISK_PATH, "roles.json")
RR_MAPPING_PATH = os.path.join(DISK_PATH, "reaction_role_mapping.json")

# Initialisation des fichiers s'ils n'existent pas
if not os.path.exists(DISK_PATH):
    os.makedirs(DISK_PATH)

if not os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "w") as f:
        json.dump({"salons_autorises": {}, "redirections": {}}, f, indent=4)

if not os.path.exists(ROLES_PATH):
    with open(ROLES_PATH, "w") as f:
        json.dump({}, f, indent=4)

if not os.path.exists(RR_MAPPING_PATH):
    with open(RR_MAPPING_PATH, "w") as f:
        json.dump({}, f, indent=4)

# ------------------- CONFIGURATION GÉNÉRALE -------------------

def charger_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def sauvegarder_config(data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)

# ------------------- ADMIN -------------------

async def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator

# ------------------- VÉRIFICATION DE SALON -------------------

async def salon_est_autorise(command_name: str, channel_id: int, member: discord.Member) -> bool:
    if await is_admin(member):
        return True  # Les admins peuvent tout exécuter partout
    config = charger_config()
    salons_autorises = config.get("salons_autorises", {})
    salon_id_autorise = salons_autorises.get(command_name)
    return str(channel_id) == str(salon_id_autorise)

def definir_salon_autorise(command_name: str, channel_id: int):
    config = charger_config()
    if "salons_autorises" not in config:
        config["salons_autorises"] = {}
    config["salons_autorises"][command_name] = str(channel_id)
    sauvegarder_config(config)

# ------------------- CONFIG PERSONNALISÉE -------------------

def definir_option_config(option: str, value: str):
    config = charger_config()
    config[option] = value
    sauvegarder_config(config)

def definir_redirection(redirection_type: str, channel_id: int):
    config = charger_config()
    if "redirections" not in config:
        config["redirections"] = {}
    config["redirections"][redirection_type] = str(channel_id)
    sauvegarder_config(config)

def get_redirection(redirection_type: str) -> str:
    config = charger_config()
    return config.get("redirections", {}).get(redirection_type)

# ------------------- ROLES & CATÉGORIES -------------------

def enregistrer_role(role_id: int, role_name: str):
    with open(ROLES_PATH, "r") as f:
        data = json.load(f)
    data[str(role_id)] = role_name
    with open(ROLES_PATH, "w") as f:
        json.dump(data, f, indent=4)

async def get_or_create_role(guild: discord.Guild, role_name: str) -> discord.Role:
    role = discord.utils.get(guild.roles, name=role_name)
    if role is None:
        role = await guild.create_role(name=role_name)
        enregistrer_role(role.id, role.name)
    return role

async def get_or_create_category(guild: discord.Guild, category_name: str) -> discord.CategoryChannel:
    category = discord.utils.get(guild.categories, name=category_name)
    if category is None:
        category = await guild.create_category(category_name)
    return category

# ------------------- RÉACTIONS & ROLES -------------------

def load_reaction_role_mapping():
    with open(RR_MAPPING_PATH, "r") as f:
        return json.load(f)

def save_reaction_role_mapping(mapping):
    with open(RR_MAPPING_PATH, "w") as f:
        json.dump(mapping, f, indent=4)
